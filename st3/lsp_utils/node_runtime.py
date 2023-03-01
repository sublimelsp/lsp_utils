from .helpers import run_command_sync
from .helpers import SemanticVersion
from .helpers import version_to_string
from .third_party.semantic_version import NpmSpec, Version
from contextlib import contextmanager
from LSP.plugin.core.logging import debug
from LSP.plugin.core.typing import cast, Any, Dict, Generator, List, Optional, Tuple, Union
from os import path
from os import remove
from sublime_lib import ActivityIndicator
import os
import shutil
import sublime
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

__all__ = ['NodeRuntime', 'NodeRuntimePATH', 'NodeRuntimeLocal']

IS_WINDOWS_7_OR_LOWER = sys.platform == 'win32' and sys.getwindowsversion()[:2] <= (6, 1)  # type: ignore

DEFAULT_NODE_VERSION = '16.17.1'
ELECTRON_VERSION = '22.2.0'  # includes matching 16.17.1 version of Node.js
NODE_DIST_URL = 'https://nodejs.org/dist/v{version}/{filename}'
NO_NODE_FOUND_MESSAGE = 'Could not start {package_name} due to not being able to resolve suitable Node.js \
runtime on the PATH. Press the "Download Node.js" button to get required Node.js version \
(note that it will be used only by LSP and will not affect your system otherwise).'


