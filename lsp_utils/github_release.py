"""
Installation of servers distributed as GitHub release assets.

Combine with :class:`InstallDirectory` so that every release is installed into its own directory.
"""

from __future__ import annotations

from .download import download_to_directory
from .download import http_request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = [
    'download_github_release_asset',
    'fetch_latest_github_release_tag',
]

GITHUB_URL = 'https://github.com'


def fetch_latest_github_release_tag(repo: str) -> str:
    """
    Return the tag of the latest release of a GitHub repository.

    Uses the redirect of the "latest release" page so that it's not subject to the rate limit of the GitHub API.
    Avoid calling it on every start of the server; check for updates periodically instead.

    :param repo: The repository, as `owner/name`.
    """
    with http_request(f'{GITHUB_URL}/{repo}/releases/latest', method='HEAD') as response:
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
    filename: str | None = None,
    sha256: str | None = None,
) -> None:
    """
    Download an asset of a GitHub release into a directory.

    Archives are extracted and gzipped files decompressed, the same as with :func:`download_to_directory`.

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
    :param filename: The file name of the download, which determines how it's handled and what a file that isn't an
                     archive is stored as. Defaults to `asset`.
    :param sha256: The expected SHA-256 hex digest of the asset, verified before it's used.
    """
    download_to_directory(
        f'{GITHUB_URL}/{repo}/releases/download/{tag}/{asset}',
        target_directory,
        filename=filename or asset,
        executables=executables,
        sha256=sha256,
    )
