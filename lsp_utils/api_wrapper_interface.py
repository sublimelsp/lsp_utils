from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Any
from typing import Callable

__all__ = [
    'ApiWrapperInterface',
]


class ApiWrapperInterface(ABC):
    """
    An interface for sending and receiving requests and notifications from and to the server.

    An implementation of it is available through the :func:`GenericClientHandler.on_ready()` override.
    """

    @abstractmethod
    def send_notification(self, method: str, params: Any) -> None:
        """Send a notification to the server."""
        ...

    @abstractmethod
    def send_request(self, method: str, params: Any, handler: Callable[[Any, bool], None]) -> None:
        """
        Send a request to the server.

        The handler will be called with the result received from the server and
        a boolean value `False` if request has succeeded and `True` if it returned an error.
        """
        ...
