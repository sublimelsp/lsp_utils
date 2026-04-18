from __future__ import annotations

from .._util import download_file
from .._util import extract_archive
from .._util import logger
from ..constants import HOST_ARCH
from ..constants import INSTALLING_MARKER_FILE
from ..helpers import rmtree_ex
from ..helpers import run_command_sync
from .node_constants import ELECTRON_DIST_URL
from .node_constants import ELECTRON_NODE_VERSION
from .node_constants import ELECTRON_RUNTIME_VERSION
from .node_constants import NODE_DIST_URL
from .node_constants import NODE_RUNTIME_VERSION
from .node_constants import YARN_URL
from pathlib import Path
from typing import final
import sublime


@final
class NodeInstaller:
    """Command to install a local copy of Node.js."""

    def __init__(self, base_dir: Path, node_version: str = NODE_RUNTIME_VERSION) -> None:
        """
        Init NodeInstaller.

        :param base_dir: The base directory for storing given Node.js runtime version
        :param node_version: The Node.js version to install
        """
        self._base_dir = base_dir
        self._node_version = node_version

    def run(self) -> None:
        rmtree_ex(self._base_dir, ignore_errors=True)
        self._base_dir.mkdir(exist_ok=True, parents=True)
        marker_file_path = (self._base_dir / INSTALLING_MARKER_FILE)
        marker_file_path.open('a', encoding='utf-8').close()
        archive_filename, url = self._node_archive()
        logger.info(f'Downloading Node.js {self._node_version} from {url}')
        tmp_dir = self._base_dir / 'tmp'
        tmp_dir.mkdir()
        archive_path = tmp_dir / archive_filename
        download_file(url, archive_path)
        self._install_node(archive_path)
        rmtree_ex(tmp_dir)
        marker_file_path.unlink()

    def _node_archive(self) -> tuple[str, str]:
        platform = sublime.platform()
        arch = HOST_ARCH
        if platform == 'windows':
            node_os = 'win'
            archive = 'zip'
        elif platform == 'linux':
            node_os = 'linux'
            archive = 'tar.gz'
        elif platform == 'osx':
            node_os = 'darwin'
            archive = 'tar.gz'
        else:
            msg = f'{arch} {platform} is not supported'
            raise Exception(msg)
        filename = f'node-v{self._node_version}-{node_os}-{arch}.{archive}'
        dist_url = NODE_DIST_URL.format(version=self._node_version, filename=filename)
        return filename, dist_url

    def _install_node(self, archive_path: Path) -> None:
        temporary_target_path = self._base_dir / 'node-temp'
        extracted_path = extract_archive(archive_path, temporary_target_path) or temporary_target_path
        extracted_path.rename(self._base_dir / 'node')
        rmtree_ex(temporary_target_path, ignore_errors=True)


@final
class ElectronInstaller:
    """Command to install a local copy of Node.js."""

    def __init__(self, base_dir: Path) -> None:
        """:param base_dir: The base directory for storing given Node.js runtime version"""
        self._base_dir = base_dir

    def run(self) -> None:
        rmtree_ex(self._base_dir, ignore_errors=True)
        self._base_dir.mkdir(exist_ok=True, parents=True)
        marker_file_path = (self._base_dir / INSTALLING_MARKER_FILE)
        marker_file_path.open('a', encoding='utf-8').close()
        archive_filename, url = self._node_archive()
        logger.info(
            f'Downloading Electron {ELECTRON_RUNTIME_VERSION} (Node.js runtime {ELECTRON_NODE_VERSION}) from {url}',
        )
        tmp_dir = self._base_dir / 'tmp'
        tmp_dir.mkdir()
        archive_path = tmp_dir / archive_filename
        download_file(url, archive_path)
        self._install(archive_path)
        download_file(YARN_URL, self._base_dir / 'yarn.js')
        rmtree_ex(tmp_dir)
        marker_file_path.unlink()

    def _node_archive(self) -> tuple[str, str]:
        platform = sublime.platform()
        arch = HOST_ARCH
        if platform == 'windows':
            platform_code = 'win32'
        elif platform == 'linux':
            platform_code = 'linux'
        elif platform == 'osx':
            platform_code = 'darwin'
        else:
            msg = f'{arch} {platform} is not supported'
            raise Exception(msg)
        filename = f'electron-v{ELECTRON_RUNTIME_VERSION}-{platform_code}-{arch}.zip'
        dist_url = ELECTRON_DIST_URL.format(version=ELECTRON_RUNTIME_VERSION, filename=filename)
        return filename, dist_url

    def _install(self, archive_path: Path) -> None:
        if sublime.platform() == 'windows':
            extract_archive(archive_path, Path(self._base_dir))
        else:
            # ZipFile doesn't handle symlinks and permissions correctly on Linux and Mac. Use unzip instead.
            _, error = run_command_sync(['unzip', archive_path, '-d', self._base_dir], cwd=archive_path.parent)
            if error:
                msg = f'Error unzipping electron archive: {error}'
                raise Exception(msg)
