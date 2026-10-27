from __future__ import annotations

from ._install_dirs import InstallDirectory
from .github_release import download_and_extract_github_asset
from .helpers import run_command_ex
from contextlib import suppress
from LSP.plugin import ST_STORAGE_PATH
from pathlib import Path
from shutil import which
from typing import final
import sublime

__all__ = [
    'UvRunner',
]


UV_TAG = '0.13.0'
UV_BINARY = 'uv.exe' if sublime.platform() == 'windows' else 'uv'
UV_RUNTIME_DIR = Path(ST_STORAGE_PATH) / 'lsp_utils' / 'uv'
UV_REPO = 'astral-sh/uv'
ARTIFACT_ARCH_MAPPING = {
    'x64': 'x86_64',
    'arm64': 'aarch64',
    'x32': False,
}
ARTIFACT_PLATFORM_MAPPING = {
    'windows': 'pc-windows-msvc',
    'osx': 'apple-darwin',
    'linux': 'unknown-linux-gnu',
}


def get_uv_artifact_name() -> str:
    sublime_arch = sublime.arch()
    arch = ARTIFACT_ARCH_MAPPING[sublime_arch]
    if arch is False:
        msg = f'Unsupported architecture: {sublime_arch}'
        raise RuntimeError(msg)
    sublime_platform = sublime.platform()
    platform = ARTIFACT_PLATFORM_MAPPING[sublime_platform]
    extension = 'zip' if sublime_platform == 'windows' else 'tar.gz'
    return f'uv-{arch}-{platform}.{extension}'


def get_uv_id() -> str:
    """Identify the uv instance that :class:`UvRunner` uses, without installing it."""
    return 'system' if which('uv') else f'managed-{UV_TAG}'


def remove_legacy_uv_files() -> None:
    # Older lsp_utils versions installed uv directly into the runtime directory.
    for legacy_file in (UV_RUNTIME_DIR / UV_BINARY, UV_RUNTIME_DIR / 'VERSION'):
        with suppress(OSError):
            legacy_file.unlink(missing_ok=True)


@final
class UvRunner:
    """
    Runs uv commands through either system-local or self-managed instance of UV.

    Installs self-managed version of uv in Package Storage if system-local version is not available.
    Make sure to initialize an instance on the async thread since it can perform long blocking operations when
    downloading uv.
    """

    def __init__(self) -> None:
        self._uv: str
        if which('uv'):
            self._uv = 'uv'
        else:
            def installer(target_directory: Path) -> None:
                download_and_extract_github_asset(
                    UV_REPO, UV_TAG, get_uv_artifact_name(), target_directory, executables=[UV_BINARY])

            target_directory = InstallDirectory(UV_RUNTIME_DIR, 'uv', UV_TAG).install(installer)
            remove_legacy_uv_files()
            self._uv = str(target_directory / UV_BINARY)

    def run_command(self, *args: str, cwd: str) -> None:
        """Run uv with the given arguments in the `cwd` directory. Raises on failure."""
        run_command_ex(self._uv, *args, cwd=cwd)
