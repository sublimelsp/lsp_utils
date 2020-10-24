from LSP.plugin.core.typing import Callable, List, Optional, Tuple
from sublime_lib import ActivityIndicator, ResourcePath
import os
import re
import shutil
import sublime
import subprocess
import threading

StringCallback = Callable[[str], None]
SemanticVersion = Tuple[int, int, int]


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


def run_command(on_success: StringCallback, on_error: StringCallback, popen_args) -> None:
    """
    Runs the given args in a subprocess.Popen, and then calls the function
    on_success when the subprocess completes.
    on_success is a callable object, and popen_args is a list/tuple of args that
    on_error when the subprocess throws an error
    would give to subprocess.Popen.
    """

    def execute(on_success, on_error, popen_args):
        try:
            output = subprocess.check_output(popen_args, shell=sublime.platform() == 'windows',
                                             stderr=subprocess.STDOUT)
            on_success(decode_bytes(output).strip())
        except subprocess.CalledProcessError as error:
            on_error(decode_bytes(error.output).strip())

    thread = threading.Thread(target=execute, args=(on_success, on_error, popen_args))
    thread.start()


def decode_bytes(data: bytes) -> str:
    return data.decode('utf-8', 'ignore')


def parse_version(version: str) -> SemanticVersion:
    """Convert filename to version tuple (major, minor, patch)."""
    match = re.match(r'v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-.+)?', version)
    if match:
        major, minor, patch = match.groups()
        return int(major), int(minor), int(patch)
    else:
        return 0, 0, 0


def version_to_string(version: SemanticVersion) -> str:
    return '.'.join([str(c) for c in version])


def log_and_show_message(msg, additional_logs: str = None, show_in_status: bool = True) -> None:
    print(msg, '\n', additional_logs) if additional_logs else print(msg)
    if show_in_status:
        sublime.active_window().status_message(msg)


class NodeVersionResolver:
    """
    A singleton for resolving Node version once per session.
    """
    def __init__(self) -> None:
        self._version = None  # type: Optional[SemanticVersion]

    def resolve(self) -> Optional[SemanticVersion]:
        if self._version:
            return self._version

        try:
            output = subprocess.check_output(
                ['node', '--version'], shell=sublime.platform() == 'windows', stderr=subprocess.STDOUT)
            self._version = parse_version(decode_bytes(output).strip())
        except subprocess.CalledProcessError as error:
            error = decode_bytes(error.output).strip()
            log_and_show_message('lsp_utils(NodeVersionResolver): Error resolving node version: {}!'.format(error))

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
    def binary_path(self) -> str:
        return os.path.join(self._package_storage, self._node_version, self._binary_path)

    def setup(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self._copy_to_storage()

    def cleanup(self) -> None:
        if os.path.isdir(self._package_storage):
            shutil.rmtree(self._package_storage)

    def _copy_to_storage(self) -> None:
        src_path = 'Packages/{}/{}/'.format(self._package_name, self._server_directory)
        dst_path = os.path.join(self._package_storage, self._node_version, self._server_directory)

        if os.path.isdir(dst_path):
            # Server already in cache. Check if version has changed and if so, delete existing copy in cache.
            try:
                src_package_json = ResourcePath(src_path, 'package.json').read_text()
                with open(os.path.join(dst_path, 'package.json'), 'r') as file:
                    dst_package_json = file.read()

                if src_package_json != dst_package_json:
                    shutil.rmtree(dst_path)
            except FileNotFoundError:
                shutil.rmtree(dst_path)

        if not os.path.isdir(dst_path):
            # create cache folder
            ResourcePath(src_path).copytree(dst_path, exist_ok=True)

        dependencies_installed = os.path.isdir(os.path.join(dst_path, 'node_modules'))
        if dependencies_installed:
            self._is_ready = True
        else:
            self._install_dependencies(dst_path)

    def _install_dependencies(self, server_path: str) -> None:
        # this will be called only when the plugin gets:
        # - installed for the first time,
        # - or when updated on package control
        install_message = '{}: Installing server in path: {}'.format(self._package_name, server_path)
        log_and_show_message(install_message, show_in_status=False)

        active_window = sublime.active_window()
        if active_window:
            self._activity_indicator = ActivityIndicator(active_window.active_view(), install_message)
            self._activity_indicator.start()

        run_command(
            self._on_install_success, self._on_error,
            ["npm", "install", "--verbose", "--production", "--prefix", server_path, server_path]
        )

    def _on_install_success(self, _: str) -> None:
        self._is_ready = True
        self._stop_indicator()
        log_and_show_message(
            '{}: Server installed. Sublime Text restart might be required.'.format(self._package_name))

    def _on_error(self, error: str) -> None:
        self._stop_indicator()
        log_and_show_message('{}: Error:'.format(self._package_name), error)

    def _stop_indicator(self) -> None:
        if self._activity_indicator:
            self._activity_indicator.stop()
            self._activity_indicator = None
