from .helpers import SemanticVersion
from abc import ABCMeta
from abc import abstractmethod
from abc import abstractproperty
from LSP.plugin.core.typing import Dict

__all__ = ['ServerStatus', 'ServerResourceInterface']


class ServerStatus():
    """
    A :class:`ServerStatus` enum for use as a return value from :func:`ServerResourceInterface.get_status()`.
    """

    UNINITIALIZED = 1
    """Initial status of the server."""
    ERROR = 2
    """Initiallation or update has failed."""
    READY = 3
    """Server is ready to provide resources."""


class ServerResourceInterface(metaclass=ABCMeta):
    """
    An interface for implementating server resource handlers. Use this interface in plugins that manage their own
    server binary (:func:`GenericClientHandler.manages_server` returns `True`).

    After implementing this interface, return an instance of implemented class from
    :meth:`GenericClientHandler.get_server()`.
    """

    @abstractmethod
    def needs_installation(self) -> bool:
        """
        This is the place to check whether the binary needs an update, or whether it needs to be installed before
        starting the language server.

        :returns: `True` if the server needs to be installed or updated. This will result in calling
                  :meth:`install_or_update()`.
        :rtype: bool
        """
        ...

    @abstractmethod
    def install_or_update_sync(self) -> None:
        """
        Do the actual update/installation of the server binary. Synchronous variant.
        """
        ...

    @abstractmethod
    def install_or_update_async(self) -> None:
        """
        Do the actual update/installation of the server binary. Asynchronous variant.
        """
        ...

    @abstractmethod
    def get_status(self) -> int:
        """
        Determines the current status of the server. The state changes as the server is being installed, updated or
        runs into an error doing those.

        :returns: A number corresponding to the :class:`ServerStatus` class members.
        """
        ...

    @abstractproperty
    def binary_path(self) -> str:
        """
        Returns a filesystem path to the server binary.
        """
        ...

    @abstractproperty
    def server_directory_path(self) -> str:
        """
        Returns a filesystem path to the server directory.
        """
        ...
