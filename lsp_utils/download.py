"""
Installation of servers downloaded from a URL.

Combine with :class:`InstallDirectory` so that every version is installed into its own directory.
"""

from __future__ import annotations

from ._util import extract_archive
from ._util import http_request
from .constants import HOST_ARCH
from hashlib import sha256 as sha256_hash
from pathlib import Path
from posixpath import basename
from sublime_lib import ActivityIndicator
from tempfile import TemporaryDirectory
from typing import cast
from typing import TYPE_CHECKING
from typing import TypedDict
from urllib.parse import unquote
from urllib.parse import urlsplit
import gzip
import shutil
import stat
import sublime

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping

__all__ = [
    'PlatformAssets',
    'UnsupportedPlatformError',
    'download_and_extract',
    'http_request',
    'select_platform_asset',
]

ARCHIVE_SUFFIXES = ('.zip', '.vsix', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')
CHUNK_SIZE = 1024 * 1024


PlatformAssets = TypedDict('PlatformAssets', {
    'linux': str,
    'linux-arm64': str,
    'linux-x32': str,
    'linux-x64': str,
    'osx': str,
    'osx-arm64': str,
    'osx-x64': str,
    'windows': str,
    'windows-arm64': str,
    'windows-x32': str,
    'windows-x64': str,
}, total=False)
"""
Assets (file names or URLs) by `<platform>-<arch>`, for :func:`select_platform_asset`.

A key of just the `<platform>` matches any architecture of that platform.
"""


class UnsupportedPlatformError(RuntimeError):
    """Raised when no asset is available for the current platform and architecture."""


def select_platform_asset(assets: PlatformAssets) -> str:
    """
    Return the asset for the current platform and architecture.

    :param assets: File names or URLs by `<platform>-<arch>` (for example `osx-arm64`). A key of just the `<platform>`
                   matches any architecture of that platform.
    :raises UnsupportedPlatformError: When there is no asset for the current platform and architecture.
    """
    platform = sublime.platform()
    assets_by_key = cast('Mapping[str, str]', assets)
    asset = assets_by_key.get(f'{platform}-{HOST_ARCH}') or assets_by_key.get(platform)
    if not asset:
        msg = f'No asset is available for {platform} ({HOST_ARCH})'
        raise UnsupportedPlatformError(msg)
    return asset


def download_and_extract(
    url: str,
    target_directory: Path,
    *,
    filename: str | None = None,
    executables: Iterable[str] = (),
    sha256: str | None = None,
) -> None:
    """
    Download a file into a directory, extracting or decompressing it depending on its file name.

    - An archive (`.zip`, `.vsix`, `.tar.gz`, `.tgz`, `.tar.bz2` or `.tar.xz`) is extracted. When all its files are
      in a single root directory, the contents of that directory are extracted.
    - A file compressed with gzip (`.gz`) is decompressed and stored under `filename` without the `.gz` extension.
    - Any other file is stored as is under `filename`.

    An activity indicator is shown in the status bar of the active window in the meantime.

    Typically called as the installer of an :class:`InstallDirectory`:

    .. code:: py

        VERSION = '1.2.3'
        URL = f'https://example.com/server/{VERSION}/server-{sublime.platform()}.zip'

        install_dir = InstallDirectory(storage_path, 'server', VERSION)
        install_dir.install(lambda path: download_and_extract(URL, path, executables=['bin/server']))

    For GitHub releases, see :func:`download_and_extract_github_asset`.

    :param url: The URL to download.
    :param target_directory: The existing directory to store the file or its extracted contents in.
    :param filename: The file name of the download, which determines how it's handled and what a file that isn't an
                     archive is stored as. Defaults to the last segment of the URL path. For example, pass
                     `server.gz` to store a gzipped download as `server`.
    :param executables: Paths, relative to `target_directory`, of files to make executable once downloaded. Zip
                        archives don't preserve the executable permission, for example.
    :param sha256: The expected SHA-256 hex digest of the download, verified before it's used.
    """
    filename = filename or basename(unquote(urlsplit(url).path))
    if not filename:
        msg = f'Failed determining the file name of "{url}"'
        raise ValueError(msg)
    indicator = ActivityIndicator(sublime.active_window(), f'[LSP] Downloading {filename}')
    with indicator, TemporaryDirectory(dir=target_directory) as tempdir:
        download_path = Path(tempdir, filename)
        digest = sha256_hash()
        with http_request(url) as response, download_path.open('wb') as out_file:
            while chunk := response.read(CHUNK_SIZE):
                digest.update(chunk)
                out_file.write(chunk)
        if sha256 and digest.hexdigest().lower() != sha256.lower():
            msg = f'Checksum mismatch of "{url}": expected {sha256}, got {digest.hexdigest()}'
            raise RuntimeError(msg)
        if filename.endswith(ARCHIVE_SUFFIXES):
            extract_directory = Path(tempdir, 'extracted')
            extract_directory.mkdir()
            root = extract_archive(download_path, extract_directory) or extract_directory
            for path in root.iterdir():
                path.replace(target_directory / path.name)
        elif filename.endswith('.gz'):
            with gzip.open(download_path) as source, (target_directory / filename[:-3]).open('wb') as out:
                shutil.copyfileobj(source, out)
        else:
            download_path.replace(target_directory / filename)
    if sublime.platform() != 'windows':
        for executable in executables:
            path = target_directory / executable
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
