from __future__ import annotations

from ._util import download_file
from ._util import extract_archive
from ._util import logger
from .constants import SETTINGS_FILENAME
from .helpers import rmtree_ex
from .helpers import run_command_sync
from .helpers import SemanticVersion
from .helpers import version_to_string
from .third_party.semantic_version import NpmSpec  # pyright: ignore[reportPrivateLocalImportUsage]
from .third_party.semantic_version import Version  # pyright: ignore[reportPrivateLocalImportUsage]
from contextlib import contextmanager
from LSP.plugin.core.logging import debug
from pathlib import Path
from sublime_lib import ActivityIndicator
from typing import Any
from typing import cast
from typing import final
from typing import Generator
from typing_extensions import override
import os
import shutil
import sublime
import subprocess  # noqa: S404
import sys

__all__ = ['NodeRuntime']


IS_WINDOWS_7_OR_LOWER = sys.platform == 'win32' and sys.getwindowsversion()[:2] <= (6, 1)

NODE_RUNTIME_VERSION = '22.18.0'
NODE_DIST_URL = 'https://nodejs.org/dist/v{version}/{filename}'

ELECTRON_RUNTIME_VERSION = '37.3.1'
ELECTRON_NODE_VERSION = '22.18.0'
ELECTRON_DIST_URL = 'https://github.com/electron/electron/releases/download/v{version}/{filename}'
YARN_URL = 'https://github.com/yarnpkg/yarn/releases/download/v1.22.22/yarn-1.22.22.js'

NO_NODE_FOUND_MESSAGE = 'Could not start {package_name} due to not being able to resolve suitable Node.js \
runtime on the PATH. Press the "Download Node.js" button to get required Node.js version \
(note that it will be used only by LSP and will not affect your system otherwise).'


