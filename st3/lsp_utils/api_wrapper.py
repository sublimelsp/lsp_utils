from abc import ABCMeta, abstractmethod
from LSP.plugin.core.typing import Any, Callable, Optional


class ApiWrapperInterface(metaclass=ABCMeta):

    @abstractmethod
    def on_notification(self, method: str, handler: Callable) -> None:
        pass

    @abstractmethod
    def on_request(self, method: str, handler: Callable) -> None:
        pass

    @abstractmethod
    def send_notification(self, method: str, params: Any) -> None:
        pass

    @abstractmethod
    def send_request(self, method: str, params: Any, handler: Callable[[Optional[str], bool], None]) -> None:
        pass
