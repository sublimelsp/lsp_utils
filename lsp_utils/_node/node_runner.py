from __future__ import annotations

from .._util import logger
from ..constants import INSTALLING_MARKER_FILE
from ..helpers import rmtree_ex
from ..helpers import run_command_sync
from ..helpers import start_process
from ..third_party.semantic_version import NpmSpec  # pyright: ignore[reportPrivateLocalImportUsage]
from ..third_party.semantic_version import Version  # pyright: ignore[reportPrivateLocalImportUsage]
from .node_constants import NODE_RUNTIME_VERSION
from .node_installer import NodeInstaller
from hashlib import md5
from pathlib import Path
from sublime_lib import ActivityIndicator
from typing import Any
from typing import final
from typing import TYPE_CHECKING
from typing_extensions import override
import shutil
import sublime
import subprocess  # noqa: S404
import sys

if TYPE_CHECKING:
    from os import PathLike
    from sublime_lib import ResourcePath


IS_WINDOWS_7_OR_LOWER = sys.platform == 'win32' and sys.getwindowsversion()[:2] <= (6, 1)
NODE_VERSION_MARKER_FILE = '.node-version'


class NodeNotInitializedError(Exception):
    pass


class NodeRunner:

    def __init__(self) -> None:
        self._node: Path | None = None
        self._npm: Path | None = None
        self._version: Version | None = None
        self._additional_paths: list[str] = []

    @override
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(node: {self._node}, npm: {self._npm}, version: {self._version or None})'

    def install_node(self) -> None:
        msg = 'Not supported!'
        raise Exception(msg)

    def node_binary_path(self) -> Path:
        if not self._node:
            raise NodeNotInitializedError
        return self._node

    def node_env(self) -> dict[str, str]:
        if IS_WINDOWS_7_OR_LOWER:
            return {'NODE_SKIP_PLATFORM_CHECK': '1'}
        return {}

    def check_binary_present(self) -> None:
        if self._node is None:
            msg = '"node" binary not found'
            raise NodeNotInitializedError(msg)
        if self._npm is None:
            msg = '"npm" binary not found'
            raise NodeNotInitializedError(msg)

    def check_satisfies_version(self, required_node_version: NpmSpec) -> None:
        node_version = self.resolve_version()
        if node_version not in required_node_version:
            msg = f'Node.js version requirement failed. Expected {required_node_version}, got {node_version}.'
            raise Exception(msg)

    def resolve_version(self) -> Version:
        if self._version:
            return self._version
        if not self._node:
            raise NodeNotInitializedError
        # In this case we have fully resolved binary path already so shouldn't need `shell` on Windows.
        version, error = run_command_sync([self._node, '--version'], extra_env=self.node_env(), shell=False)
        if error is None:
            self._version = Version(version.replace('v', ''))
        else:
            msg = f'Failed resolving Node.js version. Error:\n{error}'
            raise Exception(msg)
        return self._version

    def run_node(
        self,
        args: list[str | PathLike[str]],
        stdin: int = subprocess.PIPE,
        stdout: int = subprocess.PIPE,
        stderr: int = subprocess.PIPE,
        env: dict[str, Any] | None = None,
    ) -> subprocess.Popen[bytes]:
        if not self._node:
            raise NodeNotInitializedError
        if env is None:
            env = {}
        env.update(self.node_env())
        return start_process([self._node, *args], stdin=stdin, stdout=stdout, stderr=stderr, extra_env=env)

    def run_install(self, cwd: str | PathLike[str]) -> None:
        if not Path(cwd).is_dir():
            msg = f'Specified working directory "{cwd}" does not exist'
            raise Exception(msg)
        if not self._node:
            msg = 'Node.js not installed. Use NodeInstaller to install it first.'
            raise NodeNotInitializedError(msg)
        args = [
            'ci',
            '--omit=dev',
            '--verbose',
        ]
        stdout, error = run_command_sync(
            [*self.npm_command(), *args], cwd=cwd, extra_env=self.node_env(), extra_paths=self._additional_paths,
            shell=False,
        )
        logger.info('START output of command: "{}"'.format(' '.join(args)))
        logger.info(stdout)
        logger.info('Command output END')
        if error is not None:
            msg = 'Failed to run npm command "{}":\n{}'.format(' '.join(args), error)
            raise Exception(msg)

    def npm_command(self) -> list[Path]:
        if self._npm is None:
            msg = 'Npm binary not initialized'
            raise NodeNotInitializedError(msg)
        return [self._npm]

    def install_project_dependencies(self, source_path: ResourcePath, target_path: Path) -> None:
        if self._are_project_dependencies_installed(source_path, target_path):
            return
        try:
            if target_path.is_dir():
                rmtree_ex(target_path)
            node_version = str(self.resolve_version())
            target_path.mkdir(exist_ok=True, parents=True)
            (target_path / INSTALLING_MARKER_FILE).open('w', encoding='utf-8').close()
            source_path.copytree(target_path, exist_ok=True)
            self.run_install(cwd=target_path)
            (target_path / NODE_VERSION_MARKER_FILE).write_text(node_version, encoding='utf-8')
            (target_path / INSTALLING_MARKER_FILE).unlink()
        except Exception as error:
            msg = f'Error installing the server:\n{error}'
            raise Exception(msg) from error

    def _are_project_dependencies_installed(self, source_path: ResourcePath, target_path: Path) -> bool:
        if not (target_path / 'node_modules').is_dir():
            return False
        # Server already installed. Check if version has changed or last installation did not complete.
        src_package_json = source_path / 'package.json'
        if not src_package_json.exists():
            msg = f'Missing required "package.json" in {source_path}'
            raise Exception(msg)
        if (target_path / INSTALLING_MARKER_FILE).is_file():
            # Detected installation that was not completed.
            return False
        try:
            node_version = str(self.resolve_version())
            stored_node_version = (target_path / NODE_VERSION_MARKER_FILE).read_text(encoding='utf-8').strip()
            if node_version != stored_node_version:
                return False
            dst_package_json = target_path / 'package.json'
            src_hash = md5(src_package_json.read_bytes()).hexdigest()  # noqa: S324
            dst_hash = md5(dst_package_json.read_bytes()).hexdigest()  # noqa: S324
            if src_hash != dst_hash:
                return False
        except FileNotFoundError:
            return False
        return True


