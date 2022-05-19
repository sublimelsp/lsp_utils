from .helpers import log_and_show_message
from .helpers import parse_version
from .helpers import run_command_sync
from .helpers import SemanticVersion
from .helpers import version_to_string
from contextlib import contextmanager
from LSP.plugin.core.logging import debug
from LSP.plugin.core.typing import Any, Dict, Generator, List, Optional, Tuple
from os import path
from os import remove
from sublime_lib import ActivityIndicator
import os
import shutil
import sublime
import sys
import tarfile
import urllib.request
import zipfile

__all__ = ['NodeRuntime', 'NodeRuntimePATH', 'NodeRuntimeLocal']

IS_MAC_ARM = sublime.platform() == 'osx' and sublime.arch() == 'arm64'
IS_WINDOWS_7_OR_LOWER = sys.platform == 'win32' and sys.getwindowsversion()[:2] <= (6, 1)  # type: ignore

DEFAULT_NODE_VERSION = '16.15.0'
NODE_DIST_URL = 'https://nodejs.org/dist/v{version}/{filename}'
NO_NODE_FOUND_MESSAGE = 'Could not start {package_name} due to not being able to find Node.js \
runtime on the PATH. Press the "Install Node.js" button to install Node.js automatically \
(note that it will be installed locally for LSP and will not affect your system otherwise).'


class NodeRuntime:
    _node_runtime_resolved = False
    _node_runtime = None  # Optional[NodeRuntime]
    """
    Cached instance of resolved Node.js runtime. This is only done once per-session to avoid unnecessary IO.
    """

    @classmethod
    def get(cls, package_name: str, storage_path: str, minimum_version: SemanticVersion) -> Optional['NodeRuntime']:
        if cls._node_runtime_resolved:
            if cls._node_runtime:
                cls._check_node_version(cls._node_runtime, minimum_version)
            return cls._node_runtime
        cls._node_runtime_resolved = True
        cls._node_runtime = cls._resolve_node_runtime(package_name, storage_path, minimum_version)
        debug('Resolved Node Runtime for client {}: {}'.format(package_name, cls._node_runtime))
        return cls._node_runtime

    @classmethod
    def _resolve_node_runtime(
        cls, package_name: str, storage_path: str, minimum_version: SemanticVersion
    ) -> Optional['NodeRuntime']:
        node_runtime = None  # type: Optional[NodeRuntime]
        default_runtimes = ['system', 'local']
        settings = sublime.load_settings('lsp_utils.sublime-settings')
        selected_runtimes = settings.get('nodejs_runtime') or default_runtimes
        for runtime in selected_runtimes:
            if runtime == 'system':
                node_runtime = NodeRuntimePATH()
                if node_runtime.meets_requirements():
                    try:
                        cls._check_node_version(node_runtime, minimum_version)
                        return node_runtime
                    except Exception as ex:
                        message = 'Ignoring system Node.js runtime due to an error. {}'.format(ex)
                        log_and_show_message('{}: Error: {}'.format(package_name, message))
                else:
                    message = 'The system Node.js does not meet the requirements: {}'.format(node_runtime)
                    log_and_show_message('{}: {}'.format(package_name, message))
            elif runtime == 'local':
                node_runtime = NodeRuntimeLocal(path.join(storage_path, 'lsp_utils', 'node-runtime'))
                if not node_runtime.meets_requirements():
                    if not sublime.ok_cancel_dialog(NO_NODE_FOUND_MESSAGE.format(package_name=package_name),
                                                    'Install Node.js'):
                        return None
                    try:
                        node_runtime.install_node()
                    except Exception as ex:
                        log_and_show_message('{}: Error: Failed installing a local Node.js runtime:\n{}'.format(
                            package_name, ex))
                        return None
                if node_runtime.meets_requirements():
                    try:
                        cls._check_node_version(node_runtime, minimum_version)
                        return node_runtime
                    except Exception as ex:
                        error = 'Ignoring local Node.js runtime due to an error. {}'.format(ex)
                        log_and_show_message('{}: Error: {}'.format(package_name, error))
        return None

    @classmethod
    def _check_node_version(cls, node_runtime: 'NodeRuntime', minimum_version: SemanticVersion) -> None:
        node_version = node_runtime.resolve_version()
        if node_version < minimum_version:
            raise Exception('Node.js version requirement failed. Expected minimum: {}, got {}.'.format(
                version_to_string(minimum_version), version_to_string(node_version)))

    def __init__(self) -> None:
        self._node = None  # type: Optional[str]
        self._npm = None  # type: Optional[str]
        self._version = None  # type: Optional[SemanticVersion]
        self._additional_paths = []  # type: List[str]

    def __repr__(self) -> str:
        return '{}(node: {}, npm: {}, version: {})'.format(
            self.__class__.__name__, self._node, self._npm, version_to_string(self._version) if self._version else None)

    def meets_requirements(self) -> bool:
        return self._node is not None and self._npm is not None

    def node_bin(self) -> Optional[str]:
        return self._node

    def node_env(self) -> Optional[Dict[str, str]]:
        if IS_WINDOWS_7_OR_LOWER:
            return {'NODE_SKIP_PLATFORM_CHECK': '1'}
        return None

    def resolve_version(self) -> SemanticVersion:
        if self._version:
            return self._version
        if not self._node:
            raise Exception('Node.js not initialized')
        version, error = run_command_sync([self._node, '--version'], extra_env=self.node_env())
        if error is None:
            self._version = parse_version(version)
        else:
            raise Exception('Error resolving node version:\n{}'.format(error))
        return self._version

    def npm_command(self) -> List[str]:
        if self._npm is None:
            raise Exception('Npm command not initialized')
        return [self._npm]

    def npm_install(self, package_dir: str, use_ci: bool = True) -> None:
        if not path.isdir(package_dir):
            raise Exception('Specified package_dir path "{}" does not exist'.format(package_dir))
        if not self._node:
            raise Exception('Node.js not installed. Use InstallNode command first.')
        args = self.npm_command() + [
            'ci' if use_ci else 'install',
            '--scripts-prepend-node-path=true',
            '--verbose',
            '--production',
        ]
        stdout, error = run_command_sync(
            args, cwd=package_dir, extra_env=self.node_env(), extra_paths=self._additional_paths)
        print('[lsp_utils] START output of command: "{}"'.format(''.join(args)))
        print(stdout)
        print('[lsp_utils] Command output END')
        if error is not None:
            raise Exception('Failed to run npm command "{}":\n{}'.format(' '.join(args), error))


