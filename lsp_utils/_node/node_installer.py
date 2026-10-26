from __future__ import annotations

from .._util import download_file
from .._util import extract_archive
from .._util import logger
from ..constants import HOST_ARCH
from ..constants import INSTALLING_MARKER_FILE
from ..helpers import rmtree_ex
from .node_constants import NODE_DIST_URL
from .node_constants import NODE_RUNTIME_VERSION
from .node_constants import OBSOLETE_NODE_RUNTIME_VERSIONS
from typing import final
from typing import TYPE_CHECKING
import sublime
import threading

if TYPE_CHECKING:
    from pathlib import Path

_obsolete_runtimes_removed = False


def remove_obsolete_node_runtimes(runtime_dir: Path) -> None:
    """Remove Node.js runtimes installed by previous lsp_utils releases. Runs in the background once per session."""
    global _obsolete_runtimes_removed  # noqa: PLW0603
    if _obsolete_runtimes_removed:
        return
    _obsolete_runtimes_removed = True
    obsolete_dirs = [runtime_dir / version for version in OBSOLETE_NODE_RUNTIME_VERSIONS]
    obsolete_dirs = [path for path in obsolete_dirs if path.is_dir()]
    if not obsolete_dirs:
        return

    def remove() -> None:
        for version_dir in obsolete_dirs:
            logger.info(f'Removing obsolete Node.js runtime: {version_dir}')
            rmtree_ex(version_dir, ignore_errors=True)

    threading.Thread(target=remove, daemon=True).start()


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
