from __future__ import annotations

from ._install_dirs import INSTALLED_MARKER_FILE
from ._install_dirs import mark_in_use
from ._install_dirs import remove_unused_install_dirs_async
from ._util import download_file
from ._util import extract_archive
from .helpers import run_command_ex
from contextlib import suppress
from LSP.plugin import ST_STORAGE_PATH
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import final
import re
import sublime

__all__ = [
    'UvRunner',
]


UV_TAG = '0.13.0'
UV_BINARY = 'uv.exe' if sublime.platform() == 'windows' else 'uv'
UV_RUNTIME_DIR = Path(ST_STORAGE_PATH) / 'lsp_utils' / 'uv'
ARTIFACT_URL = 'https://github.com/astral-sh/uv/releases/download/{tag}/{filename}'
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
            target_directory = UV_RUNTIME_DIR / UV_TAG
            target_uv_path = target_directory / UV_BINARY
            installed_marker_path = target_directory / INSTALLED_MARKER_FILE
            if not installed_marker_path.is_file():
                filename = get_uv_artifact_name()
                url = ARTIFACT_URL.format(tag=UV_TAG, filename=filename)
                target_directory.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=target_directory) as tempdir:
                    archive_path = Path(tempdir, filename)
                    download_file(url, archive_path)
                    temporary_directory_path = Path(tempdir)
                    extracted_path = extract_archive(archive_path, temporary_directory_path) or temporary_directory_path
                    extracted_path.joinpath(UV_BINARY).replace(target_uv_path)
                    target_uv_path.chmod(0o744)
                    installed_marker_path.touch()
            mark_in_use(target_directory)
            remove_unused_install_dirs_async(UV_RUNTIME_DIR, re.compile(r'\d+\.\d+\.\d+'), keep=target_directory)
            remove_legacy_uv_files()
            self._uv = str(target_uv_path)

    def run_command(self, *args: str, cwd: str) -> None:
        run_command_ex(self._uv, *args, cwd=cwd)
