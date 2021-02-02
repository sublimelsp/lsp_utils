from .helpers import log_and_show_message
from .helpers import parse_version
from .helpers import run_command_sync
from .helpers import SemanticVersion
from .helpers import version_to_string
from .node_distribution import NodeDistribution
from .node_distribution import NodeDistributionPATH
from .node_distribution import NodeDistributionLocal
from .server_resource_interface import ServerResourceInterface
from .server_resource_interface import ServerStatus
from hashlib import md5
from LSP.plugin.core.typing import Dict, Optional
from os import path
from sublime_lib import ResourcePath
import shutil
import sublime

__all__ = ['ServerNpmResource']


class ServerNpmResource(ServerResourceInterface):
    """
    An implementation of :class:`lsp_utils.ServerResourceInterface` implementing server management for
    npm-based severs. Handles installation and updates of the server in package storage.
    """

    @classmethod
    def create(cls, options: Dict) -> Optional['ServerNpmResource']:
        package_name = options['package_name']
        server_directory = options['server_directory']
        server_binary_path = options['server_binary_path']
        package_storage = options['package_storage']
        minimum_node_version = options['minimum_node_version']
        storage_path = options['storage_path']
        node_distribution = cls.resolve_node_distribution(package_name, minimum_node_version, storage_path)
        if node_distribution:
            return ServerNpmResource(
                package_name, server_directory, server_binary_path, package_storage, node_distribution)

    @classmethod
    def resolve_node_distribution(
            cls, package_name: str, minimum_node_version: str, storage_path: str) -> Optional[NodeDistribution]:
        # Try with node on the PATH first.
        node_distribution = NodeDistributionPATH()
        node_version = None
        if node_distribution.node_exists():
            try:
                cls.check_node_version(node_distribution, minimum_node_version)
                return node_distribution
            except Exception as ex:
                message = 'Ignoring Node from PATH due to an error. {}'.format(ex)
                log_and_show_message('{}: Warning: {}'.format(package_name, message))
        # Failed resolving Node on the PATH. Falling back to local Node.
        node_distribution = NodeDistributionLocal(path.join(storage_path, 'lsp_utils', 'node-dist'))
        if not node_distribution.node_exists():
            try:
                node_distribution.install_node()
            except Exception as ex:
                log_and_show_message('{}: Error: Failed installing a local Node:\n{}'.format(package_name, ex))
                return
        if node_distribution.node_exists():
            try:
                cls.check_node_version(node_distribution, minimum_node_version)
                return node_distribution
            except Exception as ex:
                error = 'Ignoring local Node due to an error. {}'.format(ex)
                log_and_show_message('{}: Error: {}'.format(package_name, error))

    @classmethod
    def check_node_version(cls, node_distribution: NodeDistribution, minimum_node_version: str) -> None:
        node_version = node_distribution.resolve_version()
        if node_version < minimum_node_version:
            raise Exception('Node version requirement failed. Expected minimum: {}, got {}.'.format(
                version_to_string(minimum_node_version), version_to_string(node_version)))

    def __init__(self, package_name: str, server_directory: str, server_binary_path: str,
                 package_storage: str, node_distribution: NodeDistribution) -> None:
        if not package_name or not server_directory or not server_binary_path or not node_distribution:
            raise Exception('ServerNpmResource could not initialize due to wrong input')
        self._status = ServerStatus.UNINITIALIZED
        self._package_name = package_name
        self._server_src = 'Packages/{}/{}/'.format(self._package_name, server_directory)
        node_version = version_to_string(node_distribution.resolve_version())
        self._server_dest = path.join(package_storage, node_version, server_directory)
        self._binary_path = path.join(package_storage, node_version, server_binary_path)
        self._node_distribution = node_distribution

    @property
    def server_directory_path(self) -> str:
        return self._server_dest

    @property
    def node_bin(self) -> str:
        node_bin = self._node_distribution.node_bin()
        if node_bin is None:
            raise Exception('Failed to resolve path to the Node distribution')
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
                self._node_distribution.npm_install(self._server_dest)
            except Exception as error:
                self._status = ServerStatus.ERROR
                raise Exception(error)
        self._status = ServerStatus.READY
