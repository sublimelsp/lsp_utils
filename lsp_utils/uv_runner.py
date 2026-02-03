from __future__ import annotations
from ._util import download_file, extract_archive
from .helpers import run_command_ex
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import final
import sublime


__all__ = [
    'UvRunner',
]


UV_TAG = '0.9.26'
UV_BINARY = 'uv.exe' if sublime.platform() == 'windows' else 'uv'
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
        raise RuntimeError(f'Unsupported architecture: {sublime_arch}')
    sublime_platform = sublime.platform()
    platform = ARTIFACT_PLATFORM_MAPPING[sublime_platform]
    extension = 'zip' if sublime_platform == 'windows' else 'tar.gz'
    return f'uv-{arch}-{platform}.{extension}'


@final
class UvRunner:
    """
    Runs uv commands through either system-local or self-managed instance of UV.

    Installs self-managed version of uv in Package Storage if system-local version is not available.
    Make sure to initialize an instance on the async thread since it can perform long blocking operations when
    downloading uv.
    """

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._uv: str
        if which('uv'):
            self._uv = 'uv'
        else:
            target_directory = self._storage_path / 'lsp_utils' / 'uv'
            target_version_path = target_directory / 'VERSION'
            target_uv_path = target_directory / UV_BINARY
            if not target_uv_path.exists() or not target_version_path.exists() or \
                    target_version_path.read_text() != UV_TAG:
                filename = get_uv_artifact_name()
                url = ARTIFACT_URL.format(tag=UV_TAG, filename=filename)
                with TemporaryDirectory() as tempdir:
                    archive_path = Path(tempdir, filename)
                    download_file(url, archive_path)
                    source_directory = extract_archive(archive_path, Path(tempdir))
                    target_directory.mkdir(parents=True, exist_ok=True)
                    source_directory.joinpath(UV_BINARY).replace(target_uv_path)
                    target_uv_path.chmod(0o744)
                    target_version_path.write_text(UV_TAG)
            self._uv = str(target_uv_path)

    def run_command(self, *args: str, cwd: str) -> None:
        run_command_ex(self._uv, *args, cwd=cwd)
