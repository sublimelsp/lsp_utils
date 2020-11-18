from ..api_wrapper_interface import ApiWrapperInterface
from ..helpers import log_and_show_message
from ..server_resource_interface import ServerStatus
from .decorator import HANDLER_MARKS
from .interface import ClientHandlerInterface
from LSP.plugin import ClientConfig
from LSP.plugin import LanguageHandler
from LSP.plugin import Notification
from LSP.plugin import read_client_config
from LSP.plugin import Request
from LSP.plugin import Response
from LSP.plugin.core.typing import Any, Callable, Dict, List, Optional
from sublime_lib import ActivityIndicator
import inspect
import sublime

__all__ = ['ClientHandler']


class ApiWrapper(ApiWrapperInterface):
    def __init__(self, client):
        self.__client = client

    # --- ApiWrapperInterface -----------------------------------------------------------------------------------------

    def on_notification(self, method: str, handler: Callable[[Any], None]) -> None:
        self.__client.on_notification(method, handler)

    def on_request(self, method: str, handler: Callable[[Any, Callable[[Any], None]], None]) -> None:
        def on_response(params, request_id):
            handler(params, lambda result: send_response(request_id, result))

        def send_response(request_id, result):
            self.__client.send_response(Response(request_id, result))

        self.__client.on_request(method, on_response)

    def send_notification(self, method: str, params: Any) -> None:
        self.__client.send_notification(Notification(method, params))

    def send_request(self, method: str, params: Any, handler: Callable[[Any, bool], None]) -> None:
        self.__client.send_request(
            Request(method, params), lambda result: handler(result, False), lambda result: handler(result, True))


class ClientHandler(LanguageHandler, ClientHandlerInterface):
    _setup_called = False

    # --- LanguageHandler handlers ------------------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.get_displayed_name().lower()

    @classmethod
    def additional_variables(cls) -> Optional[Dict[str, str]]:
        return cls.get_additional_variables()

    @property
    def config(self) -> ClientConfig:
        settings, filepath = self.read_settings()
        settings_dict = {}
        for key, default in self.get_default_settings_schema().items():
            settings_dict[key] = settings.get(key, default)
        if self.manages_server():
            can_enable = self.get_server() is not None
        else:
            can_enable = True
        enabled = settings_dict.get('enabled', True) and can_enable
        settings_dict['enabled'] = enabled
        if not settings_dict['command']:
            settings_dict['command'] = self.get_command()
        return read_client_config(self.name, settings_dict, filepath)

    @classmethod
    def on_start(cls, window: sublime.Window) -> bool:
        if cls.manages_server():
            server = cls.get_server()
            return server is not None and server.get_status() == ServerStatus.READY
        message = cls.is_allowed_to_start(window)
        if message:
            window.status_message('{}: {}'.format(cls.package_name, message))
            return False
        return True

    def on_initialized(self, client) -> None:
        api = ApiWrapper(client)
        self._register_decorated_handlers(api)
        self.on_ready(api)

    # --- ClientHandlerInterface --------------------------------------------------------------------------------------

    @classmethod
    def setup(cls) -> None:
        if cls._setup_called:
            return
        cls._setup_called = True
        super().setup()
        if cls.manages_server():
            name = cls.package_name
            server = cls.get_server()
            if not server:
                return
            try:
                if not server.needs_installation():
                    return
            except Exception as exception:
                log_and_show_message('{}: Error checking if server was installed: {}'.format(name), str(exception))
                return

            def perform_install() -> None:
                try:
                    message = '{}: Installing server in path: {}'.format(name, cls.get_storage_path())
                    log_and_show_message(message, show_in_status=False)
                    with ActivityIndicator(sublime.active_window(), message):
                        server.install_or_update()
                    log_and_show_message('{}: Server installed. Sublime Text restart is required.'.format(name))
                except Exception as exception:
                    log_and_show_message('{}: Server installation error: {}'.format(name), str(exception))

            sublime.set_timeout_async(perform_install)

    @classmethod
    def cleanup(cls) -> None:
        super().cleanup()
        cls._setup_called = False

    @classmethod
    def get_default_settings_schema(cls) -> Dict[str, Any]:
        return {
            'command': [],
            'env': {},
            'experimental_capabilities': {},
            'initializationOptions': {},
            'languages': [],
            'settings': {},
        }

    @classmethod
    def get_storage_path(cls) -> str:
        return cls.storage_path()

    # --- Internals ---------------------------------------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        # Calling setup() also here as this might run before `plugin_loaded`.
        # Will be a no-op if already ran.
        # See https://github.com/sublimelsp/LSP/issues/899
        self.setup()

    def _register_decorated_handlers(self, api: ApiWrapperInterface) -> None:
        """
        Register decorator-style custom event handlers.

        This method works as following steps:

        1. Scan through all methods of this object.
        2. If a method is decorated, it will has a "handler mark" attribute which is put by the decorator.
        3. Register the method with wanted events, which are stored in the "handler mark" attribute.

        :param api: The API instance for interacting with the server.
        """
        for _, func in inspect.getmembers(self, predicate=inspect.isroutine):
            # client_event is like "notification", "request"
            for client_event, handler_mark in HANDLER_MARKS.items():
                event_registrator = getattr(api, "on_" + client_event, None)
                if callable(event_registrator):
                    server_events = getattr(func, handler_mark, [])  # type: List[str]
                    for server_event in server_events:
                        event_registrator(server_event, func)
