from ..api_wrapper_interface import ApiWrapperInterface
from .interface import ClientHandlerInterface
from LSP.plugin.core.typing import Any, Callable, Iterable, List, Union
import inspect

__all__ = [
    "notification_handler",
    "request_handler",
    "register_decorated_handlers",
]

# the first argument is always "self"
T_HANDLER = Callable[[Any, Any], None]
T_SERVER_EVENTS = Union[str, Iterable[str]]

_HANDLER_MARKS = {
    "notification": "__handle_notification_events",
    "request": "__handle_request_events",
}


def notification_handler(server_events: T_SERVER_EVENTS) -> Callable[[T_HANDLER], T_HANDLER]:
    """ Marks the decorated function as a "notification" event handler. """

    return _create_handler("notification", server_events)


def request_handler(server_events: T_SERVER_EVENTS) -> Callable[[T_HANDLER], T_HANDLER]:
    """ Marks the decorated function as a "request" event handler. """

    return _create_handler("request", server_events)


def _create_handler(client_event: str, server_events: T_SERVER_EVENTS) -> Callable[[T_HANDLER], T_HANDLER]:
    """ Marks the decorated function as a event handler. """

    server_events = [server_events] if isinstance(server_events, str) else list(server_events)

    def decorator(func: T_HANDLER) -> T_HANDLER:
        setattr(func, _HANDLER_MARKS[client_event], server_events)
        return func

    return decorator


def register_decorated_handlers(client_handler: ClientHandlerInterface, api: ApiWrapperInterface) -> None:
    """
    Register decorator-style custom event handlers.

    This method works as following steps:

    1. Scan through all methods of the `client_handler`.
    2. If a method is decorated, it will has a "handler mark" attribute which is set by a decorator.
    3. Register the method with wanted events, which are stored in the "handler mark" attribute.

    :param api: The API instance for interacting with the server.
    """
    for _, func in inspect.getmembers(client_handler, predicate=inspect.isroutine):
        is_decorated = False  # indicates whether `func` is found decorated

        # client_event is like "notification", "request"
        for client_event, handler_mark in _HANDLER_MARKS.items():
            # it makes no sense that a handler handlers both "notification" and "request"
            # so we do early break once we've registered the handler for any event
            if is_decorated:
                break

            event_registrator = getattr(api, "on_" + client_event, None)
            if callable(event_registrator):
                try:
                    server_events = getattr(func, handler_mark)  # type: List[str]
                    for server_event in server_events:
                        event_registrator(server_event, func)
                    is_decorated = True
                except AttributeError:
                    pass
