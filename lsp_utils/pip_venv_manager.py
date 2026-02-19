from __future__ import annotations

from .helpers import platform_program_file_extension
from .helpers import rmtree_ex
from .helpers import run_command_ex
from hashlib import md5
from pathlib import Path
from sublime_lib import ResourcePath
from typing import final
import sublime

__all__ = ['PipVenvManager']


@final
class PipVenvManager:
    """Handles installation and update of resources specified in provided pip requirements list."""

    def __init__(self, venv_path: Path, requirements_path: str, python_binary: str) -> None:
        """
        PipVenvManager initializer.

        :param venv_path:         The path where the resources should be installed.
        :param requirements_path: The path to the `requirements.txt` file, relative to the `Packages/` directory.
                                  If the package `LSP-foo` has a `requirements.txt` file at the root then the path
                                  should be `LSP-foo/requirements.txt`.
        :param python_binary:     The file name or a full path to the python binary. Defaults to py, python or python3
                                  depending on the platform.
        """
        self._venv_path = venv_path
        self._requirements_resource_path = f'Packages/{requirements_path}'
        self._python_binary = python_binary

    @property
    def venv_path(self) -> Path:
        return self._venv_path

    @property
    def venv_bin_path(self) -> Path:
        bin_dir = 'Scripts' if sublime.platform() == 'windows' else 'bin'
        return self.venv_path.joinpath(bin_dir)

    @property
    def _venv_pip_binary(self) -> Path:
        return self.venv_bin_path.joinpath('pip' + platform_program_file_extension())

    @property
    def _python_version_path(self) -> Path:
        return self.venv_path.joinpath('python_version')

    def needs_install_or_update(self) -> bool:
        if not Path(self._venv_pip_binary).exists():
            return True
        if not Path(self._python_version_path).exists():
            return True
        with Path(self._python_version_path).open(encoding='utf-8') as f:
            if f.readline().strip() != run_command_ex(self._python_binary, '--version').strip():
                return True
        src_requirements_resource = ResourcePath(self._requirements_resource_path)
        if not src_requirements_resource.exists():
            msg = f'Missing required "requirements.txt" in {self._requirements_resource_path}'
            raise Exception(msg)
        src_requirements_hash = md5(src_requirements_resource.read_bytes()).hexdigest()  # noqa: S324
        try:
            with (self.venv_path / 'requirements.txt').open('rb') as file:
                dst_requirements_hash = md5(file.read()).hexdigest()  # noqa: S324
            if src_requirements_hash != dst_requirements_hash:
                return True
        except FileNotFoundError:
            # Needs to be re-installed.
            return True
        return False

    def install(self) -> None:
        rmtree_ex(self.venv_path, ignore_errors=True)
        Path(self.venv_path).mkdir(exist_ok=True, parents=True)
        run_command_ex(self._python_binary, '-m', 'venv', str(self._venv_path))
        dest_requirements_txt_path = self._venv_path / 'requirements.txt'
        ResourcePath(self._requirements_resource_path).copy(dest_requirements_txt_path)
        run_command_ex(
            self._venv_pip_binary, 'install', '-r', dest_requirements_txt_path, '--disable-pip-version-check')
        Path(self._python_version_path).write_text(run_command_ex(self._python_binary, '--version'), encoding='utf-8')
