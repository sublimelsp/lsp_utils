from LSP.plugin.core.typing import Any, Callable, Iterable, Union

__all__ = [
    "HANDLER_MARKS",
    "as_notification_handler",
    "as_request_handler",
]

# the first argument is always "self"
T_HANDLER = Callable[[Any, Any], None]
T_SERVER_EVENTS = Union[str, Iterable[str]]

HANDLER_MARKS = {
    "notification": "__handle_notification_events",
    "request": "__handle_request_events",
}


def as_notification_handler(server_events: T_SERVER_EVENTS) -> Callable[[T_HANDLER], T_HANDLER]:
    """ Marks the decorated function as a "notification" event handler. """

    return _as_handler("notification", server_events)


def as_request_handler(server_events: T_SERVER_EVENTS) -> Callable[[T_HANDLER], T_HANDLER]:
    """ Marks the decorated function as a "request" event handler. """

    return _as_handler("request", server_events)


def _as_handler(client_event: str, server_events: T_SERVER_EVENTS) -> Callable[[T_HANDLER], T_HANDLER]:
    """ Marks the decorated function as a event handler. """

    server_events = [server_events] if isinstance(server_events, str) else list(server_events)

    def decorator(func: T_HANDLER) -> T_HANDLER:
        setattr(func, HANDLER_MARKS[client_event], server_events)
        return func

    return decorator
