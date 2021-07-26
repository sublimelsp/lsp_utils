from .helpers import run_command_sync
from .server_resource_interface import ServerResourceInterface
from .server_resource_interface import ServerStatus
from LSP.plugin.core.typing import Any, Dict, Optional
from sublime_lib import ResourcePath
import os
import shutil
import sublime

__all__ = ['ServerPipResource']


def parse_requirements(content: str) -> Dict[str, Optional[str]]:
    requirements = {}  # type: Dict[str, Optional[str]]
    lines = [line.strip() for line in content.splitlines()]
    for line in lines:
        if line:
            parts = line.split('==')
            if len(parts) == 2:
                requirements[parts[0].replace('[all]', '')] = parts[1]
            elif len(parts) == 1:
                requirements[parts[0]] = None
    return requirements


class ServerPipResource(ServerResourceInterface):
    """
    An implementation of :class:`lsp_utils.ServerResourceInterface` implementing server management for
    pip-based servers. Handles installation and updates of the server in the package storage.

    :param storage_path: The path to the package storage (pass :meth:`lsp_utils.GenericClientHandler.storage_path()`)
    :param package_name: The package name (used as a directory name for storage)
    :param requirements_path: The path to the `requirements.txt` file, relative to the package directory.
           If the package `LSP-foo` has a `requirements.txt` file at the root then the path will be `requirements.txt`.
    :param server_binary_filename: The name of the file used to start the server.
    """

    @classmethod
    def file_extension(cls) -> str:
        return '.exe' if sublime.platform() == 'windows' else ''

    @classmethod
    def python_exe(cls) -> str:
        return 'python' if sublime.platform() == 'windows' else 'python3'

    @classmethod
    def run(cls, *args: Any, cwd: Optional[str] = None) -> str:
        output, error = run_command_sync(list(args), cwd=cwd)
        if error:
            raise Exception(error)
        return output

    def __init__(self, storage_path: str, package_name: str, requirements_path: str,
                 server_binary_filename: str) -> None:
        self._storage_path = storage_path
        self._package_name = package_name
        self._requirements_path = 'Packages/{}/{}'.format(self._package_name, requirements_path)
        self._server_binary_filename = server_binary_filename
        self._status = ServerStatus.UNINITIALIZED

    def basedir(self) -> str:
        return os.path.join(self._storage_path, self._package_name)

    def bindir(self) -> str:
        bin_dir = 'Scripts' if sublime.platform() == 'windows' else 'bin'
        return os.path.join(self.basedir(), bin_dir)

    def server_exe(self) -> str:
        return os.path.join(self.bindir(), self._server_binary_filename + self.file_extension())

    def pip_exe(self) -> str:
        return os.path.join(self.bindir(), 'pip' + self.file_extension())

    def python_version(self) -> str:
        return os.path.join(self.basedir(), 'python_version')

    # --- ServerResourceInterface handlers ----------------------------------------------------------------------------

    @property
    def binary_path(self) -> str:
        return self.server_exe()

    def needs_installation(self) -> bool:
        if os.path.exists(self.server_exe()) and os.path.exists(self.pip_exe()):
            if not os.path.exists(self.python_version()):
                return True
            with open(self.python_version(), 'r') as f:
                if f.readline().strip() != self.run(self.python_exe(), '--version').strip():
                    return True
            installed_requirements = parse_requirements(self.run(self.pip_exe(), 'freeze'))
            requirements = parse_requirements(ResourcePath(self._requirements_path).read_text())
            for name, version in requirements.items():
                if name not in installed_requirements:
                    # Has new requirement
                    return True
                if not version:
                    continue
                installed_version = installed_requirements.get(name)
                if version != installed_version:
                    return True
            self._status = ServerStatus.READY
            return False
        return True

    def install_or_update(self) -> None:
        shutil.rmtree(self.basedir(), ignore_errors=True)
        try:
            os.makedirs(self.basedir(), exist_ok=True)
            self.run(self.python_exe(), '-m', 'venv', self._package_name, cwd=self._storage_path)
            dest_requirements_txt_path = os.path.join(self._storage_path, self._package_name, 'requirements.txt')
            ResourcePath(self._requirements_path).copy(dest_requirements_txt_path)
            self.run(self.pip_exe(), 'install', '-r', dest_requirements_txt_path, '--disable-pip-version-check')
            with open(self.python_version(), 'w') as f:
                f.write(self.run(self.python_exe(), '--version'))
        except Exception:
            shutil.rmtree(self.basedir(), ignore_errors=True)
            raise
        self._status = ServerStatus.READY

    def get_status(self) -> int:
        return self._status