class NodeRuntime:
    _node_runtime_resolved = False
    _node_runtime = None  # Optional[NodeRuntime]
    """
    Cached instance of resolved Node.js runtime. This is only done once per-session to avoid unnecessary IO.
    """

    @classmethod
    def get(
        cls, package_name: str, storage_path: str, required_node_version: Union[str, SemanticVersion]
    ) -> Optional['NodeRuntime']:
        if isinstance(required_node_version, tuple):
            required_semantic_version = NpmSpec('>={}'.format(version_to_string(required_node_version)))
        elif isinstance(required_node_version, str):
            required_semantic_version = NpmSpec(required_node_version)
        if cls._node_runtime_resolved:
            if cls._node_runtime:
                cls._node_runtime.check_satisfies_version(required_semantic_version)
            return cls._node_runtime
        cls._node_runtime_resolved = True
        cls._node_runtime = cls._resolve_node_runtime(package_name, storage_path, required_semantic_version)
        debug('Resolved Node.js Runtime for package {}: {}'.format(package_name, cls._node_runtime))
        return cls._node_runtime

    @classmethod
    def _resolve_node_runtime(
        cls, package_name: str, storage_path: str, required_node_version: NpmSpec
    ) -> 'NodeRuntime':
        resolved_runtime = None  # type: Optional[NodeRuntime]
        default_runtimes = ['system', 'local']
        settings = sublime.load_settings('lsp_utils.sublime-settings')
        selected_runtimes = cast(List[str], settings.get('nodejs_runtime') or default_runtimes)
        log_lines = ['--- lsp_utils Node.js resolving start ---']
        for runtime_type in selected_runtimes:
            if runtime_type == 'system':
                log_lines.append('Resolving Node.js Runtime in env PATH for package {}...'.format(package_name))
                path_runtime = NodeRuntimePATH()
                try:
                    path_runtime.check_binary_present()
                except Exception as ex:
                    log_lines.append(' * Failed: {}'.format(ex))
                    continue
                try:
                    path_runtime.check_satisfies_version(required_node_version)
                    resolved_runtime = path_runtime
                    break
                except Exception as ex:
                    log_lines.append(' * {}'.format(ex))
            elif runtime_type == 'local':
                log_lines.append('Resolving Node.js Runtime from lsp_utils for package {}...'.format(package_name))
                use_electron = cast(bool, settings.get('use_electron_for_local_runtime') or False)
                local_runtime = NodeRuntimeLocal(path.join(storage_path, 'lsp_utils', 'node-runtime'), use_electron)
                try:
                    local_runtime.check_binary_present()
                except Exception:
                    log_lines.append(' * Not downloaded. Asking to download...')
                    if not sublime.ok_cancel_dialog(
                            NO_NODE_FOUND_MESSAGE.format(package_name=package_name), 'Download Node.js'):
                        log_lines.append(' * Download skipped')
                        continue
                    try:
                        local_runtime.install_node()
                    except Exception as ex:
                        log_lines.append(' * Failed downloading: {}'.format(ex))
                        resolved_runtime = local_runtime
                        continue
                    try:
                        local_runtime.check_binary_present()
                    except Exception as ex:
                        log_lines.append(' * Failed: {}'.format(ex))
                        continue
                try:
                    local_runtime.check_satisfies_version(required_node_version)
                    if use_electron:
                        local_runtime.check_satisfies_electron()
                    resolved_runtime = local_runtime
                    break
                except Exception as ex:
                    log_lines.append(' * {}'.format(ex))
        if not resolved_runtime:
            log_lines.append('--- lsp_utils Node.js resolving end ---')
            print('\n'.join(log_lines))
            raise Exception('Failed resolving Node.js Runtime. Please check in the console for more details.')
        return resolved_runtime

    def __init__(self) -> None:
        self._node = None  # type: Optional[str]
        self._npm = None  # type: Optional[str]
        self._version = None  # type: Optional[Version]
        self._additional_paths = []  # type: List[str]

    def __repr__(self) -> str:
        return '{}(node: {}, npm: {}, version: {})'.format(
            self.__class__.__name__, self._node, self._npm, self._version if self._version else None)

    def node_bin(self) -> Optional[str]:
        return self._node

    def npm_bin(self) -> Optional[str]:
        return self._npm

    def node_env(self) -> Dict[str, str]:
        if IS_WINDOWS_7_OR_LOWER:
            return {'NODE_SKIP_PLATFORM_CHECK': '1'}
        return {}

    def check_binary_present(self) -> None:
        if self._node is None:
            raise Exception('"node" binary not found')
        if self._npm is None:
            raise Exception('"npm" binary not found')

    def check_satisfies_version(self, required_node_version: NpmSpec) -> None:
        node_version = self.resolve_version()
        if node_version not in required_node_version:
            raise Exception(
                'Node.js version requirement failed. Expected {}, got {}.'.format(required_node_version, node_version))

    def resolve_version(self) -> Version:
        if self._version:
            return self._version
        if not self._node:
            raise Exception('Node.js not initialized')
        version, error = run_command_sync([self._node, '--version'], extra_env=self.node_env())
        if error is None:
            self._version = Version(version.replace('v', ''))
        else:
            raise Exception('Error resolving Node.js version:\n{}'.format(error))
        return self._version

    def run_node(
        self,
        args: List[str],
        stdin: int = subprocess.PIPE,
        stdout: int = subprocess.PIPE,
        stderr: int = subprocess.PIPE,
        env: Dict[str, Any] = {}
    ) -> Optional[subprocess.Popen]:
        node_bin = self.node_bin()
        if node_bin is None:
            return None
        os_env = os.environ.copy()
        os_env.update(self.node_env())
        os_env.update(env)
        startupinfo = None
        if sublime.platform() == 'windows':
            startupinfo = subprocess.STARTUPINFO()  # type: ignore
            startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW  # type: ignore
        return subprocess.Popen(
            [node_bin] + args, stdin=stdin, stdout=stdout, stderr=stderr, env=os_env, startupinfo=startupinfo)

    def run_npm(self, args: List[str], cwd: str) -> None:
        if not path.isdir(cwd):
            raise Exception('Specified working directory "{}" does not exist'.format(cwd))
        if not self._node:
            raise Exception('Node.js not installed. Use InstallNode command first.')
        stdout, error = run_command_sync(
            self._npm_command() + args, cwd=cwd, extra_env=self.node_env(), extra_paths=self._additional_paths)
        print('[lsp_utils] START output of command: "{}"'.format(''.join(args)))
        print(stdout)
        print('[lsp_utils] Command output END')
        if error is not None:
            raise Exception('Failed to run npm command "{}":\n{}'.format(' '.join(args), error))

    def _npm_command(self) -> List[str]:
        if self._npm is None:
            raise Exception('Npm command not initialized')
        return [self._npm]


