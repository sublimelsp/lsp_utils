from .helpers import log_and_show_message
from .helpers import SemanticVersion
from .helpers import version_to_string
from .node_runtime import NodeRuntime
from .node_runtime import NodeRuntimeLocal
from .node_runtime import NodeRuntimePATH
from .server_resource_interface import ServerResourceInterface
from .server_resource_interface import ServerStatus
from hashlib import md5
from LSP.plugin.core.typing import Dict, Optional
from os import path
from sublime_lib import ResourcePath
import shutil
import sublime

__all__ = ['ServerNpmResource']

NO_NODE_FOUND_MESSAGE = 'Could not start {package_name} due to not being able to find Node.js \
runtime on the PATH. Press the "Install Node.js" button to install Node.js automatically \
(note that it will be installed locally for LSP and will not affect your system otherwise).'


class ServerNpmResource(ServerResourceInterface):
    """
    An implementation of :class:`lsp_utils.ServerResourceInterface` implementing server management for
    node-based severs. Handles installation and updates of the server in package storage.
    """

    _node_runtime_resolved = False
    _node_runtime = None  # Optional[NodeRuntime]
    """
    Cached instance of resolved Node.js runtime. This is only done once per-session to avoid unnecessary IO.
    """

    @classmethod
    def create(cls, options: Dict) -> Optional['ServerNpmResource']:
        package_name = options['package_name']
        server_directory = options['server_directory']
        server_binary_path = options['server_binary_path']
        package_storage = options['package_storage']
        minimum_node_version = options['minimum_node_version']
        storage_path = options['storage_path']
        if not cls._node_runtime_resolved:
            cls._node_runtime = cls.resolve_node_runtime(package_name, minimum_node_version, storage_path)
            cls._node_runtime_resolved = True
        if cls._node_runtime:
            return ServerNpmResource(
                package_name, server_directory, server_binary_path, package_storage, cls._node_runtime)

    @classmethod
    def resolve_node_runtime(
        cls, package_name: str, minimum_node_version: SemanticVersion, storage_path: str
    ) -> Optional[NodeRuntime]:
        selected_runtimes = sublime.load_settings('lsp_utils.sublime-settings').get('nodejs_runtime')
        for runtime in selected_runtimes:
            if runtime == 'system':
                node_runtime = NodeRuntimePATH()
                if node_runtime.node_exists():
                    try:
                        cls.check_node_version(node_runtime, minimum_node_version)
                        return node_runtime
                    except Exception as ex:
                        message = 'Ignoring system Node.js runtime due to an error. {}'.format(ex)
                        log_and_show_message('{}: Error: {}'.format(package_name, message))
            elif runtime == 'local':
                node_runtime = NodeRuntimeLocal(path.join(storage_path, 'lsp_utils', 'node-runtime'))
                if not node_runtime.node_exists():
                    if not sublime.ok_cancel_dialog(NO_NODE_FOUND_MESSAGE.format(package_name=package_name),
                                                    'Install Node.js'):
                        return
                    try:
                        node_runtime.install_node()
                    except Exception as ex:
                        log_and_show_message('{}: Error: Failed installing a local Node.js runtime:\n{}'.format(
                            package_name, ex))
                        return
                if node_runtime.node_exists():
                    try:
                        cls.check_node_version(node_runtime, minimum_node_version)
                        return node_runtime
                    except Exception as ex:
                        error = 'Ignoring local Node.js runtime due to an error. {}'.format(ex)
                        log_and_show_message('{}: Error: {}'.format(package_name, error))

    @classmethod
    def check_node_version(cls, node_runtime: NodeRuntime, minimum_node_version: SemanticVersion) -> None:
        node_version = node_runtime.resolve_version()
        if node_version < minimum_node_version:
            raise Exception('Node.js version requirement failed. Expected minimum: {}, got {}.'.format(
                version_to_string(minimum_node_version), version_to_string(node_version)))

    def __init__(self, package_name: str, server_directory: str, server_binary_path: str,
                 package_storage: str, node_runtime: NodeRuntime) -> None:
        if not package_name or not server_directory or not server_binary_path or not node_runtime:
            raise Exception('ServerNpmResource could not initialize due to wrong input')
        self._status = ServerStatus.UNINITIALIZED
        self._package_name = package_name
        self._server_src = 'Packages/{}/{}/'.format(self._package_name, server_directory)
        node_version = version_to_string(node_runtime.resolve_version())
        self._server_dest = path.join(package_storage, node_version, server_directory)
        self._binary_path = path.join(package_storage, node_version, server_binary_path)
        self._node_runtime = node_runtime

    @property
    def server_directory_path(self) -> str:
        return self._server_dest

    @property
    def node_bin(self) -> str:
        node_bin = self._node_runtime.node_bin()
        if node_bin is None:
            raise Exception('Failed to resolve path to the Node.js runtime')
        return node_bin

    # --- ServerResourceInterface -------------------------------------------------------------------------------------

    @property
    def binary_path(self) -> str:
        return self._binary_path

    def get_status(self) -> int:
        return self._status

    def needs_installation(self) -> bool:
        installed = False
        if path.isdir(path.join(self._server_dest, 'node_modules')):
            # Server already installed. Check if version has changed.
            try:
                src_hash = md5(ResourcePath(self._server_src, 'package.json').read_bytes()).hexdigest()
                with open(path.join(self._server_dest, 'package.json'), 'rb') as file:
                    dst_hash = md5(file.read()).hexdigest()
                if src_hash == dst_hash:
                    installed = True
            except FileNotFoundError:
                # Needs to be re-installed.
                pass
        if installed:
            self._status = ServerStatus.READY
            return False
        return True

    def install_or_update(self) -> None:
        shutil.rmtree(self._server_dest, ignore_errors=True)
        ResourcePath(self._server_src).copytree(self._server_dest, exist_ok=True)
        dependencies_installed = path.isdir(path.join(self._server_dest, 'node_modules'))
        if not dependencies_installed:
            try:
                self._node_runtime.npm_install(self._server_dest)
            except Exception as error:
                self._status = ServerStatus.ERROR
                raise Exception(error)
        self._status = ServerStatus.READY
