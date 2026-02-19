from __future__ import annotations

from .helpers import platform_program_file_extension
from .pip_venv_manager import PipVenvManager
from .server_resource_interface import ServerResourceInterface
from .server_resource_interface import ServerStatus
from pathlib import Path
from typing import final
from typing_extensions import override

__all__ = ['ServerPipResource']


@final
class ServerPipResource(ServerResourceInterface):
    """
    Implements server management for pip-based servers.

    Handles installation and updates of the server in the package storage.

    :param storage_path: The path to the package storage (pass :meth:`lsp_utils.GenericClientHandler.storage_path()`)
    :param package_name: The package name (used as a directory name for storage)
    :param requirements_path: The path to the `requirements.txt` file, relative to the package directory.
           If the package `LSP-foo` has a `requirements.txt` file at the root then the path will be `requirements.txt`.
           Use forward slashes regardless of the platform.
    :param server_binary_filename: The name of the file used to start the server.
    """

    def __init__(self, storage_path: str, package_name: str, requirements_path: str,
                 server_binary_filename: str, python_binary: str) -> None:
        target_path = Path(storage_path, package_name)
        requirements_resource_path = f'{package_name}/{requirements_path}'
        self._pip_venv_manager = PipVenvManager(target_path, requirements_resource_path, python_binary)
        self._server_binary_filename = server_binary_filename
        self._status = ServerStatus.UNINITIALIZED

    def _server_binary(self) -> Path:
        return self._pip_venv_manager.venv_bin_path / (self._server_binary_filename + platform_program_file_extension())

    # --- ServerResourceInterface handlers ----------------------------------------------------------------------------

    @property
    @override
    def binary_path(self) -> str:
        return str(self._server_binary())

    @override
    def get_status(self) -> int:
        return self._status

    @override
    def needs_installation(self) -> bool:
        if self._pip_venv_manager.needs_install_or_update() or not self._server_binary().exists():
            return True
        self._status = ServerStatus.READY
        return False

    @override
    def install_or_update(self) -> None:
        try:
            self._pip_venv_manager.install()
        except Exception as error:
            self._status = ServerStatus.ERROR
            msg = f'Error installing the server:\n{error}'
            raise Exception(msg) from error
        self._status = ServerStatus.READY
