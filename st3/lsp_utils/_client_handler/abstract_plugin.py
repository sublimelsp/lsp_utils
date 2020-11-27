from ..api_wrapper_interface import ApiWrapperInterface
from ..server_resource_interface import ServerStatus
from .api_decorator import register_decorated_handlers
from .interface import ClientHandlerInterface
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
from LSP.plugin.core.typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict
import sublime
import weakref

__all__ = ['ClientHandler']

LanguagesDict = TypedDict('LanguagesDict', {
    'document_selector': Optional[str],
    'languageId': Optional[str],
    'scopes': Optional[List[str]],
    'syntaxes': Optional[List[str]],
}, total=False)


class ApiWrapper(ApiWrapperInterface):
    def __init__(self, plugin: AbstractPlugin):
        self.__plugin = plugin

    # --- ApiWrapperInterface -----------------------------------------------------------------------------------------

    def on_notification(self, method: str, handler: Callable[[Any], None]) -> None:
        setattr(self.__plugin, method2attr(method), lambda params: handler(params))

    def on_request(self, method: str, handler: Callable[[Any, Callable[[Any], None]], None]) -> None:
        def send_response(request_id: Any, result: Any) -> None:
            session = self.__plugin.weaksession()
            if session:
                session.send_response(Response(request_id, result))

        def on_response(params: Any, request_id: Any) -> None:
            handler(params, lambda result: send_response(request_id, result))

        setattr(self.__plugin, method2attr(method), on_response)

    def send_notification(self, method: str, params: Any) -> None:
        session = self.__plugin.weaksession()
        if session:
            session.send_notification(Notification(method, params))

    def send_request(self, method: str, params: Any, handler: Callable[[Any, bool], None]) -> None:
        session = self.__plugin.weaksession()
        if session:
            session.send_request(
                Request(method, params), lambda result: handler(result, False), lambda result: handler(result, True))
        else:
            handler(None, True)


class ClientHandler(AbstractPlugin, ClientHandlerInterface):
    """
    The base class for creating an LSP plugin.
    """

    # --- AbstractPlugin handlers -------------------------------------------------------------------------------------

    @classmethod
    def name(cls) -> str:
        return cls.get_displayed_name()

    @classmethod
    def configuration(cls) -> Tuple[sublime.Settings, str]:
        return cls.read_settings()

    @classmethod
    def additional_variables(cls) -> Dict[str, str]:
        return cls.get_additional_variables()

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        if cls.manages_server():
            server = cls.get_server()
            return bool(server and server.needs_installation())
        return False

    @classmethod
    def install_or_update(cls) -> None:
        server = cls.get_server()
        if server:
            server.install_or_update()

    @classmethod
    def can_start(cls, window: sublime.Window, initiating_view: sublime.View,
                  workspace_folders: List[WorkspaceFolder], configuration: ClientConfig) -> Optional[str]:
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

    # --- ClientHandlerInterface --------------------------------------------------------------------------------------

    @classmethod
    def setup(cls) -> None:
        super().setup()
        register_plugin(cls)

    @classmethod
    def cleanup(cls) -> None:
        unregister_plugin(cls)
        super().cleanup()

    @classmethod
    def get_default_settings_schema(cls) -> Dict[str, Any]:
        return {
            'auto_complete_selector': '',
            'command': [],
            'env': {},
            'experimental_capabilities': {},
            'ignore_server_trigger_chars': False,
            'initializationOptions': {},
            'languages': [],
            'settings': {},
        }

    @classmethod
    def get_storage_path(cls) -> str:
        return cls.storage_path()

    @classmethod
    def on_settings_read_internal(cls, settings: sublime.Settings) -> None:
        settings.set('enabled', True)
        languages = settings.get('languages', None)  # type: Optional[List[LanguagesDict]]
        if languages:
            settings.set('languages', cls._upgrade_languages_list(languages))

    # --- Internals ---------------------------------------------------------------------------------------------------

    @classmethod
    def _upgrade_languages_list(cls, languages: List[LanguagesDict]) -> List[LanguagesDict]:
        upgraded_list = []
        for language in languages:
            if 'document_selector' in language:
                language.pop('scopes', None)
                language.pop('syntaxes', None)
                upgraded_list.append(language)
            elif 'scopes' in language:
                upgraded_list.append({
                    'languageId': language.get('languageId'),
                    'document_selector': ' | '.join(language['scopes'] or []),
                })
            else:
                upgraded_list.append(language)
        return upgraded_list

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        api = ApiWrapper(self)
        register_decorated_handlers(self, api)
        self.on_ready(api)