@final
class NodeRunnerPath(NodeRunner):
    def __init__(self) -> None:
        super().__init__()
        node = shutil.which('node')
        npm = shutil.which('npm')
        self._node = Path(node) if node else None
        self._npm = Path(npm) if npm else None


@final
class NodeRunnerLocal(NodeRunner):

    def __init__(self, base_dir: Path, node_version: str = NODE_RUNTIME_VERSION) -> None:
        super().__init__()
        self._base_dir = (base_dir / node_version).resolve()
        self._node_version = node_version
        self._node_dir = self._base_dir / 'node'
        self._resolve_paths()

    # --- NodeRunner overrides ---------------------------------------------------------------------------------------

    @override
    def npm_command(self) -> list[Path]:
        if not self._node or not self._npm:
            msg = 'Node.js or Npm command not initialized'
            raise NodeNotInitializedError(msg)
        return [self._node, self._npm]

    @override
    def install_node(self) -> None:
        with ActivityIndicator(sublime.active_window(), '[LSP] Setting up local Node.js'):
            install_node = NodeInstaller(self._base_dir, self._node_version)
            install_node.run()
        self._resolve_paths()

    # --- private methods ----------------------------------------------------------------------------------------------

    def _resolve_paths(self) -> None:
        self._node = self._resolve_binary()
        node_lib = self._resolve_lib()
        self._npm = node_lib / 'npm' / 'bin' / 'npm-cli.js'
        self._additional_paths = [str(self._node.parent)] if self._node else []

    def _resolve_binary(self) -> Path | None:
        exe_path = self._node_dir / 'node.exe'
        binary_path = self._node_dir / 'bin' / 'node'
        if exe_path.is_file():
            return exe_path
        if binary_path.is_file():
            return binary_path
        return None

    def _resolve_lib(self) -> Path:
        lib_path = self._node_dir / 'lib' / 'node_modules'
        if not lib_path.is_dir():
            lib_path = self._node_dir / 'node_modules'
        return lib_path
