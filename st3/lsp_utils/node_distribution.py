from .activity_indicator import ActivityIndicator
from .helpers import parse_version
from .helpers import run_command_sync
from .helpers import SemanticVersion
from contextlib import contextmanager
from LSP.plugin.core.typing import Optional, Tuple
from os import path
import os
import shutil
import sublime
import tarfile
import urllib.request
import zipfile

__all__ = ['NodeDistribution', 'NodeDistributionPATH', 'NodeDistributionLocal']


class NodeDistribution:
    def __init__(self) -> None:
        self._node = None  # type: Optional[str]
        self._npm = None  # type: Optional[str]
        self._version = None  # type: Optional[SemanticVersion]

    def node_exists(self) -> bool:
        return self._node is not None

    def node_bin(self) -> Optional[str]:
        return self._node

    def resolve_version(self) -> Optional[SemanticVersion]:
        if self._version:
            return self._version
        if not self._node:
            raise Exception('Node not initialized')
        version, error = run_command_sync([self._node, '--version'])
        if error is None:
            self._version = parse_version(version)
        else:
            raise Exception('Error resolving node version: {}'.format(error))
        return self._version

    def npm_command(self) -> str:
        if self._npm is None:
            raise Exception('Npm command not initialized')
        return self._npm

    def npm_install(self, package_dir: str, use_ci: bool = True) -> None:
        if not path.isdir(package_dir):
            raise Exception('Specified package_dir path "{}" does not exist'.format(package_dir))
        if not self._node:
            raise Exception('Node not installed. Use InstallNode command first.')
        args = [
            self.npm_command(),
            'ci' if use_ci else 'install',
            '--scripts-prepend-node-path',
            '--verbose',
            '--production',
            '--prefix', package_dir,
            package_dir
        ]
        output, error = run_command_sync(args)
        if error is not None:
            raise Exception('Failed to run npm command "{}":\n{}'.format(' '.join(args), error))


class NodeDistributionPATH(NodeDistribution):
    def __init__(self) -> None:
        super().__init__()
        self._node = shutil.which('node')
        self._npm = 'npm'


class NodeDistributionLocal(NodeDistribution):
    def __init__(self, base_dir: str):
        super().__init__()
        self._base_dir = path.abspath(base_dir)
        self._node_dir = path.join(self._base_dir, 'node')
        self.resolve_paths()

    def resolve_paths(self) -> None:
        self._node = self.resolve_binary()
        self._node_lib = self.resolve_lib()
        self._npm = path.join(self._node_lib, 'npm', 'bin', 'npm-cli.js')

    def resolve_binary(self) -> Optional[str]:
        exe_path = path.join(self._node_dir, 'node.exe')
        binary_path = path.join(self._node_dir, 'bin', 'node')
        if path.isfile(exe_path):
            return exe_path
        elif path.isfile(binary_path):
            return binary_path

    def resolve_lib(self) -> str:
        lib_path = path.join(self._node_dir, 'lib', 'node_modules')
        if not path.isdir(lib_path):
            lib_path = path.join(self._node_dir, 'node_modules')
        return lib_path

    def npm_command(self) -> str:
        if not self._node or not self._npm:
            raise Exception('Node or Npm command not initialized')
        return path.join(self._node, self._npm)

    def install_node(self) -> None:
        with ActivityIndicator(sublime.active_window(), 'Installing Node'):
            install_node = InstallNode(self._base_dir)
            install_node.run()
            self.resolve_paths()


class InstallNode:
    '''Command to install a local copy of Node'''

    def __init__(self, base_dir: str, node_version: str = '14.15.4',
                 node_dist_url = 'https://nodejs.org/dist/') -> None:
        """
        :param base_dir: The base directory for storing given node version and distribution files
        :param node_version: Directory to cache Node distribution files
        :param node_dist_url: Base URL to fetch Node from
        """
        self._base_dir = base_dir
        self._node_version = node_version
        self._cache_dir = path.join(self._base_dir, 'cache')
        self._node_dist_url = node_dist_url

    def run(self) -> None:
        print('Installing Node {}'.format(self._node_version))
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
        elif platform == 'linux' and arch == 'x64':
            node_os = 'linux'
            archive = 'tar.xz'
        elif platform == 'osx' and arch == 'x64':
            node_os = 'darwin'
            archive = 'tar.gz'
        else:
            raise Exception('{} {} is not supported'.format(arch, platform))
        filename = 'node-v{}-{}-{}.{}'.format(self._node_version, node_os, arch, archive)
        dist_url = '{}v{}/{}'.format(self._node_dist_url, self._node_version, filename)
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
        opener = zipfile.ZipFile if filename.endswith('.zip') else tarfile.open
        with opener(archive) as f:
            names = f.namelist() if hasattr(f, 'namelist') else f.getnames()
            install_dir, _ = next(x for x in names if '/' in x).split('/', 1)
            bad_members = [x for x in names if x.startswith('/') or x.startswith('..')]
            if bad_members:
                raise Exception('{} appears to be malicious, bad filenames: {}'.format(filename, bad_members))
            f.extractall(self._base_dir)
            with chdir(self._base_dir):
                os.rename(install_dir, 'node')
        os.remove(archive)


@contextmanager
def chdir(new_dir: str):
    '''Context Manager for changing the working directory'''
    cur_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(cur_dir)