class NodeRuntime:
    _node_runtime_resolved: bool = False
    _node_runtime: NodeRuntime | None = None
    """
    Cached instance of resolved Node.js runtime. This is only done once per-session to avoid unnecessary IO.
    """

    @classmethod
    def get(
        cls, package_name: str, storage_path: str, required_node_version: str | SemanticVersion,
    ) -> NodeRuntime | None:
        if isinstance(required_node_version, tuple):
            required_semantic_version = NpmSpec(f'>={version_to_string(required_node_version)}')
        else:
            required_semantic_version = NpmSpec(required_node_version)
        if cls._node_runtime_resolved:
            if cls._node_runtime:
                cls._node_runtime.check_satisfies_version(required_semantic_version)
            return cls._node_runtime
        cls._node_runtime_resolved = True
        cls._node_runtime = cls._resolve_node_runtime(package_name, Path(storage_path), required_semantic_version)
        debug(f'Resolved Node.js Runtime for package {package_name}: {cls._node_runtime}')
        return cls._node_runtime

    @classmethod
    def _resolve_node_runtime(
        cls, package_name: str, storage_path: Path, required_node_version: NpmSpec,
    ) -> NodeRuntime:
        resolved_runtime: NodeRuntime | None = None
        default_runtimes = ['system', 'local']
        settings = sublime.load_settings(SETTINGS_FILENAME)
        selected_runtimes = cast('list[str]', settings.get('nodejs_runtime') or default_runtimes)
        log_lines = ['--- lsp_utils Node.js resolving start ---']
        for runtime_type in selected_runtimes:
            if runtime_type == 'system':
                log_lines.append(f'Resolving Node.js Runtime in env PATH for package {package_name}...')
                path_runtime = NodeRuntimePATH()
                try:
                    path_runtime.check_binary_present()
                except Exception as ex:
                    log_lines.append(f' * Failed: {ex}')
                    continue
                try:
                    path_runtime.check_satisfies_version(required_node_version)
                    resolved_runtime = path_runtime
                    break
                except Exception as ex:
                    log_lines.append(f' * {ex}')
            elif runtime_type == 'local':
                log_lines.append(f'Resolving Node.js Runtime from lsp_utils for package {package_name}...')
                use_electron = cast('bool', settings.get('local_use_electron') or False)
                runtime_dir = storage_path / 'lsp_utils' / 'node-runtime'
                local_runtime = ElectronRuntimeLocal(runtime_dir) if use_electron else NodeRuntimeLocal(runtime_dir)
                try:
                    local_runtime.check_binary_present()
                except Exception as ex:
                    log_lines.append(f' * Binaries check failed: {ex}')
                    if selected_runtimes[0] != 'local' and not sublime.ok_cancel_dialog(
                            NO_NODE_FOUND_MESSAGE.format(package_name=package_name), 'Download Node.js'):
                        log_lines.append(' * Download skipped')
                        continue
                    # Remove outdated runtimes.
                    if runtime_dir.is_dir():
                        for directory in next(os.walk(runtime_dir))[1]:
                            old_dir = runtime_dir / directory
                            logger.info(f'Deleting outdated Node.js runtime directory "{old_dir}"')
                            try:
                                rmtree_ex(old_dir)
                            except Exception as ex:
                                log_lines.append(f' * Failed deleting: {ex}')
                    try:
                        local_runtime.install_node()
                    except Exception as ex:
                        log_lines.append(f' * Failed downloading: {ex}')
                        continue
                    try:
                        local_runtime.check_binary_present()
                    except Exception as ex:
                        log_lines.append(f' * Failed: {ex}')
                        continue
                try:
                    local_runtime.check_satisfies_version(required_node_version)
                    resolved_runtime = local_runtime
                    break
                except Exception as ex:
                    log_lines.append(f' * {ex}')
        if not resolved_runtime:
            log_lines.append('--- lsp_utils Node.js resolving end ---')
            msg = 'Failed resolving Node.js Runtime. Please check in the console for more details.'
            raise Exception(msg)
        return resolved_runtime

    def __init__(self) -> None:
        self._node: Path | None = None
        self._npm: Path | None = None
        self._version: Version | None = None
        self._additional_paths: list[str] = []

    @override
    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(node: {self._node}, npm: {self._npm}, version: {self._version or None})'

    def install_node(self) -> None:
        msg = 'Not supported!'
        raise Exception(msg)

    def node_bin(self) -> str | None:
        return str(self._node)

    def npm_bin(self) -> str | None:
        return str(self._npm)

    def node_env(self) -> dict[str, str]:
        if IS_WINDOWS_7_OR_LOWER:
            return {'NODE_SKIP_PLATFORM_CHECK': '1'}
        return {}

    def check_binary_present(self) -> None:
        if self._node is None:
            msg = '"node" binary not found'
            raise Exception(msg)
        if self._npm is None:
            msg = '"npm" binary not found'
            raise Exception(msg)

    def check_satisfies_version(self, required_node_version: NpmSpec) -> None:
        node_version = self.resolve_version()
        if node_version not in required_node_version:
            msg = f'Node.js version requirement failed. Expected {required_node_version}, got {node_version}.'
            raise Exception(
                msg)

    def resolve_version(self) -> Version:
        if self._version:
            return self._version
        if not self._node:
            msg = 'Node.js not initialized'
            raise Exception(msg)
        # In this case we have fully resolved binary path already so shouldn't need `shell` on Windows.
        version, error = run_command_sync([self._node, '--version'], extra_env=self.node_env(), shell=False)
        if error is None:
            self._version = Version(version.replace('v', ''))
        else:
            msg = f'Failed resolving Node.js version. Error:\n{error}'
            raise Exception(msg)
        return self._version

    def run_node(
        self,
        args: list[str],
        stdin: int = subprocess.PIPE,
        stdout: int = subprocess.PIPE,
        stderr: int = subprocess.PIPE,
        env: dict[str, Any] | None = None,
    ) -> subprocess.Popen[bytes] | None:
        if env is None:
            env = {}
        node_bin = self.node_bin()
        if node_bin is None:
            return None
        os_env = os.environ.copy()
        os_env.update(self.node_env())
        os_env.update(env)
        startupinfo = None
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
        return subprocess.Popen(  # noqa: S603
            [node_bin, *args], stdin=stdin, stdout=stdout, stderr=stderr, env=os_env, startupinfo=startupinfo)

    def run_install(self, cwd: str | os.PathLike[str]) -> None:
        if not Path(cwd).is_dir():
            msg = f'Specified working directory "{cwd}" does not exist'
            raise Exception(msg)
        if not self._node:
            msg = 'Node.js not installed. Use NodeInstaller to install it first.'
            raise Exception(msg)
        args = [
            'ci',
            '--omit=dev',
            '--verbose',
        ]
        stdout, error = run_command_sync(
            [*self.npm_command(), *args], cwd=cwd, extra_env=self.node_env(), extra_paths=self._additional_paths,
            shell=False,
        )
        logger.info('START output of command: "{}"'.format(' '.join(args)))
        logger.info(stdout)
        logger.info('Command output END')
        if error is not None:
            msg = 'Failed to run npm command "{}":\n{}'.format(' '.join(args), error)
            raise Exception(msg)

    def npm_command(self) -> list[Path]:
        if self._npm is None:
            msg = 'Npm command not initialized'
            raise Exception(msg)
        return [self._npm]


