"""
Installation of servers distributed as GitHub release assets.

Combine with :class:`InstallDirectory` so that every release is installed into its own directory.
"""

from __future__ import annotations

from ._util import extract_archive
from .constants import HOST_ARCH
from hashlib import sha256 as sha256_hash
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from typing import TYPE_CHECKING
from typing import TypedDict
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
    'download_github_release_asset',
    'get_latest_github_release_tag',
    'select_platform_asset',
]

GITHUB_URL = 'https://github.com'
USER_AGENT = 'Sublime Text lsp_utils'
TIMEOUT = 60
ARCHIVE_SUFFIXES = ('.zip', '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz')
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
Release assets by `<platform>-<arch>`, for :func:`select_platform_asset`.

A key of just the `<platform>` matches any architecture of that platform.
"""


class UnsupportedPlatformError(RuntimeError):
    """Raised when no release asset is available for the current platform and architecture."""


def select_platform_asset(assets: PlatformAssets) -> str:
    """
    Return the release asset for the current platform and architecture.

    :param assets: The names of the assets by `<platform>-<arch>` (for example `osx-arm64`). A key of just the
                   `<platform>` matches any architecture of that platform.
    :raises UnsupportedPlatformError: When there is no asset for the current platform and architecture.
    """
    platform = sublime.platform()
    assets_by_key = cast('Mapping[str, str]', assets)
    asset = assets_by_key.get(f'{platform}-{HOST_ARCH}') or assets_by_key.get(platform)
    if not asset:
        msg = f'No release asset is available for {platform} ({HOST_ARCH})'
        raise UnsupportedPlatformError(msg)
    return asset


def get_latest_github_release_tag(repo: str) -> str:
    """
    Return the tag of the latest release of a GitHub repository.

    Uses the redirect of the "latest release" page so that it's not subject to the rate limit of the GitHub API.
    Avoid calling it on every start of the server; check for updates periodically instead.

    :param repo: The repository, as `owner/name`.
    """
    with _open_url(f'{GITHUB_URL}/{repo}/releases/latest', method='HEAD') as response:
        url = response.geturl()
    _, separator, tag = url.rstrip('/').rpartition('/releases/tag/')
    if not separator or not tag:
        msg = f'Failed resolving the latest release of "{repo}"'
        raise RuntimeError(msg)
    return tag


def download_github_release_asset(
    repo: str,
    tag: str,
    asset: str,
    target_directory: Path,
    *,
    executables: Iterable[str] = (),
    sha256: str | None = None,
    save_as: str | None = None,
) -> None:
    """
    Download an asset of a GitHub release into a directory.

    - An archive (`.zip`, `.tar.gz`, `.tgz`, `.tar.bz2` or `.tar.xz`) is extracted. When all its files are in a single
      root directory, the contents of that directory are extracted.
    - A file compressed with gzip (`.gz`) is decompressed, dropping the `.gz` extension from its name.
    - Any other file is stored as is.

    Typically called as the installer of an :class:`InstallDirectory`:

    .. code:: py

        TAG = 'v1.2.3'
        ASSETS: PlatformAssets = {
            'linux-x64': 'server-x86_64-unknown-linux-gnu.tar.gz',
            'osx-arm64': 'server-aarch64-apple-darwin.tar.gz',
            'windows-x64': 'server-x86_64-pc-windows-msvc.zip',
        }
        BINARY = 'server.exe' if sublime.platform() == 'windows' else 'server'

        install_dir = InstallDirectory(storage_path, 'server', TAG)
        if install_dir.needs_installation():
            install_dir.install(lambda path: download_github_release_asset(
                'owner/server', TAG, select_platform_asset(ASSETS), path, executables=[BINARY]))
        binary_path = install_dir.path / BINARY

    :param repo: The repository, as `owner/name`.
    :param tag: The tag of the release.
    :param asset: The file name of the asset.
    :param target_directory: The existing directory to store the asset or its extracted contents in.
    :param executables: Paths, relative to `target_directory`, of files to make executable once downloaded. Zip
                        archives don't preserve the executable permission, for example.
    :param sha256: The expected SHA-256 hex digest of the asset, verified before it's used.
    :param save_as: The file name to store a file that isn't an archive under, instead of the asset name (without the
                    `.gz` extension).
    """
    is_archive = asset.endswith(ARCHIVE_SUFFIXES)
    if save_as and is_archive:
        msg = '"save_as" is not supported for archives'
        raise ValueError(msg)
    url = f'{GITHUB_URL}/{repo}/releases/download/{tag}/{asset}'
    with TemporaryDirectory(dir=target_directory) as tempdir:
        download_path = Path(tempdir, asset)
        digest = sha256_hash()
        with _open_url(url) as response, download_path.open('wb') as out_file:
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
        elif asset.endswith('.gz'):
            with gzip.open(download_path) as source, (target_directory / (save_as or asset[:-3])).open('wb') as out:
                shutil.copyfileobj(source, out)
        else:
            download_path.replace(target_directory / (save_as or asset))
    if sublime.platform() != 'windows':
        for executable in executables:
            path = target_directory / executable
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _open_url(url: str, *, method: str = 'GET') -> HTTPResponse:
    request = Request(url, headers={'User-Agent': USER_AGENT}, method=method)  # ruff: ignore[suspicious-url-open-usage]
    return urlopen(request, timeout=TIMEOUT)  # ruff: ignore[suspicious-url-open-usage]
