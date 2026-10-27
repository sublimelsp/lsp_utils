from __future__ import annotations

from ._install_dirs import InstallDirectory
from .constants import INSTALLING_MARKER_FILE
from .helpers import prepend_to_path
from .uv_runner import get_uv_id
from .uv_runner import UvRunner
from contextlib import suppress
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
        if hasattr(context.configuration, 'root_settings'):
            server_path = context.configuration.root_settings.get('server_path')
        elif hasattr(context.configuration, 'server_path'):
            server_path = context.configuration.server_path
        else:
            server_path = 'auto'
        if not server_path or server_path == 'auto':
            uv_venv_manager = UvVenvManager(plugin_storage_path, pyproject_directory_resource_path, server_binary_name)
            uv_venv_manager.install_async()
            context.configuration.env['PATH'] = prepend_to_path(
                context.configuration.env.get('PATH'), [str(uv_venv_manager.venv_bin_path)])
            context.variables['server_path'] = str(uv_venv_manager.venv_bin_path / server_binary_name)
        else:
            context.variables['server_path'] = server_path

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
        source_uv_lock_path = pyproject_directory_resource_path / UV_LOCK
        self._install_dir = InstallDirectory(
            plugin_storage_path,
            f'{pyproject_directory_resource_path.name}-venv',
            (pyproject_directory_resource_path / PYPROJECT_TOML).read_bytes(),
            source_uv_lock_path.read_bytes() if source_uv_lock_path.exists() else b'',
            get_uv_id(),
            legacy_dirs=[plugin_storage_path / '.venv'],
        )
        self._uv: UvRunner | None = None

    @property
    def venv_path(self) -> Path:
        """
        The path to the venv.

        Depends on the contents of `pyproject.toml` and `uv.lock` and on the version of uv so changes when those are
        updated.
        """
        return self._install_dir.path / '.venv'

    @property
    def venv_bin_path(self) -> Path:
        bin_dir = 'Scripts' if sublime.platform() == 'windows' else 'bin'
        return self.venv_path / bin_dir

    def install_async(self) -> None:
        source_pyproject_path = self._source_resource_path / PYPROJECT_TOML
        source_uv_lock_path = self._source_resource_path / UV_LOCK

        def install(target_path: Path) -> None:
            if not self._uv:
                self._uv = UvRunner()
            source_pyproject_path.copy(target_path / PYPROJECT_TOML)
            if source_uv_lock_path.exists():
                source_uv_lock_path.copy(target_path / UV_LOCK)
            self._uv.run_command('sync', '--frozen', cwd=str(target_path))
            bin_path = self.venv_bin_path
            binary_name = self._server_binary_name
            if not (bin_path / binary_name).is_file() and not (bin_path / f'{binary_name}.exe').is_file():
                msg = f'Expected "{binary_name}" binary not found in "{bin_path}" after installation'
                raise RuntimeError(msg)

        self._install_dir.install(install)
        self._remove_legacy_files()

    def _remove_legacy_files(self) -> None:
        # Older lsp_utils versions installed directly into the plugin storage. Remove the remaining files once the
        # legacy venv itself is removed.
        if (self._plugin_storage_path / '.venv').exists():
            return
        for filename in (PYPROJECT_TOML, UV_LOCK, INSTALLING_MARKER_FILE):
            with suppress(OSError):
                (self._plugin_storage_path / filename).unlink(missing_ok=True)
