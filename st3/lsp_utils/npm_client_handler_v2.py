from .server_npm_resource import ServerNpmResource
from LSP.plugin import AbstractPlugin
from LSP.plugin import ClientConfig
from LSP.plugin import Response
from LSP.plugin import Session
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.rpc import method2attr
from LSP.plugin.core.typing import Callable, Dict, List, Optional, Tuple
import shutil
import sublime
import weakref

# Keys to read and their fallbacks.
CLIENT_SETTING_KEYS = {
    'env': {},
    'experimental_capabilities': {},
    'languages': [],
    'initializationOptions': {},
    'settings': {},
}  # type: ignore


class ApiWrapper(object):
    def __init__(self, plugin: AbstractPlugin):
        self.__plugin = plugin

    def on_notification(self, method: str, handler: Callable) -> None:
        setattr(self.__plugin, method2attr(method), lambda params: handler(params))

    def on_request(self, method: str, handler: Callable) -> None:
        def send_response(request_id, result):
            session = self.__plugin.weaksession()
            if session:
                session.send_response(Response(request_id, result))

        def on_response(params, request_id):
            handler(params, lambda result: send_response(request_id, result))

        setattr(self.__plugin, method2attr(method), on_response)


class NpmClientHandler(AbstractPlugin):
    package_name = ''  # type: str
    server_directory = ''  # type: str
    server_binary_path = ''  # type: str
    # Internal
    __server = None  # type: ServerNpmResource

    @classmethod
    def setup(cls) -> None:
        if not cls.package_name:
            print('ERROR: [lsp_utils] package_name is required to instantiate an instance of {}'.format(cls))
            return
        if not cls.__server:
            cls.__server = ServerNpmResource(cls.package_name, cls.server_directory, cls.server_binary_path)
            cls.__server.setup()

    @classmethod
    def cleanup(cls) -> None:
        if cls.__server:
            cls.__server.cleanup()

    @classmethod
    def name(cls) -> str:
        return cls.package_name

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        return False

    @classmethod
    def install_or_update(cls) -> None:
        pass

    @classmethod
    def configuration(cls) -> Tuple[sublime.Settings, str]:
        cls.setup()
        name = cls.name()
        basename = "{}.sublime-settings".format(name)
        filepath = "Packages/{}/{}".format(name, basename)
        settings = sublime.load_settings(basename)
        settings.set('enabled', True)
        settings.set('command', ['node', cls.__server.binary_path] + cls.get_binary_arguments())
        cls.on_settings_read(settings)
        # Read into a dict so we can call old API "on_client_configuration_ready" and then
        # resave potentially changed values.
        settings_dict = {}
        for key, default in CLIENT_SETTING_KEYS.items():
            settings_dict[key] = settings.get(key, default)
        cls.on_client_configuration_ready(settings_dict)
        for key in CLIENT_SETTING_KEYS.keys():
            settings.set(key, settings_dict[key])

        return settings, filepath

    @classmethod
    def get_binary_arguments(cls):
        """
        Returns a list of extra arguments to append when starting server.
        """
        return ['--stdio']

    @classmethod
    def on_settings_read(cls, settings: sublime.Settings):
        """
        Called when package settings were read. Receives a `sublime.Settings` object.

        Can be used to change user settings, migrating them to new schema, for example.

        Return True if settings were modified to save changes to file.
        """
        return False

    @classmethod
    def on_client_configuration_ready(cls, configuration: Dict) -> None:
        """
        Called with default configuration object that contains merged default and user settings.

        Can be used to alter default configuration before registering it.
        """
        pass

    @classmethod
    def can_start(cls, window: sublime.Window, initiating_view: sublime.View,
                  workspace_folders: List[WorkspaceFolder], configuration: ClientConfig) -> Optional[str]:
        if shutil.which('node') is None:
            return "{}: Please install Node.js for the server to work.".format(cls.package_name)
        if not cls.__server or not cls.__server.ready:
            return "{}: Server installation in progress.".format(cls.package_name)
        return None

    def __init__(self, weaksession: 'weakref.ref[Session]') -> None:
        super().__init__(weaksession)
        if not self.package_name:
            return
        self.on_ready(ApiWrapper(self))

    def on_ready(self, api: ApiWrapper) -> None:
        pass
