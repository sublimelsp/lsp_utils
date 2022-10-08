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
import sys
import tarfile
import urllib.request
import zipfile

__all__ = ['NodeRuntime', 'NodeRuntimePATH', 'NodeRuntimeLocal']

IS_MAC_ARM = sublime.platform() == 'osx' and sublime.arch() == 'arm64'
IS_WINDOWS_7_OR_LOWER = sys.platform == 'win32' and sys.getwindowsversion()[:2] <= (6, 1)  # type: ignore

DEFAULT_NODE_VERSION = '16.15.0'
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
                local_runtime = NodeRuntimeLocal(path.join(storage_path, 'lsp_utils', 'node-runtime'))
                try:
                    local_runtime.check_binary_present()
                except Exception as ex:
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

    def node_env(self) -> Optional[Dict[str, str]]:
        if IS_WINDOWS_7_OR_LOWER:
            return {'NODE_SKIP_PLATFORM_CHECK': '1'}
        return None

    def check_binary_present(self) -> None:
        if self._node is None:
            raise Exception('"node" binary not found')
        if self._npm is None:
            raise Exception('"npm" binary not found')

    def check_satisfies_version(self, required_node_version: NpmSpec) -> None:
        node_version = self.resolve_version()
        if node_version not in required_node_version:
            raise Exception(
                'Version requirement failed. Expected {}, got {}.'.format(required_node_version, node_version))

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
        with ActivityIndicator(sublime.active_window(), 'Downloading Node.js'):
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
        print('[lsp_utils] Downloading Node.js {}'.format(self._node_version))
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