class NodeRuntimePATH(NodeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._node = shutil.which('node')
        self._npm = shutil.which('npm')


class NodeRuntimeLocal(NodeRuntime):
    def __init__(self, base_dir: str, use_electron: bool, node_version: str = DEFAULT_NODE_VERSION):
        super().__init__()
        self._base_dir = path.abspath(path.join(base_dir, node_version))
        self._node_version = node_version
        self._node_dir = path.join(self._base_dir, 'node')
        self._additional_paths = [self._node_dir, path.join(self._node_dir, 'bin')]
        self._install_in_progress_marker_file = path.join(self._base_dir, '.installing')
        self._use_electron = use_electron
        self._resolve_paths()

    def node_env(self) -> Dict[str, str]:
        extra_env = super().node_env()
        if self._use_electron:
            extra_env.update({'ELECTRON_RUN_AS_NODE': 'true'})
        return extra_env

    def _resolve_paths(self) -> None:
        if path.isfile(self._install_in_progress_marker_file):
            # Will trigger re-installation.
            return
        self._node = self._resolve_binary()
        self._npm = path.join(self._resolve_lib(), 'npm', 'bin', 'npm-cli.js')

    def _resolve_binary(self) -> Optional[str]:
        exe_path = path.join(self._node_dir, 'node.exe')
        binary_path = path.join(self._node_dir, 'bin', 'node')
        if path.isfile(exe_path):
            return exe_path
        if path.isfile(binary_path):
            return binary_path
        return None

    def _resolve_lib(self) -> str:
        lib_path = path.join(self._node_dir, 'lib', 'node_modules')
        if not path.isdir(lib_path):
            lib_path = path.join(self._node_dir, 'node_modules')
        return lib_path

    def _npm_command(self) -> List[str]:
        if not self._node or not self._npm:
            raise Exception('Node.js or Npm command not initialized')
        return [self._node, self._npm]

    def install_node(self) -> None:
        os.makedirs(os.path.dirname(self._install_in_progress_marker_file), exist_ok=True)
        open(self._install_in_progress_marker_file, 'a').close()
        with ActivityIndicator(sublime.active_window(), 'Downloading Node.js'):
            install_node = InstallNode(self._base_dir, self._node_version)
            install_node.run()
            self._resolve_paths()
        remove(self._install_in_progress_marker_file)
        self._resolve_paths()

    def check_satisfies_electron(self) -> None:
        if not self._use_electron:
            return
        if not self._resolve_electron_binary():
            self._install_electron()
        self._node = self._resolve_electron_binary()

    def _install_electron(self) -> None:
        if not self._use_electron:
            return
        with ActivityIndicator(sublime.active_window(), 'Downloading Electron'):
            print('[lsp_utils] Installing Electron dependency...')
            self.run_npm(['install', '-g', 'electron@{}'.format(ELECTRON_VERSION)], cwd=self._node_dir)

    def _resolve_electron_binary(self) -> Optional[str]:
        if not self._use_electron:
            return None
        electron_dist_dir = path.join(self._resolve_lib(), 'electron', 'dist')
        binary_path = None
        platform = sublime.platform()
        if platform == 'osx':
            binary_path = path.join(electron_dist_dir, 'Electron.app', 'Contents', 'MacOS', 'Electron')
        elif platform == 'windows':
            binary_path = path.join(electron_dist_dir, 'electron.exe')
        else:
            binary_path = path.join(electron_dist_dir, 'electron')
        return binary_path if binary_path and path.isfile(binary_path) else None


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
        print('[lsp_utils] Downloading Node.js {}'.format(self._node_version))
        archive, url = self._node_archive()
        if not self._node_archive_exists(archive):
            self._download_node(url, archive)
        self._install(archive)

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

    def _install(self, filename: str) -> None:
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
