from .helpers import log_and_show_message
from .helpers import parse_version
from .helpers import run_command_async
from .helpers import run_command_sync
from .helpers import SemanticVersion
from .helpers import version_to_string
from .server_resource_interface import ServerResourceInterface
from .server_resource_interface import ServerStatus
from LSP.plugin.core.typing import Dict, Optional
from sublime_lib import ActivityIndicator
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
        self._initialized = False
        self._is_ready = False
        self._error_on_install = False
        self._package_name = package_name
        self._server_directory = server_directory
        self._binary_path = server_binary_path
        self._package_storage = package_storage
        self._node_version = node_version
        self._activity_indicator = None
        if not self._package_name or not self._server_directory or not self._binary_path:
            raise Exception('ServerNpmResource could not initialize due to wrong input')

    # --- ServerResourceInterface -------------------------------------------------------------------------------------

    def get_status(self) -> int:
        if self._is_ready:
            return ServerStatus.READY
        if self._error_on_install:
            return ServerStatus.ERROR
        return ServerStatus.UNINITIALIZED

    @property
    def binary_path(self) -> str:
        return os.path.join(self._package_storage, self._node_version, self._binary_path)

    @property
    def src_path(self) -> str:
        return 'Packages/{}/{}/'.format(self._package_name, self._server_directory)

    @property
    def server_directory_path(self) -> str:
        return os.path.join(self._package_storage, self._node_version, self._server_directory)

    def needs_installation(self) -> bool:
        if self._initialized:
            return False
        self._initialized = True
        installed = False
        if os.path.isdir(self.server_directory_path):
            # Server already installed. Check if version has changed.
            try:
                src_package_json = ResourcePath(self.src_path, 'package.json').read_text()
                with open(os.path.join(self.server_directory_path, 'package.json'), 'r') as file:
                    dst_package_json = file.read()
                if src_package_json == dst_package_json:
                    installed = True
            except FileNotFoundError:
                # Needs to be re-installed.
                pass
        self._is_ready = installed
        return not installed

    def install_or_update_async(self) -> None:
        self._install_or_update(async_io=True)

    def install_or_update_sync(self) -> None:
        self._install_or_update(async_io=False)

    # --- Internal ----------------------------------------------------------------------------------------------------

    def _install_or_update(self, async_io: bool) -> None:
        shutil.rmtree(self.server_directory_path, ignore_errors=True)
        ResourcePath(self.src_path).copytree(self.server_directory_path, exist_ok=True)
        dependencies_installed = os.path.isdir(os.path.join(self.server_directory_path, 'node_modules'))
        if dependencies_installed:
            self._is_ready = True
        else:
            self._install_dependencies(self.server_directory_path, async_io)

    def _install_dependencies(self, server_path: str, async_io: bool) -> None:
        # this will be called only when the plugin gets:
        # - installed for the first time,
        # - or when updated on package control
        install_message = '{}: Installing server in path: {}'.format(self._package_name, server_path)
        log_and_show_message(install_message, show_in_status=False)

        active_window = sublime.active_window()
        if active_window:
            self._activity_indicator = ActivityIndicator(active_window.active_view(), install_message)
            self._activity_indicator.start()

        args = ["npm", "install", "--verbose", "--production", "--prefix", server_path, server_path]
        if async_io:
            run_command_async(args, self._on_install_success, self._on_error)
        else:
            output, error = run_command_sync(args)
            self._on_error(error) if error is not None else self._on_install_success(output)

    def _on_install_success(self, _: str) -> None:
        self._is_ready = True
        self._stop_indicator()
        log_and_show_message(
            '{}: Server installed. Sublime Text restart might be required.'.format(self._package_name))

    def _on_error(self, error: str) -> None:
        self._error_on_install = True
        self._stop_indicator()
        log_and_show_message('{}: Error:'.format(self._package_name), error)

    def _stop_indicator(self) -> None:
        if self._activity_indicator:
            self._activity_indicator.stop()
            self._activity_indicator = None