@final
class NodeRuntimePATH(NodeRuntime):
    def __init__(self) -> None:
        super().__init__()
        node = shutil.which('node')
        npm = shutil.which('npm')
        self._node = Path(node) if node else None
        self._npm = Path(npm) if npm else None


@final
class NodeRuntimeLocal(NodeRuntime):

    def __init__(self, base_dir: Path, node_version: str = NODE_RUNTIME_VERSION) -> None:
        super().__init__()
        self._base_dir = (base_dir / node_version).resolve()
        self._node_version = node_version
        self._node_dir = self._base_dir / 'node'
        self._install_in_progress_marker_file = self._base_dir / '.installing'
        self._resolve_paths()

    # --- NodeRuntime overrides ----------------------------------------------------------------------------------------

    @override
    def npm_command(self) -> list[Path]:
        if not self._node or not self._npm:
            msg = 'Node.js or Npm command not initialized'
            raise Exception(msg)
        return [self._node, self._npm]

    @override
    def install_node(self) -> None:
        self._install_in_progress_marker_file.parent.mkdir(exist_ok=True, parents=True)
        self._install_in_progress_marker_file.open('a', encoding='utf-8').close()
        with ActivityIndicator(sublime.active_window(), '[LSP] Setting up local Node.js'):
            install_node = NodeInstaller(self._base_dir, self._node_version)
            install_node.run()
            self._resolve_paths()
        self._install_in_progress_marker_file.unlink()
        self._resolve_paths()

    # --- private methods ----------------------------------------------------------------------------------------------

    def _resolve_paths(self) -> None:
        if self._install_in_progress_marker_file.is_file():
            # Will trigger re-installation.
            return
        self._node = self._resolve_binary()
        self._node_lib = self._resolve_lib()
        self._npm = self._node_lib / 'npm' / 'bin' / 'npm-cli.js'
        self._additional_paths = [str(self._node.parent)] if self._node else []

    def _resolve_binary(self) -> Path | None:
        exe_path = self._node_dir / 'node.exe'
        binary_path = self._node_dir / 'bin' / 'node'
        if exe_path.is_file():
            return exe_path
        if binary_path.is_file():
            return binary_path
        return None

    def _resolve_lib(self) -> Path:
        lib_path = self._node_dir / 'lib' / 'node_modules'
        if not lib_path.is_dir():
            lib_path = self._node_dir / 'node_modules'
        return lib_path


@final
class NodeInstaller:
    """Command to install a local copy of Node.js."""

    def __init__(self, base_dir: Path, node_version: str = NODE_RUNTIME_VERSION) -> None:
        """
        Init NodeInstaller.

        :param base_dir: The base directory for storing given Node.js runtime version
        :param node_version: The Node.js version to install
        """
        self._base_dir = base_dir
        self._node_version = node_version
        self._cache_dir = self._base_dir / 'cache'

    def run(self) -> None:
        cache_directory = self._cache_dir
        archive_filename, url = self._node_archive()
        logger.info(f'Downloading Node.js {self._node_version} from {url}')
        archive_path = cache_directory / archive_filename
        if not archive_path.is_file():
            if not cache_directory.is_dir():
                cache_directory.mkdir()
            download_file(url, archive_path)
        self._install_node(archive_path)

    def _node_archive(self) -> tuple[str, str]:
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
            msg = f'{arch} {platform} is not supported'
            raise Exception(msg)
        filename = f'node-v{self._node_version}-{node_os}-{arch}.{archive}'
        dist_url = NODE_DIST_URL.format(version=self._node_version, filename=filename)
        return filename, dist_url

    def _install_node(self, archive_path: Path) -> None:
        install_directory = extract_archive(archive_path, self._base_dir)
        install_directory.rename(install_directory.parent / 'node')
        archive_path.unlink()


