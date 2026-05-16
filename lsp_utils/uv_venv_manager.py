from __future__ import annotations

from .constants import INSTALLING_MARKER_FILE
from .helpers import rmtree_ex
from .uv_runner import UvRunner
from hashlib import md5
from os import pathsep
from typing import final
from typing import TYPE_CHECKING
import sublime

if TYPE_CHECKING:
    from LSP.plugin import OnPreStartContext
    from pathlib import Path
    from sublime_lib import ResourcePath

__all__ = ['UvVenvManager']


PYPROJECT_TOML = 'pyproject.toml'
UV_LOCK = 'uv.lock'


def is_hash_equal(resource_path: ResourcePath, filesystem_path: Path) -> bool:
    if not resource_path.exists():
        # If source resource doesn't exist then return "equal" since we don't care about that file then.
        return True
    if not filesystem_path.exists():
        return False
    source_hash = md5(resource_path.read_bytes()).hexdigest()  # noqa: S324
    try:
        return source_hash == md5(filesystem_path.read_bytes()).hexdigest()  # noqa: S324
    except FileNotFoundError:
        pass
    return False


@final
class UvVenvManager:
    """Handles installation and update of dependencies specified in pyproject.toml."""

    @classmethod
    def on_pre_start_async(
        cls,
        context: OnPreStartContext,
        plugin_storage_path: Path,
        pyproject_directory_resource_path: ResourcePath,
        server_binary_name: str,
    ) -> None:
        """
        Initialize UvVenvManager for an LspPlugin.

        Automatically adds support for a root `server_path` package setting that defaults to `"auto"`, meaning
        that the package-managed server instance will be used. It can be overridden to use a custom server binary.

        Also extends the PATH to include the venv directory if the managed server instance is used.

        :param context: The plugin context.
        :param plugin_storage_path: The path to the plugin's storage (`cls.plugin_storage_path`).
        :param pyproject_directory_resource_path: The `ResourcePath` to the directory that contains the
            `pyproject.toml` file. Must have a `Packages/<package_name>/` prefix followed by the path to
            the directory containing `pyproject.toml` within the package.
        :param server_binary_name: The name of the binary used to start the server within the venv's
            `scripts/bin` directory.
        """
        if not context.configuration.server_path or context.configuration.server_path == 'auto':
            uv_venv_manager = UvVenvManager(plugin_storage_path, pyproject_directory_resource_path, server_binary_name)
            uv_venv_manager.install_async()
            path = context.configuration.env.get('PATH', '')
            context.configuration.env['PATH'] = f'{uv_venv_manager.venv_bin_path}{pathsep}{path}'
            context.variables['server_path'] = str(uv_venv_manager.venv_bin_path / server_binary_name)
        else:
            context.variables['server_path'] = context.configuration.server_path

    def __init__(
        self, plugin_storage_path: Path, pyproject_directory_resource_path: ResourcePath, server_binary_name: str,
    ) -> None:
        """
        Initialize UvVenvManager.

        :param plugin_storage_path: The path to the plugin's storage (`cls.plugin_storage_path`).
        :param pyproject_directory_resource_path: The resource path to the directory that contains the
            `pyproject.toml` file. Must have a `Packages/<package_name>/` prefix followed by the path to
            the directory containing `pyproject.toml` within the package.
        :param server_binary_name: The name of the binary used to start the server within the venv's
            `scripts/bin` directory.
        """
        if not (pyproject_directory_resource_path / PYPROJECT_TOML).exists():
            msg = f'Expected "{pyproject_directory_resource_path / PYPROJECT_TOML}" resource not found!'
            raise Exception(msg)
        self._source_resource_path = pyproject_directory_resource_path
        self._plugin_storage_path = plugin_storage_path
        self._server_binary_name = server_binary_name
        self._uv: UvRunner | None = None

    @property
    def venv_path(self) -> Path:
        return self._plugin_storage_path / '.venv'

    @property
    def venv_bin_path(self) -> Path:
        bin_dir = 'Scripts' if sublime.platform() == 'windows' else 'bin'
        return self.venv_path / bin_dir

    def install_async(self) -> None:
        installation_marker_file_path = self._plugin_storage_path / INSTALLING_MARKER_FILE
        source_pyproject_path = self._source_resource_path / PYPROJECT_TOML
        source_uv_lock_path = self._source_resource_path / UV_LOCK
        target_pyproject_path = self._plugin_storage_path / PYPROJECT_TOML
        target_uv_lock_path = self._plugin_storage_path / UV_LOCK
        installed_and_up_to_date = (
            not installation_marker_file_path.is_file()
            and self.venv_path.exists()
            and is_hash_equal(source_pyproject_path, target_pyproject_path)
            and is_hash_equal(source_uv_lock_path, target_uv_lock_path)
            and (self.venv_bin_path / self._server_binary_name).is_file()
        )
        if installed_and_up_to_date:
            return
        if not self._uv:
            self._uv = UvRunner()
        self._plugin_storage_path.mkdir(parents=True, exist_ok=True)
        installation_marker_file_path.open('w', encoding='utf-8').close()
        target_pyproject_path.unlink(missing_ok=True)
        target_uv_lock_path.unlink(missing_ok=True)
        rmtree_ex(self.venv_path, ignore_errors=True)
        source_pyproject_path.copy(target_pyproject_path)
        if source_uv_lock_path.exists():
            source_uv_lock_path.copy(target_uv_lock_path)
        self._uv.run_command('sync', '--frozen', cwd=str(self._plugin_storage_path))
        installation_marker_file_path.unlink()
