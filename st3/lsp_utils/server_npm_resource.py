from .helpers import log_and_show_message
from .helpers import parse_version
from .helpers import run_command_async
from .helpers import run_command_sync
from .helpers import SemanticVersion
from .helpers import version_to_string
from LSP.plugin.core.typing import Callable, List, Optional, Tuple
from sublime_lib import ActivityIndicator, ResourcePath
import os
import shutil
import sublime


def get_server_npm_resource_for_package(
    package_name: str, server_directory: str, server_binary_path: str, package_storage: str,
    minimum_node_version: SemanticVersion
) -> Optional['ServerNpmResource']:
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


class ServerNpmResource:
    """Global object providing paths to server resources.
    Also handles the installing and updating of the server in cache.

    setup() needs to be called during (or after) plugin_loaded() for paths to be valid.
    """

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

    @property
    def ready(self) -> bool:
        return self._is_ready

    @property
    def error_on_install(self) -> bool:
        return self._error_on_install

    @property
    def binary_path(self) -> str:
        return os.path.join(self._package_storage, self._node_version, self._binary_path)

    @property
    def src_path(self) -> str:
        return 'Packages/{}/{}/'.format(self._package_name, self._server_directory)

    @property
    def dst_path(self) -> str:
        return os.path.join(self._package_storage, self._node_version, self._server_directory)

    def cleanup(self) -> None:
        if os.path.isdir(self._package_storage):
            shutil.rmtree(self._package_storage)

    def needs_installation(self) -> bool:
        if self._initialized:
            return False
        self._initialized = True
        installed = False
        if os.path.isdir(self.dst_path):
            # Server already installed. Check if version has changed.
            try:
                src_package_json = ResourcePath(self.src_path, 'package.json').read_text()
                with open(os.path.join(self.dst_path, 'package.json'), 'r') as file:
                    dst_package_json = file.read()
                if src_package_json == dst_package_json:
                    installed = True
            except FileNotFoundError:
                # Needs to be re-installed.
                pass
        self._is_ready = installed
        return not installed

    def install_or_update(self, async_io: bool) -> None:
        shutil.rmtree(self.dst_path, ignore_errors=True)
        ResourcePath(self.src_path).copytree(self.dst_path, exist_ok=True)
        dependencies_installed = os.path.isdir(os.path.join(self.dst_path, 'node_modules'))
        if dependencies_installed:
            self._is_ready = True
        else:
            self._install_dependencies(self.dst_path, async_io)

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