@final
class ElectronRuntimeLocal(NodeRuntime):
    def __init__(self, base_dir: Path) -> None:
        super().__init__()
        self._base_dir = (base_dir / ELECTRON_NODE_VERSION).resolve()
        self._yarn = self._base_dir / 'yarn.js'
        self._install_in_progress_marker_file = self._base_dir / '.installing'
        if not self._install_in_progress_marker_file.is_file():
            self._resolve_paths()

    # --- NodeRuntime overrides ----------------------------------------------------------------------------------------

    @override
    def node_env(self) -> dict[str, str]:
        extra_env = super().node_env()
        extra_env.update({'ELECTRON_RUN_AS_NODE': 'true'})
        return extra_env

    @override
    def install_node(self) -> None:
        self._install_in_progress_marker_file.parent.mkdir(exist_ok=True, parents=True)
        self._install_in_progress_marker_file.open('a', encoding='utf-8').close()
        with ActivityIndicator(sublime.active_window(), '[LSP] Setting up local Node.js'):
            install_node = ElectronInstaller(self._base_dir)
            install_node.run()
            self._resolve_paths()
        self._install_in_progress_marker_file.unlink()

    @override
    def run_install(self, cwd: str | os.PathLike[str]) -> None:
        self._run_yarn(['import'], cwd)
        args = [
            'install',
            '--production',
            '--frozen-lockfile',
            '--cache-folder={}'.format(self._base_dir / 'cache' / 'yarn'),
            # '--verbose',
        ]
        self._run_yarn(args, cwd)

    # --- private methods ----------------------------------------------------------------------------------------------

    def _resolve_paths(self) -> None:
        self._node = self._resolve_binary()
        self._npm = self._base_dir / 'yarn.js'

    def _resolve_binary(self) -> Path | None:
        binary_path = None
        platform = sublime.platform()
        if platform == 'osx':
            binary_path = self._base_dir / 'Electron.app' / 'Contents' / 'MacOS' / 'Electron'
        elif platform == 'windows':
            binary_path = self._base_dir / 'electron.exe'
        else:
            binary_path = self._base_dir / 'electron'
        return binary_path if binary_path.is_file() else None

    def _run_yarn(self, args: list[str], cwd: str | os.PathLike[str]) -> None:
        if not Path(cwd).is_dir():
            msg = f'Specified working directory "{cwd}" does not exist'
            raise Exception(msg)
        if not self._node:
            msg = 'Node.js not installed. Use NodeInstaller to install it first.'
            raise Exception(msg)
        stdout, error = run_command_sync(
            [self._node, self._yarn, *args], cwd=cwd, extra_env=self.node_env(), shell=False,
        )
        logger.info('START output of command: "{}"'.format(' '.join(args)))
        logger.info(stdout)
        logger.info('Command output END')
        if error is not None:
            msg = 'Failed to run yarn command "{}":\n{}'.format(' '.join(args), error)
            raise Exception(msg)


@final
class ElectronInstaller:
    """Command to install a local copy of Node.js."""

    def __init__(self, base_dir: Path) -> None:
        """:param base_dir: The base directory for storing given Node.js runtime version"""
        self._base_dir = base_dir
        self._cache_dir = self._base_dir / 'cache'

    def run(self) -> None:
        cache_directory = self._cache_dir
        archive_filename, url = self._node_archive()
        logger.info(
            f'Downloading Electron {ELECTRON_RUNTIME_VERSION} (Node.js runtime {ELECTRON_NODE_VERSION}) from {url}',
        )
        archive_path = cache_directory / archive_filename
        if not archive_path.is_file():
            if not cache_directory.is_dir():
                cache_directory.mkdir()
            download_file(url, archive_path)
        self._install(archive_path)
        download_file(YARN_URL, self._base_dir / 'yarn.js')

    def _node_archive(self) -> tuple[str, str]:
        platform = sublime.platform()
        arch = sublime.arch()
        if platform == 'windows':
            platform_code = 'win32'
        elif platform == 'linux':
            platform_code = 'linux'
        elif platform == 'osx':
            platform_code = 'darwin'
        else:
            msg = f'{arch} {platform} is not supported'
            raise Exception(msg)
        filename = f'electron-v{ELECTRON_RUNTIME_VERSION}-{platform_code}-{arch}.zip'
        dist_url = ELECTRON_DIST_URL.format(version=ELECTRON_RUNTIME_VERSION, filename=filename)
        return filename, dist_url

    def _install(self, archive_path: Path) -> None:
        try:
            if sublime.platform() == 'windows':
                extract_archive(archive_path, Path(self._base_dir))
            else:
                # ZipFile doesn't handle symlinks and permissions correctly on Linux and Mac. Use unzip instead.
                _, error = run_command_sync(['unzip', archive_path, '-d', self._base_dir], cwd=self._cache_dir)
                if error:
                    msg = f'Error unzipping electron archive: {error}'
                    raise Exception(msg)
        finally:
            archive_path.unlink()


@contextmanager
def chdir(new_dir: str) -> Generator[None, None, None]:
    """Context Manager for changing the working directory."""
    cur_dir = Path.cwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(cur_dir)
