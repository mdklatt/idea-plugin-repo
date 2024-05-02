""" Build site files.

"""
from __future__ import annotations

from asyncio import gather, run
from io import BytesIO
from pathlib import Path, PosixPath
from typing import IO, Optional, Sequence
from xml.etree import ElementTree as etree
from zipfile import ZipFile, Path as ZipPath

from aiohttp import ClientSession
from jinja2 import Environment, FileSystemLoader
from semver import Version
from toml import load


__all__ = "main",


config = load("config.toml")


async def main() -> int:
    """ Application entry point.

    :return: exit status
    """
    context = await PluginContext.define(config["github"]["user"], config["plugins"])
    for name in config["content"]["templates"]:
        path = Path(config["content"]["dist"], name)
        StaticTemplate(name).render(path, context)
    return 0


class StaticTemplate:
    """ Static file template.

    """
    _env = Environment(loader=FileSystemLoader(config["content"]["src"]), autoescape=False)

    def __init__(self, name: str):
        """ Initialize this instance.

        :param name: Jinja template name
        """
        self._template = self._env.get_template(name)
        return

    def render(self, path: str | Path, context: Optional[dict] = None):
        """ Render the template.

        :param path: output file path
        :param context: template parameters
        """
        if not context:
            context = {}
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = self._template.stream(**context)
        stream.dump(str(path))
        return


class PluginContext(dict):
    """ Template context for plugin data.

    """
    @classmethod
    async def define(cls, user: str, plugins: Sequence[dict]) -> PluginContext:
        """ Define a new context.

        :param user: GitHub user
        :param plugins: sequence of plugin config data
        :return: initialized context
        """
        context = cls({"user": user})
        tasks = [cls._download(user, plugin) for plugin in plugins]
        context["plugins"] = [item for item in await gather(*tasks)]
        return context

    @classmethod
    async def _download(cls, user: str, plugin: dict) -> dict:
        """ Download plugin metadata from GitHub.

        :param user: GitHub user
        :param plugin: plugin config data
        :return: plugin metadata
        """
        release = await _GitHubRelease.get(user, plugin["repo"])
        name = f"{plugin['artifact']}-{release.version.finalize_version()}.zip"
        url = release.assets[name]["browser_download_url"]
        jar = await _JarFile.download(url)
        return plugin | cls._metadata(jar)

    @classmethod
    def _metadata(cls, jar: _JarFile) -> dict:
        """ Get plugin metadata from its JAR file.

        :param jar: plugin distribution file
        :return: plugin metadata
        """
        root_dir = next(jar.root.iterdir())  # single root directory
        assert root_dir.is_dir()
        meta_file = "META-INF/plugin.xml"
        for item in root_dir.joinpath("lib").iterdir():
            # Find plugin library.
            if root_dir.name in item.name:
                url = f"zip:://{item.at}"
                lib = _JarFile(url, item.open("rb"))
                doc = etree.parse(lib.item(meta_file))
                root = doc.getroot()
                break
        else:
            raise ValueError(f"Could not find {meta_file}")
        text_keys = "id", "name", "version", "description"
        metadata = {key: root.find(key).text for key in text_keys}
        attr_keys = "idea-version",
        metadata.update({key: root.find(key).attrib for key in attr_keys})
        metadata["url"] = jar.url
        return metadata


class _GitHubRelease:
    """ GitHub API release resource.

    """
    @classmethod
    def _semver(cls, tag: str) -> Version:
        """ Get SemVer of a release from its Git tag.

        :return: version
        """
        return Version.parse(tag.lstrip("v"))

    @classmethod
    async def get(cls, user: str, repo: str, tag=None) -> _GitHubRelease:
        """ Get a release from the GitHub API.

        :param user: GitHub username
        :param repo: project repo name
        :param tag: release tag; defaults to latest version
        :return: release object
        """
        api = config["github"]["api"]
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
        return _JarFile(url, stream)

    def __init__(self, url: str, stream: IO[bytes]):
        """ Initialize a new instance from a byte stream.

        :param: url: URL of origin
        :param stream: input data
        """
        self.url = url
        self._archive = ZipFile(stream)
        return

    @property
    def root(self) -> ZipPath:
        """ Return a Path-ish object for iterating over an archive.

        :return: path object
        """
        return ZipPath(self._archive)

    def item(self, path: PosixPath | str) -> IO[bytes]:
        """ Return an input stream for an item in the archive.

        :param path: file path within the archive
        :return: binary input stream
        """
        return self._archive.open(str(path), "r")


# Execute the application.

if __name__ == "__main__":
    raise SystemExit(run(main()))
