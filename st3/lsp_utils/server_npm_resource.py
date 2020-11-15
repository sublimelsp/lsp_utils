from .helpers import log_and_show_message
from .helpers import parse_version
from .helpers import run_command_sync
from .helpers import SemanticVersion
from .helpers import version_to_string
from .server_resource_interface import ServerResourceInterface
from .server_resource_interface import ServerStatus
from hashlib import md5
from LSP.plugin.core.typing import Dict, Optional
from sublime_lib import ResourcePath
import os
import shutil
import sublime

__all__ = ['ServerNpmResource']


class NodeVersionResolver:
    """
    A singleton for resolving Node version once per session.
    """

    def __init__(self) -> None:
        self._version = None  # type: Optional[SemanticVersion]

    def resolve(self) -> Optional[SemanticVersion]:
        if self._version:
            return self._version
        version, error = run_command_sync(['node', '--version'])
        if error is not None:
            log_and_show_message('lsp_utils(NodeVersionResolver): Error resolving node version: {}!'.format(error))
        else:
            self._version = parse_version(version)
        return self._version


node_version_resolver = NodeVersionResolver()


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
        if shutil.which('node') is None:
            log_and_show_message(
                '{}: Error: Node binary not found on the PATH.'
                'Check the LSP Troubleshooting section for information on how to fix that: '
                'https://lsp.readthedocs.io/en/latest/troubleshooting/'.format(package_name))
            return None
        installed_node_version = node_version_resolver.resolve()
        if not installed_node_version:
            return None
        if installed_node_version < minimum_node_version:
            error = 'Installed node version ({}) is lower than required version ({})'.format(
                version_to_string(installed_node_version), version_to_string(minimum_node_version))
            log_and_show_message('{}: Error:'.format(package_name), error)
            return None
        return ServerNpmResource(package_name, server_directory, server_binary_path, package_storage,
                                 version_to_string(installed_node_version))

    def __init__(self, package_name: str, server_directory: str, server_binary_path: str,
                 package_storage: str, node_version: str) -> None:
        if not package_name or not server_directory or not server_binary_path:
            raise Exception('ServerNpmResource could not initialize due to wrong input')
        self._status = ServerStatus.UNINITIALIZED
        self._package_name = package_name
        self._server_src = 'Packages/{}/{}/'.format(self._package_name, server_directory)
        self._server_dest = os.path.join(package_storage, node_version, server_directory)
        self._binary_path = os.path.join(package_storage, node_version, server_binary_path)

    @property
    def server_directory_path(self) -> str:
        return self._server_dest

    # --- ServerResourceInterface -------------------------------------------------------------------------------------

    @property
    def binary_path(self) -> str:
        return self._binary_path

    def get_status(self) -> int:
        return self._status

    def needs_installation(self) -> bool:
        installed = False
        if os.path.isdir(self._server_dest):
            # Server already installed. Check if version has changed.
            try:
                src_hash = md5(ResourcePath(self._server_src, 'package.json').read_bytes()).hexdigest()
                with open(os.path.join(self._server_dest, 'package.json'), 'rb') as file:
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
        dependencies_installed = os.path.isdir(os.path.join(self._server_dest, 'node_modules'))
        if dependencies_installed:
            self._status = ServerStatus.READY
        else:
            args = ["npm", "install", "--verbose", "--production", "--prefix", self._server_dest, self._server_dest]
            output, error = run_command_sync(args)
            if error is not None:
                self._status = ServerStatus.ERROR
                raise Exception(error)
            else:
                self._status = ServerStatus.READY
