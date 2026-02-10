from __future__ import annotations
from .helpers import platform_program_file_extension, rmtree_ex
from .uv_runner import UvRunner
from hashlib import md5
from pathlib import Path
from sublime_lib import ResourcePath
from typing import final
import sublime


__all__ = ['UvVenvManager']


PYPROJECT_TOML = 'pyproject.toml'
UV_LOCK = 'uv.lock'


def is_hash_equal(resource_path: ResourcePath, filesystem_path: Path) -> bool:
    if not resource_path.exists():
        # If source resource doesn't exist then return "equal" since we don't care about that file then.
        return True
    if not filesystem_path.exists():
        return False
    source_hash = md5(resource_path.read_bytes()).hexdigest()
    try:
        return source_hash == md5(filesystem_path.read_bytes()).hexdigest()
    except FileNotFoundError:
        pass
    return False


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

        pyproject_toml_resource_path = ResourcePath(f'Packages/{package_name}/{project_toml_resource_path}')
        if not pyproject_toml_resource_path.exists():
            raise Exception(f'Expected "{project_toml_resource_path}" resource not found!')
        self._source_resource_path = pyproject_toml_resource_path.parent
        self._storage_path = storage_path
        self._package_storage = Path(self._storage_path, package_name)
        self._uv: UvRunner | None = None

    @property
    def venv_path(self) -> Path:
        return self._package_storage / '.venv'

    @property
    def venv_bin_path(self) -> Path:
        bin_dir = 'Scripts' if sublime.platform() == 'windows' else 'bin'
        return self.venv_path / bin_dir

    @property
    def venv_python_path(self) -> Path:
        return self.venv_bin_path / f'python{platform_program_file_extension()}'

    def needs_install_or_update(self) -> bool:
        return not self.venv_path.exists() or \
            not is_hash_equal(self._source_resource_path / PYPROJECT_TOML, self._package_storage / PYPROJECT_TOML) or \
            not is_hash_equal(self._source_resource_path / UV_LOCK, self._package_storage / UV_LOCK)

    def install(self) -> None:
        if not self._uv:
            self._uv = UvRunner(self._storage_path)
        (self._package_storage / PYPROJECT_TOML).unlink(missing_ok=True)
        (self._package_storage / UV_LOCK).unlink(missing_ok=True)
        rmtree_ex(self.venv_path, ignore_errors=True)
        self._package_storage.mkdir(parents=True, exist_ok=True)
        (self._source_resource_path / PYPROJECT_TOML).copy(str(self._package_storage / PYPROJECT_TOML))
        if (self._source_resource_path / UV_LOCK).exists():
            (self._source_resource_path / UV_LOCK).copy(self._package_storage / UV_LOCK)
        self._uv.run_command('sync', cwd=str(self._package_storage))
