"""
Installation of servers downloaded from a URL.

Combine with :class:`InstallDirectory` so that every version is installed into its own directory.
"""

from __future__ import annotations

from ._util import extract_archive
from .constants import HOST_ARCH
from hashlib import sha256 as sha256_hash
from pathlib import Path
from posixpath import basename
from tempfile import TemporaryDirectory
from typing import cast
from typing import TYPE_CHECKING
from typing import TypedDict
from urllib.parse import unquote
from urllib.parse import urlsplit
from urllib.request import Request
from urllib.request import urlopen
import gzip
import shutil
import stat
import sublime

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Mapping
    from http.client import HTTPResponse

__all__ = [
    'PlatformAssets',
    'UnsupportedPlatformError',
    'download_to_directory',
    'open_url',
    'select_platform_asset',
]

USER_AGENT = 'Sublime Text lsp_utils'
TIMEOUT = 60
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
File names or URLs of downloads by `<platform>-<arch>`, for :func:`select_platform_asset`.

A key of just the `<platform>` matches any architecture of that platform.
"""


class UnsupportedPlatformError(RuntimeError):
    """Raised when no download is available for the current platform and architecture."""


def select_platform_asset(assets: PlatformAssets) -> str:
    """
    Return the download for the current platform and architecture.

    :param assets: File names or URLs by `<platform>-<arch>` (for example `osx-arm64`). A key of just the `<platform>`
                   matches any architecture of that platform.
    :raises UnsupportedPlatformError: When there is no download for the current platform and architecture.
    """
    platform = sublime.platform()
    assets_by_key = cast('Mapping[str, str]', assets)
    asset = assets_by_key.get(f'{platform}-{HOST_ARCH}') or assets_by_key.get(platform)
    if not asset:
        msg = f'No download is available for {platform} ({HOST_ARCH})'
        raise UnsupportedPlatformError(msg)
    return asset


def open_url(url: str, *, method: str = 'GET') -> HTTPResponse:
    """Open a URL with the User-Agent of lsp_utils and a timeout. Use as a context manager."""
    request = Request(url, headers={'User-Agent': USER_AGENT}, method=method)  # ruff: ignore[suspicious-url-open-usage]
    return urlopen(request, timeout=TIMEOUT)  # ruff: ignore[suspicious-url-open-usage]


def download_to_directory(
    url: str,
    target_directory: Path,
    *,
    filename: str | None = None,
    executables: Iterable[str] = (),
    sha256: str | None = None,
    save_as: str | None = None,
) -> None:
    """
    Download a file into a directory, extracting or decompressing it depending on its file name.

    - An archive (`.zip`, `.vsix`, `.tar.gz`, `.tgz`, `.tar.bz2` or `.tar.xz`) is extracted. When all its files are
      in a single root directory, the contents of that directory are extracted.
    - A file compressed with gzip (`.gz`) is decompressed, dropping the `.gz` extension from its name.
    - Any other file is stored as is.

    Typically called as the installer of an :class:`InstallDirectory`:

    .. code:: py

        VERSION = '1.2.3'
        URL = f'https://example.com/server/{VERSION}/server-{sublime.platform()}.zip'

        install_dir = InstallDirectory(storage_path, 'server', VERSION)
        if install_dir.needs_installation():
            install_dir.install(lambda path: download_to_directory(URL, path, executables=['bin/server']))

    For GitHub releases, see :func:`download_github_release_asset`.

    :param url: The URL to download.
    :param target_directory: The existing directory to store the file or its extracted contents in.
    :param filename: The file name of the download, which determines how it's handled. Defaults to the last segment
                     of the URL path.
    :param executables: Paths, relative to `target_directory`, of files to make executable once downloaded. Zip
                        archives don't preserve the executable permission, for example.
    :param sha256: The expected SHA-256 hex digest of the download, verified before it's used.
    :param save_as: The file name to store a file that isn't an archive under, instead of `filename` (without the
                    `.gz` extension).
    """
    filename = filename or basename(unquote(urlsplit(url).path))
    if not filename:
        msg = f'Failed determining the file name of "{url}"'
        raise ValueError(msg)
    is_archive = filename.endswith(ARCHIVE_SUFFIXES)
    if save_as and is_archive:
        msg = '"save_as" is not supported for archives'
        raise ValueError(msg)
    with TemporaryDirectory(dir=target_directory) as tempdir:
        download_path = Path(tempdir, filename)
        digest = sha256_hash()
        with open_url(url) as response, download_path.open('wb') as out_file:
            while chunk := response.read(CHUNK_SIZE):
                digest.update(chunk)
                out_file.write(chunk)
        if sha256 and digest.hexdigest().lower() != sha256.lower():
            msg = f'Checksum mismatch of "{url}": expected {sha256}, got {digest.hexdigest()}'
            raise RuntimeError(msg)
        if is_archive:
            extract_directory = Path(tempdir, 'extracted')
            extract_directory.mkdir()
            root = extract_archive(download_path, extract_directory) or extract_directory
            for path in root.iterdir():
                path.replace(target_directory / path.name)
        elif filename.endswith('.gz'):
            with gzip.open(download_path) as source, (target_directory / (save_as or filename[:-3])).open('wb') as out:
                shutil.copyfileobj(source, out)
        else:
            download_path.replace(target_directory / (save_as or filename))
    if sublime.platform() != 'windows':
        for executable in executables:
            path = target_directory / executable
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
