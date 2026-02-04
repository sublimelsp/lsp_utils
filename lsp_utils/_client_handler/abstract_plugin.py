from __future__ import annotations
from ..api_wrapper_interface import ApiNotificationHandler
from ..api_wrapper_interface import ApiRequestHandler
from ..api_wrapper_interface import ApiWrapperInterface
from ..server_resource_interface import ServerStatus
from .api_decorator import register_decorated_handlers
from .interface import ClientHandlerInterface
from abc import ABCMeta
from functools import partial
from LSP.plugin import AbstractPlugin
from LSP.plugin import ClientConfig
from LSP.plugin import Notification
from LSP.plugin import register_plugin
from LSP.plugin import Request
from LSP.plugin import Response
from LSP.plugin import Session
from LSP.plugin import unregister_plugin
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.rpc import method2attr
from os import path
from typing import Any, Callable
from typing_extensions import override
from weakref import WeakMethod, ref
import sublime

__all__ = ['ClientHandler']


class ApiWrapper(ApiWrapperInterface):
    def __init__(self, plugin: 'ref[AbstractPlugin]'):
        self.__plugin = plugin

    def __session(self) -> Session | None:
        plugin = self.__plugin()
        return plugin.weaksession() if plugin else None

    # --- ApiWrapperInterface -----------------------------------------------------------------------------------------

    @override
    def on_notification(self, method: str, handler: ApiNotificationHandler) -> None:
        def handle_notification(weak_handler: WeakMethod[ApiNotificationHandler], params: Any) -> None:
            if handler := weak_handler():
                handler(params)

        plugin = self.__plugin()
        if plugin:
            setattr(plugin, method2attr(method), partial(handle_notification, WeakMethod(handler)))

    @override
    def on_request(self, method: str, handler: ApiRequestHandler) -> None:
        def send_response(request_id: Any, result: Any) -> None:
            session = self.__session()
            if session:
                session.send_response(Response(request_id, result))

        def on_response(weak_handler: WeakMethod[ApiRequestHandler], params: Any, request_id: Any) -> None:
            if handler := weak_handler():
                handler(params, lambda result: send_response(request_id, result))

        plugin = self.__plugin()
        if plugin:
            setattr(plugin, method2attr(method), partial(on_response, WeakMethod(handler)))

    @override
    def send_notification(self, method: str, params: Any) -> None:
        session = self.__session()
        if session:
            session.send_notification(Notification(method, params))

    @override
    def send_request(self, method: str, params: Any, handler: Callable[[Any, bool], None]) -> None:
        session = self.__session()
        if session:
            request: Request[Any, Any] = Request(method, params)
            session.send_request(request, lambda result: handler(result, False), lambda result: handler(result, True))

        else:
            handler(None, True)


class ClientHandler(AbstractPlugin, ClientHandlerInterface, metaclass=ABCMeta):
    """
    The base class for creating an LSP plugin.
    """

    # --- AbstractPlugin handlers -------------------------------------------------------------------------------------

    @classmethod
    @override
    def name(cls) -> str:
        return cls.get_displayed_name()

    @classmethod
    @override
    def configuration(cls) -> tuple[sublime.Settings, str]:
        return cls.read_settings()

    @classmethod
    @override
    def additional_variables(cls) -> dict[str, str]:
        return cls.get_additional_variables()

    @classmethod
    @override
    def needs_update_or_installation(cls) -> bool:
        if cls.manages_server():
            server = cls.get_server()
            return bool(server and server.needs_installation())
        return False

    @classmethod
    @override
    def install_or_update(cls) -> None:
        server = cls.get_server()
        if server:
            server.install_or_update()

    @classmethod
    @override
    def can_start(cls, window: sublime.Window, initiating_view: sublime.View,
                  workspace_folders: list[WorkspaceFolder], configuration: ClientConfig) -> str | None:
        if cls.manages_server():
            server = cls.get_server()
            if not server or server.get_status() == ServerStatus.ERROR:
                return "{}: Error installing server dependencies.".format(cls.package_name)
            if server.get_status() != ServerStatus.READY:
                return "{}: Server installation in progress...".format(cls.package_name)
        message = cls.is_allowed_to_start(window, initiating_view, workspace_folders, configuration)
        if message:
            return message
        # Lazily update command after server has initialized if not set manually by the user.
        if not configuration.command:
            configuration.command = cls.get_command()
        return None

    @classmethod
    @override
    def on_pre_start(cls, window: sublime.Window, initiating_view: sublime.View,
                     workspace_folders: list[WorkspaceFolder], configuration: ClientConfig) -> str | None:
        extra_paths = cls.get_additional_paths()
        if extra_paths:
            original_path_raw = configuration.env.get('PATH') or ''
            if isinstance(original_path_raw, str):
                original_paths = original_path_raw.split(path.pathsep)
            else:
                original_paths = original_path_raw
            # To fix https://github.com/TerminalFi/LSP-copilot/issues/163 ,
            # We don't want to add the same path multiple times whenever a new server session is created.
            # Note that additional paths should be prepended to the original paths.
            wanted_paths = [path for path in extra_paths if path not in original_paths]
            wanted_paths.extend(original_paths)
            configuration.env['PATH'] = path.pathsep.join(wanted_paths)
        return None

    # --- ClientHandlerInterface --------------------------------------------------------------------------------------

    @classmethod
    @override
    def setup(cls) -> None:
        register_plugin(cls)

    @classmethod
    @override
    def cleanup(cls) -> None:
        unregister_plugin(cls)

    # --- Internals ---------------------------------------------------------------------------------------------------

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        api = ApiWrapper(ref(self))  # type: ignore
        register_decorated_handlers(self, api)
        self.on_ready(api)
