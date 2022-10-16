""" Update repository metadata.

"""
from __future__ import annotations

from aiohttp import ClientSession
from asyncio import gather, run
from io import BytesIO
from operator import itemgetter
from pathlib import Path, PosixPath
from semver import VersionInfo
from toml import load
from typing import IO, Sequence
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


class _RepoConfig:
    """ Plugin repository configuration.

    """
    def __init__(self, plugins: Sequence[_Plugin]):
        """ Initialize an instance.

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
        meta = plugin.meta()
        id = meta.find("id").text
        parent = self._xml.getroot()
        elem = etree.SubElement(parent, "plugin", {"id": id})
        elem.attrib |= {
            "version": meta.find("version").text,
            "url": plugin.url,
        }
        etree.SubElement(elem, "idea-version")
        elem.find("idea-version").attrib |= meta.find("idea-version").attrib
        return


class _Plugin:
    """ Plugin file.

    """
    @classmethod
    async def get(cls, user: str, repo: str, artifact: str):
        """ Get a plugin from GitHub.

        :param user: GitHub user
        :param repo: plugin repo name
        :param artifact: plugin artifact name
        """
        release = await _GitHubRelease.get(user, repo)
        name = f"{artifact}-{release.version}.zip"
        url = release.assets[name]["browser_download_url"]
        jar = await _JarFile.download(url)
        return _Plugin(url, jar)

    def __init__(self, url: str, jar: _JarFile):
        """ Initialize this object.

        :param url: plugin URL
        :param jar: distribution JAR
        """
        self.url = url
        self._jar = jar
        return

    def meta(self) -> etree.Element:
        """ Extract plugin metadata.

        :return: XML
        """
        root_dir = next(self._jar.root.iterdir())  # single root directory
        assert root_dir.is_dir()
        meta_file = "META-INF/plugin.xml"
        for item in root_dir.joinpath("lib").iterdir():
            # Find plugin library.
            if item.name.startswith(root_dir.name):
                lib = _JarFile(item.open("rb"))
                doc = etree.parse(lib.item(meta_file))
                return doc.getroot()
        else:
            raise ValueError(f"Could not find {meta_file}")


# Execute the application.

if __name__ == "__main__":
    raise SystemExit(run(main()))