class NodeRuntimePATH(NodeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._node = shutil.which('node')
        self._npm = shutil.which('npm')


class NodeRuntimeLocal(NodeRuntime):
    def __init__(self, base_dir: str, node_version: str = DEFAULT_NODE_VERSION):
        super().__init__()
        self._base_dir = path.abspath(path.join(base_dir, node_version))
        self._node_version = node_version
        self._node_dir = path.join(self._base_dir, 'node')
        self._additional_paths = [path.join(self._node_dir, 'bin')]
        self._install_in_progress_marker_file = path.join(self._base_dir, '.installing')
        self.resolve_paths()

    def resolve_paths(self) -> None:
        if path.isfile(self._install_in_progress_marker_file):
            # Will trigger re-installation.
            return
        self._node = self.resolve_binary()
        self._node_lib = self.resolve_lib()
        self._npm = path.join(self._node_lib, 'npm', 'bin', 'npm-cli.js')

    def resolve_binary(self) -> Optional[str]:
        exe_path = path.join(self._node_dir, 'node.exe')
        binary_path = path.join(self._node_dir, 'bin', 'node')
        if path.isfile(exe_path):
            return exe_path
        if path.isfile(binary_path):
            return binary_path
        return None

    def resolve_lib(self) -> str:
        lib_path = path.join(self._node_dir, 'lib', 'node_modules')
        if not path.isdir(lib_path):
            lib_path = path.join(self._node_dir, 'node_modules')
        return lib_path

    def npm_command(self) -> List[str]:
        if not self._node or not self._npm:
            raise Exception('Node.js or Npm command not initialized')
        return [self._node, self._npm]

    def install_node(self) -> None:
        os.makedirs(os.path.dirname(self._install_in_progress_marker_file), exist_ok=True)
        open(self._install_in_progress_marker_file, 'a').close()
        with ActivityIndicator(sublime.active_window(), 'Installing Node.js'):
            install_node = InstallNode(self._base_dir, self._node_version)
            install_node.run()
            self.resolve_paths()
        remove(self._install_in_progress_marker_file)
        self.resolve_paths()


class InstallNode:
    '''Command to install a local copy of Node.js'''

    def __init__(self, base_dir: str, node_version: str = DEFAULT_NODE_VERSION) -> None:
        """
        :param base_dir: The base directory for storing given Node.js runtime version
        :param node_version: The Node.js version to install
        """
        self._base_dir = base_dir
        self._node_version = node_version
        self._cache_dir = path.join(self._base_dir, 'cache')

    def run(self) -> None:
        print('[lsp_utils] Installing Node.js {}'.format(self._node_version))
        archive, url = self._node_archive()
        if not self._node_archive_exists(archive):
            self._download_node(url, archive)
        self._install_node(archive)

    def _node_archive(self) -> Tuple[str, str]:
        platform = sublime.platform()
        arch = sublime.arch()
        if platform == 'windows' and arch == 'x64':
            node_os = 'win'
            archive = 'zip'
        elif platform == 'linux':
            node_os = 'linux'
            archive = 'tar.gz'
        elif platform == 'osx':
            node_os = 'darwin'
            archive = 'tar.gz'
        else:
            raise Exception('{} {} is not supported'.format(arch, platform))
        filename = 'node-v{}-{}-{}.{}'.format(self._node_version, node_os, arch, archive)
        dist_url = NODE_DIST_URL.format(version=self._node_version, filename=filename)
        return filename, dist_url

    def _node_archive_exists(self, filename: str) -> bool:
        archive = path.join(self._cache_dir, filename)
        return path.isfile(archive)

    def _download_node(self, url: str, filename: str) -> None:
        if not path.isdir(self._cache_dir):
            os.makedirs(self._cache_dir)
        archive = path.join(self._cache_dir, filename)
        with urllib.request.urlopen(url) as response:
            with open(archive, 'wb') as f:
                shutil.copyfileobj(response, f)

    def _install_node(self, filename: str) -> None:
        archive = path.join(self._cache_dir, filename)
        opener = zipfile.ZipFile if filename.endswith('.zip') else tarfile.open  # type: Any
        try:
            with opener(archive) as f:
                names = f.namelist() if hasattr(f, 'namelist') else f.getnames()
                install_dir, _ = next(x for x in names if '/' in x).split('/', 1)
                bad_members = [x for x in names if x.startswith('/') or x.startswith('..')]
                if bad_members:
                    raise Exception('{} appears to be malicious, bad filenames: {}'.format(filename, bad_members))
                f.extractall(self._base_dir)
                with chdir(self._base_dir):
                    os.rename(install_dir, 'node')
        except Exception as ex:
            raise ex
        finally:
            remove(archive)


@contextmanager
def chdir(new_dir: str) -> Generator[None, None, None]:
    '''Context Manager for changing the working directory'''
    cur_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(cur_dir)
