""" Update repository metadata.

"""
from __future__ import annotations

from aiohttp import ClientSession
from asyncio import gather, run
from io import BytesIO
from jinja2 import Environment, FileSystemLoader
from operator import itemgetter
from pathlib import Path, PosixPath
from semver import VersionInfo
from toml import load
from typing import IO, Sequence
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as etree
from zipfile import ZipFile, Path as ZipPath


__all__ = "main",


async def main() -> int:
    """ Application entry point.

    :return: exit status
    """
    config = load("config.toml")
    user = config["user"]
    args = itemgetter("repo", "artifact")
    tasks = [_Plugin.get(user, *args(item)) for item in config["plugins"]]
    plugins = await gather(*tasks)
    repo_config = _RepoConfig(plugins)
    repo_config.write(config["repo_config"])
    index_file = _IndexFile(user, plugins)
    index_file.write("dist/index.html")
    return 0


class _GitHubRelease:
    """ GitHub release resource.

    """
    @classmethod
    def _semver(cls, tag: str) -> VersionInfo:
        """ Get SemVer of a release from its Git tag.

        :return: version
        """
        return VersionInfo.parse(tag.lstrip("v"))

    @classmethod
    async def get(cls, user: str, repo: str, tag=None) -> _GitHubRelease:
        """ Get a release from the GitHub API.

        :param user: GitHub username
        :param repo: project repo name
        :param tag: release tag; defaults to latest version
        :return: release object
        """
        api = "https://api.github.com"
        url = "/".join((api, "repos", user, repo, "releases"))
        headers = {
            "Accept": "application/vnd.github+json"
        }
        async with ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                # TODO: Error checking.
                content = await response.json()
        releases = {item["tag_name"]: item for item in content}
        if not tag:
            tag = str(max(releases.keys(), key=cls._semver))
        return cls(releases[tag])

    def __init__(self, release: dict):
        """ Initialize a new instance from a release resource.

        """
        self._release = release
        self.version = self._semver(release["tag_name"])
        self.assets = {item.pop("name"): item for item in self._release["assets"]}
        return


class _JarFile:
    """ Java ARchive file (jar/zip).

    """
    @classmethod
    async def download(cls, url: str) -> _JarFile:
        """ Create a JarFile from a remote file.

        :param url: JAR file URL
        :return: new JarFile instance
        """
        async with ClientSession() as session:
            async with session.get(url) as response:
                # Cannot create a ZipFile with an async stream, so wrap
                # contents in a regular stream. This is not ideal for large
                # files, but in this case the files are <100 kB.
                stream = BytesIO(await response.content.read())
        return _JarFile(stream)

    def __init__(self, stream: IO[bytes]):
        """ Initialize a new instance from a byte stream.

        :param: url: URL of origin
        :param stream: input data
        """
        self._archive = ZipFile(stream)
        return

    @property
    def root(self) -> ZipPath:
        """ Return a Path-like object for iterating over an archive.

        :return: path object
        """
        return ZipPath(self._archive)

    def item(self, path: PosixPath | str) -> IO[bytes]:
        """ Return an input stream for an item in the archive.

        :param path: file path within the archive
        :return: binary stream to read the file
        """
        return self._archive.open(str(path), "r")


class _Plugin:
    """ Plugin file.

    """
    @classmethod
    async def get(cls, user: str, repo: str, artifact: str):
        """ Get a plugin from GitHub.

        :param user: GitHub user
        :param repo: parent repo name
        :param artifact: plugin artifact name
        """
        release = await _GitHubRelease.get(user, repo)
        name = f"{artifact}-{release.version}.zip"
        url = release.assets[name]["browser_download_url"]
        jar = await _JarFile.download(url)
        return _Plugin(url, jar)

    def __init__(self, url: str, jar: _JarFile):
        """ Initialize this object.

        :param repo: parent repo name
        :param url: plugin URL
        :param jar: distribution JAR
        """
        self._jar = jar
        self.url = url
        self.meta = self._meta(self._jar)
        config = load("config.toml")
        return

    @classmethod
    def _meta(cls, jar: _JarFile) -> dict:
        """ Extract plugin metadata.

        :return: XML
        """
        root_dir = next(jar.root.iterdir())  # single root directory
        assert root_dir.is_dir()
        meta_file = "META-INF/plugin.xml"
        for item in root_dir.joinpath("lib").iterdir():
            # Find plugin library.
            if item.name.startswith(root_dir.name):
                lib = _JarFile(item.open("rb"))
                doc = etree.parse(lib.item(meta_file))
                root = doc.getroot()
                break
        else:
            raise ValueError(f"Could not find {meta_file}")
        keys = "id", "name", "version", "description"
        meta = {key: root.find(key).text for key in keys}
        keys = "idea-version",
        meta |= {key: root.find(key).attrib for key in keys}
        return meta


class _RepoConfig:
    """ Plugin repository configuration.

    """
    def __init__(self, plugins: Sequence[_Plugin]):
        """ Initialize an instance.

        :param plugins: plugins for this repo
        """
        self._xml = etree.ElementTree(etree.Element("plugins"))
        for plugin in plugins:
            self._add(plugin)
        return

    def write(self, path: str | Path):
        """ Write XML file.

        :param path: output path
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        etree.indent(self._xml)
        self._xml.write(path, encoding="utf-8", xml_declaration=True)
        return

    def _add(self, plugin: _Plugin):
        """ Add <plugin> element.

        :param plugin: plugin object
        """
        attrib = {key: plugin.meta[key] for key in ("id", "version")}
        attrib["url"] = plugin.url
        elem = etree.SubElement(self._xml.getroot(), "plugin", attrib)
        attrib = {key: plugin.meta[key] for key in ("idea-version",)}
        etree.SubElement(elem, "idea-version", attrib)
        return


class _IndexFile:
    """ Template for index.html.

    """
    @classmethod
    def repo_url(cls, plugin_url: str) -> str:
        """ Get parent project repo from a plugin repo.

        :param plugin_url: plugin file URL
        :return: user URL
        """
        url = urlsplit(plugin_url)
        path = url.path.split("/")
        url = url._replace(path="/".join(path[:path.index("releases")]))
        return urlunsplit(url)

    def __init__(self, user: str, plugins: Sequence[_Plugin]):
        """ Initialize an instance.

        """
        env = Environment(loader=FileSystemLoader("."), autoescape=False)
        self._template = env.get_template("src/index.html")
        self._context = {
            "user": user,
            "plugins": []
        }
        for plugin in plugins:
            params = plugin.meta.copy()
            params["repo"] = self.repo_url(plugin.url)
            self._context["plugins"].append(params)
        return

    def write(self, path: str | Path):
        """ Write rendered template to a file.

        :param path: output path
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = self._template.stream(**self._context)
        stream.dump(str(path))
        return


# Execute the application.

if __name__ == "__main__":
    raise SystemExit(run(main()))
