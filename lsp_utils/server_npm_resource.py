from __future__ import annotations

from .helpers import rmtree_ex
from .helpers import SemanticVersion
from .node_runtime import NodeRuntime
from .server_resource_interface import ServerResourceInterface
from .server_resource_interface import ServerStatus
from hashlib import md5
from pathlib import Path
from sublime_lib import ResourcePath
from typing import final
from typing import TypedDict
from typing_extensions import override

__all__ = ['ServerNpmResource']


class ServerNpmResourceCreateOptions(TypedDict):
    package_name: str
    server_directory: str
    server_binary_path: str
    package_storage: str
    storage_path: str
    minimum_node_version: SemanticVersion
    required_node_version: str
    skip_npm_install: bool


@final
class ServerNpmResource(ServerResourceInterface):
    """
    Implements server management for node-based severs.

    Handles installation and updates of the server in package storage.
    """

    @classmethod
    def create(cls, options: ServerNpmResourceCreateOptions) -> ServerNpmResource:
        package_name = options['package_name']
        server_directory = options['server_directory']
        server_binary_path = options['server_binary_path']
        package_storage = options['package_storage']
        storage_path = options['storage_path']
        minimum_node_version = options['minimum_node_version']
        required_node_version: str | SemanticVersion = options['required_node_version']
        skip_npm_install = options['skip_npm_install']
        # Fallback to "minimum_node_version" if "required_node_version" is 0.0.0 (not overridden).
        if required_node_version == '0.0.0':
            required_node_version = minimum_node_version
        node_runtime = NodeRuntime.get(package_name, storage_path, required_node_version)
        if not node_runtime:
            msg = 'Failed resolving Node.js Runtime. Please see Sublime Text console for more information.'
            raise Exception(msg)
        return ServerNpmResource(
            package_name, server_directory, server_binary_path, package_storage, node_runtime,
            skip_npm_install=skip_npm_install)

    def __init__(self, package_name: str, server_directory: str, server_binary_path: str,
                 package_storage: str, node_runtime: NodeRuntime, *, skip_npm_install: bool) -> None:
        if not package_name or not server_directory or not server_binary_path or not node_runtime:
            msg = 'ServerNpmResource could not initialize due to wrong input'
            raise Exception(msg)
        self._status = ServerStatus.UNINITIALIZED
        self._package_name = package_name
        self._package_storage = package_storage
        self._server_src = f'Packages/{self._package_name}/{server_directory}/'
        self._server_dest = Path(package_storage, server_directory)
        self._binary_path = Path(package_storage, server_binary_path)
        self._installation_marker_file = Path(package_storage, '.installing')
        self._node_version_marker_file = Path(package_storage, '.node-version')
        self._node_runtime = node_runtime
        self._skip_npm_install = skip_npm_install

    @property
    def server_directory_path(self) -> str:
        return str(self._server_dest)

    @property
    def node_bin(self) -> str:
        node_bin = self._node_runtime.node_bin()
        if node_bin is None:
            msg = 'Failed to resolve path to the Node.js runtime'
            raise Exception(msg)
        return node_bin

    @property
    def node_env(self) -> dict[str, str] | None:
        return self._node_runtime.node_env()

    # --- ServerResourceInterface -------------------------------------------------------------------------------------

    @property
    @override
    def binary_path(self) -> str:
        return str(self._binary_path)

    @override
    def get_status(self) -> int:
        return self._status

    @override
    def needs_installation(self) -> bool:
        installed = False
        if self._skip_npm_install or Path(self._server_dest, 'node_modules').is_dir():
            # Server already installed. Check if version has changed or last installation did not complete.
            src_package_json = ResourcePath(self._server_src, 'package.json')
            if not src_package_json.exists():
                msg = f'Missing required "package.json" in {self._server_src}'
                raise Exception(msg)
            try:
                with self._node_version_marker_file.open(encoding='utf-8') as file:
                    node_version = str(self._node_runtime.resolve_version())
                    stored_node_version = file.read()
                    if node_version != stored_node_version.strip():
                        return True
                src_hash = md5(src_package_json.read_bytes()).hexdigest()  # noqa: S324
                with (self._server_dest / 'package.json').open('rb') as file:
                    dst_hash = md5(file.read()).hexdigest()  # noqa: S324
                if src_hash == dst_hash and not Path(self._installation_marker_file).is_file():
                    installed = True
            except FileNotFoundError:
                # Needs to be re-installed.
                pass
        if installed:
            self._status = ServerStatus.READY
            return False
        return True

    @override
    def install_or_update(self) -> None:
        try:
            if Path(self._package_storage).is_dir():
                rmtree_ex(self._package_storage)
            node_version = str(self._node_runtime.resolve_version())
            Path(self._package_storage).mkdir(exist_ok=True, parents=True)
            self._installation_marker_file.open('w', encoding='utf-8').close()
            ResourcePath(self._server_src).copytree(self._server_dest, exist_ok=True)
            if not self._skip_npm_install:
                self._node_runtime.run_install(cwd=self._server_dest)
            self._node_version_marker_file.write_text(node_version, encoding='utf-8')
            self._installation_marker_file.unlink()
        except Exception as error:
            self._status = ServerStatus.ERROR
            msg = f'Error installing the server:\n{error}'
            raise Exception(msg) from error
        self._status = ServerStatus.READY
