from __future__ import annotations
from .helpers import platform_program_file_extension
from .uv_runner import UvRunner
from hashlib import md5
from pathlib import Path
from sublime_lib import ResourcePath
from typing import final
import sublime


__all__ = ['UvVenvManager']


@final
class UvVenvManager:
    """
    Handles installation and update of dependencies specified in pyproject.toml.
    """

    def __init__(self, package_name: str, project_toml_resource_path: str, storage_path: Path) -> None:
        """
        :param package_name:               The name of the package that uses this manager.
        :param project_toml_resource_path: The resource path to the `pyproject.toml` file, relative to the
                                           package's directory. If the package `LSP-foo` has a `pyproject.toml` file
                                           inside the `dep` directory then the path should be `dep/pyproject.toml`.
        :param storage_path:               The path of the Package Storage directory.
        """

        self._package_name = package_name
        self._project_toml_resource_path = project_toml_resource_path
        self._storage_path = storage_path
        self._package_storage = Path(self._storage_path, self._package_name)
        self._target_project_toml_path = self._package_storage / 'pyproject.toml'
        self._target_venv_path = self._package_storage / '.venv'
        self._uv: UvRunner | None = None

    @property
    def venv_python_path(self) -> Path:
        bin_dir = 'Scripts' if sublime.platform() == 'windows' else 'bin'
        return self._target_venv_path / bin_dir / f'python{platform_program_file_extension()}'

    @property
    def _source_project_toml_resource(self) -> ResourcePath:
        resource = ResourcePath(f'Packages/{self._package_name}/{self._project_toml_resource_path}')
        if not resource.exists():
            raise Exception(f'Expected "{self._project_toml_resource_path}" resource not found!')
        return resource

    def needs_install_or_update(self) -> bool:
        source_hash = md5(self._source_project_toml_resource.read_bytes()).hexdigest()
        try:
            with self._target_project_toml_path.open('rb') as file:
                target_hash = md5(file.read()).hexdigest()
        except FileNotFoundError:
            return True
        return source_hash != target_hash or not self._target_venv_path.exists()

    def install(self) -> None:
        if not self._uv:
            self._uv = UvRunner(self._storage_path)
        if self._target_project_toml_path.exists():
            self._target_project_toml_path.unlink()
        self._source_project_toml_resource.copy(str(self._target_project_toml_path))
        self._uv.run_command('sync', cwd=str(self._package_storage))
