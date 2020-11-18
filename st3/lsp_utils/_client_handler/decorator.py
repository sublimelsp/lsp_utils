from ..api_wrapper_interface import ApiWrapperInterface
from .interface import ClientHandlerInterface
from LSP.plugin.core.typing import Any, Callable, List, Optional, Union
import inspect

__all__ = [
    "notification_handler",
    "request_handler",
    "register_decorated_handlers",
]

# the first argument is always "self"
T_Handler = Callable[[Any, Any], None]
T_MessageMethods = Union[str, List[str]]

_HANDLER_MARKS = {
    "notification": "__handle_notification_events",
    "request": "__handle_request_events",
}


def notification_handler(notification_methods: T_MessageMethods) -> Callable[[T_Handler], T_Handler]:
    """ Marks the decorated function as a "notification" message handler. """

    return _create_handler("notification", notification_methods)


def request_handler(request_methods: T_MessageMethods) -> Callable[[T_Handler], T_Handler]:
    """ Marks the decorated function as a "request" message handler. """

    return _create_handler("request", request_methods)


def _create_handler(client_event: str, message_methods: T_MessageMethods) -> Callable[[T_Handler], T_Handler]:
    """ Marks the decorated function as a message handler. """

    message_methods = [message_methods] if isinstance(message_methods, str) else message_methods

    def decorator(func: T_Handler) -> T_Handler:
        setattr(func, _HANDLER_MARKS[client_event], message_methods)
        return func

    return decorator


def register_decorated_handlers(client_handler: ClientHandlerInterface, api: ApiWrapperInterface) -> None:
    """
    Register decorator-style custom message handlers.

    This method works as following steps:

    1. Scan through all methods of `client_handler`.
    2. If a method is decorated, it will has a "handler mark" attribute which is set by the decorator.
    3. Register the method with wanted message methods, which are stored in the "handler mark" attribute.

    :param api: The API instance for interacting with the server.
    """
    for _, func in inspect.getmembers(client_handler, predicate=inspect.isroutine):
        for client_event, handler_mark in _HANDLER_MARKS.items():
            message_methods = getattr(func, handler_mark, None)  # type: Optional[List[str]]
            if message_methods is None:
                continue

            event_registrator = getattr(api, "on_" + client_event, None)
            if callable(event_registrator):
                for message_method in message_methods:
                    event_registrator(message_method, func)

                # it makes no sense that a handler handlers both "notification" and "request"
                # so we do early break once we've registered a handler
                break
