# type: ignore
from .._util import weak_method
from ..api_wrapper_interface import ApiWrapperInterface
from ..helpers import log_and_show_message
from ..server_resource_interface import ServerStatus
from .api_decorator import register_decorated_handlers
from .interface import ClientHandlerInterface
from functools import partial
from LSP.plugin import ClientConfig
from LSP.plugin import LanguageHandler
from LSP.plugin import Notification
from LSP.plugin import read_client_config
from LSP.plugin import Request
from LSP.plugin import Response
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.typing import Any, Callable, Dict
from sublime_lib import ActivityIndicator
from weakref import ref
import sublime

__all__ = ['ClientHandler']

ApiNotificationHandler = Callable[[Any], None]
ApiRequestHandler = Callable[[Any, Callable[[Any], None]], None]


class ApiWrapper(ApiWrapperInterface):
    def __init__(self, client: 'ref[LanguageHandler]'):
        self.__client = client

    # --- ApiWrapperInterface -----------------------------------------------------------------------------------------

    def on_notification(self, method: str, handler: Callable[[Any], None]) -> None:
        def handle_notification(weak_handler: ApiNotificationHandler, params: Any) -> None:
            weak_handler(params)

        client = self.__client()
        if client:
            client.on_notification(method, partial(handle_notification, weak_method(handler)))

    def on_request(self, method: str, handler: ApiRequestHandler) -> None:
        def on_response(weak_handler: ApiRequestHandler, params: Any, request_id: Any) -> None:
            weak_handler(params, lambda result: send_response(request_id, result))

        def send_response(request_id, result):
            client = self.__client()
            if client:
                client.send_response(Response(request_id, result))

        client = self.__client()
        if client:
            client.on_request(method, partial(on_response, weak_method(handler)))

    def send_notification(self, method: str, params: Any) -> None:
        client = self.__client()
        if client:
            client.send_notification(Notification(method, params))

    def send_request(self, method: str, params: Any, handler: Callable[[Any, bool], None]) -> None:
        client = self.__client()
        if client:
            client.send_request(
                Request(method, params), lambda result: handler(result, False), lambda result: handler(result, True))


class ClientHandler(LanguageHandler, ClientHandlerInterface):
    _setup_called = False

    # --- LanguageHandler handlers ------------------------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.get_displayed_name().lower()

    @classmethod
    def additional_variables(cls) -> Dict[str, str]:
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
        client_config = read_client_config(self.name, settings_dict, filepath)
        self.on_settings_changed(client_config.settings)
        return client_config

    @classmethod
    def on_start(cls, window: sublime.Window) -> bool:
        if cls.manages_server():
            server = cls.get_server()
            if server is None or server.get_status() != ServerStatus.READY:
                log_and_show_message('{}: Server not ready'.format(cls.get_displayed_name()))
                return False
        startup_view = window.active_view()
        workspace_folders = [WorkspaceFolder.from_path(folder) for folder in window.folders()]
        message = cls.is_allowed_to_start(window, startup_view, workspace_folders)
        if message:
            log_and_show_message('{}: {}'.format(cls.get_displayed_name(), message))
            return False
        return True

    def on_initialized(self, client) -> None:
        api = ApiWrapper(ref(client))
        register_decorated_handlers(self, api)
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
                log_and_show_message('{}: Error checking if server was installed: {}'.format(name, str(exception)))
                return

            def perform_install() -> None:
                try:
                    message = '{}: Installing server in path: {}'.format(name, cls.storage_path())
                    log_and_show_message(message, show_in_status=False)
                    with ActivityIndicator(sublime.active_window(), message):
                        server.install_or_update()
                    log_and_show_message('{}: Server installed. Sublime Text restart is required.'.format(name))
                except Exception as exception:
                    log_and_show_message('{}: Server installation error: {}'.format(name, str(exception)))

            sublime.set_timeout_async(perform_install)

    @classmethod
    def cleanup(cls) -> None:
        super().cleanup()
        cls._setup_called = False

    # --- Internals ---------------------------------------------------------------------------------------------------

    @classmethod
    def get_default_settings_schema(cls) -> Dict[str, Any]:
        return {
            'command': [],
            'enabled': True,
            'env': {},
            'experimental_capabilities': {},
            'initializationOptions': {},
            'languages': [],
            'settings': {},
        }

    def __init__(self):
        super().__init__()
        # Calling setup() also here as this might run before `plugin_loaded`.
        # Will be a no-op if already ran.
        # See https://github.com/sublimelsp/LSP/issues/899
        self.setup()
