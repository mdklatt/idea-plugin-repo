""" Update repository metadata.

"""
from __future__ import annotations

from aiohttp import ClientSession
from asyncio import get_event_loop
from io import BytesIO
from pathlib import Path, PosixPath
from semver import VersionInfo
from tempfile import NamedTemporaryFile
from toml import load
from typing import IO
from xml.etree import ElementTree
from zipfile import ZipFile, Path as ZipPath


__all__ = "main",


async def main() -> int:
    """ Application entry point.

    :return: exit status
    """
    config = load("etc/config.toml")
    repo_config = _RepoConfig(config["repo_config"])
    for plugin in config["plugins"]:
        # TODO: Use async loop.
        release = await _GitHubRelease.get(config["user"], plugin["repo"])
        dist_name = f"{plugin['artifact']}-{release.version}.zip"
        dist_url = release.assets[dist_name]["browser_download_url"]
        dist_jar = await _JarFile.download(dist_url)
        repo_config.update(dist_url, dist_jar)
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
        """ Get a release from the GitHub API

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
    @classmethod
    def _extract(cls, plugin: _JarFile) -> ElementTree:
        """ Extract metadata from plugin JAR file

        :param plugin: distribution JAR
        :return: XML
        """
        root_dir = next(plugin.root.iterdir())  # single root directory
        assert root_dir.is_dir()
        for item in root_dir.joinpath("lib").iterdir():
            # Find plugin library.
            if item.name.startswith(root_dir.name):
                lib = _JarFile(item.open("rb"))
                doc = ElementTree.parse(lib.item("META-INF/plugin.xml"))
                return doc.getroot()
        else:
            raise ValueError("Could not find plugin.xml")

    def __init__(self, path: str | Path):
        """ Initialize an instance from an existing file.

        :param path: input path
        """
        self._xml = ElementTree.parse(path)
        self._plugins = {elem.attrib["id"]: elem for elem in self._xml.getroot()}
        return

    def update(self, url: str, plugin: _JarFile):
        """ Add/replace <plugin> element in file.

        :param url: plugin URL
        :param plugin: plugin info
        """
        meta = self._extract(plugin)
        elem = self._plugins[meta.find("id").text]
        elem.attrib |= {
            "version": meta.find("version").text,
            "url": url,
        }
        elem.find("idea-version").attrib |= meta.find("idea-version").attrib
        return

    def write(self, path: str | Path):
        """ Write XML file.

        :param path: output path
        """
        # Do not replace existing file unless new file is successfully written.
        tmp_file = NamedTemporaryFile("wb", delete=False)
        tmp_path = Path(tmp_file.name)
        try:
            self._xml.write(tmp_file, encoding="utf-8", xml_declaration=True)
            tmp_file.close()
            tmp_path.replace(path)
        except Exception:
            tmp_path.unlink()
            raise
        return


# Execute the application.

if __name__ == "__main__":
    loop = get_event_loop()
    raise SystemExit(loop.run_until_complete(main()))