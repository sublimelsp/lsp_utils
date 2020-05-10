from .server_npm_resource import ServerNpmResource
from LSP.plugin.core.typing import Callable, Dict, List, Optional
import shutil
import sublime

USE_NEW_API = True

try:

    from LSP.plugin import ClientConfig
    from LSP.plugin import read_client_config
    from LSP.plugin import Response
    from LSP.plugin import Session
    from LSP.plugin import WorkspaceFolder
    from LSP.plugin.core.rpc import method2attr  # temporary
    BaseClass = Session

except ImportError:

    USE_NEW_API = False
    from LSP.plugin.core.handlers import LanguageHandler
    from LSP.plugin.core.protocol import Response
    from LSP.plugin.core.protocol import WorkspaceFolder
    from LSP.plugin.core.settings import ClientConfig
    from LSP.plugin.core.settings import read_client_config
    BaseClass = LanguageHandler


# Keys to read and their fallbacks.
CLIENT_SETTING_KEYS = {
    'env': {},
    'experimental_capabilities': {},
    'languages': [],
    'initializationOptions': {},
    'settings': {},
}  # type: ignore


class ApiWrapper:

    def __init__(self, client):
        self.__client = client

    def on_notification(self, method: str, handler: Callable) -> None:
        if USE_NEW_API:
            setattr(self.__client, method2attr(method), handler)
        else:
            self.__client.on_notification(method, handler)

    def on_request(self, method: str, handler: Callable) -> None:
        if USE_NEW_API:

            def handler_wrapper(this, params, request_id):
                handler(params, lambda result: this.send_response(Response(request_id, result)))

            setattr(self.__client, method2attr(method), handler_wrapper)

        else:

            def on_response(params, request_id):
                handler(params, lambda result: send_response(request_id, result))

            def send_response(request_id, result):
                self.__client.send_response(Response(request_id, result))

            self.__client.on_request(method, on_response)


class NpmClientHandler(BaseClass):  # type: ignore
    # To be overridden by subclass.
    package_name = None
    server_directory = None
    server_binary_path = None
    # Internal
    __server = None
    settings_filename = None

    def __init__(self):
        super().__init__()
        assert self.package_name
        # Calling setup() also here as this might run before `plugin_loaded`.
        # Will be a no-op if already ran.
        # See https://github.com/sublimelsp/LSP/issues/899
        if self.__server is None:
            self.setup()

    @classmethod
    def setup(cls) -> None:
        assert cls.package_name
        assert cls.server_directory
        assert cls.server_binary_path
        if not cls.__server:
            cls.__server = ServerNpmResource(cls.package_name, cls.server_directory, cls.server_binary_path)
        cls.__server.setup()
        cls.settings_filename = '{}.sublime-settings'.format(cls.package_name)

    @classmethod
    def cleanup(cls) -> None:
        if cls.__server:
            cls.__server.cleanup()

    @classmethod
    def config(cls) -> ClientConfig:
        if cls.__server is None:
            cls.setup()

        configuration = {
            'enabled': True,
            'command': ['node', cls.__server.binary_path] + cls.get_binary_arguments(),
        }

        configuration.update(cls._read_configuration())
        cls.on_client_configuration_ready(configuration)
        return read_client_config(cls.name, configuration)

    @classmethod
    def name(cls) -> str:
        return cls.package_name.lower()  # type: ignore

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        return False

    @classmethod
    def install_or_update(cls) -> None:
        pass

    @classmethod
    def standard_configuration(cls) -> ClientConfig:
        return cls.config()

    @classmethod
    def adjust_configuration(cls, configuration: ClientConfig) -> ClientConfig:
        return configuration

    @classmethod
    def can_start(cls, window: sublime.Window, initiating_view: sublime.View,
                  workspace_folders: List[WorkspaceFolder], configuration: ClientConfig) -> Optional[str]:
        return None

    @classmethod
    def get_binary_arguments(cls):
        """
        Returns a list of extra arguments to append when starting server.
        """
        return ['--stdio']

    @classmethod
    def _read_configuration(cls) -> Dict:
        settings = {}  # type: Dict
        loaded_settings = sublime.load_settings(cls.settings_filename)  # type: sublime.Settings

        if loaded_settings:
            migrated = cls._migrate_obsolete_settings(loaded_settings)
            changed = cls.on_settings_read(loaded_settings)
            if migrated or changed:
                sublime.save_settings(cls.settings_filename)

            for key, default in CLIENT_SETTING_KEYS.items():
                settings[key] = loaded_settings.get(key, default)

        return settings

    @classmethod
    def on_settings_read(cls, settings: sublime.Settings):
        """
        Called when package settings were read. Receives a `sublime.Settings` object.

        Can be used to change user settings, migrating them to new schema, for example.

        Return True if settings were modified to save changes to file.
        """
        return False

    @classmethod
    def _migrate_obsolete_settings(cls, settings: sublime.Settings):
        """
        Migrates setting with a root `client` key to flattened structure.
        Receives a `sublime.Settings` object.

        Returns True if settings were migrated.
        """
        client = settings.get('client')  # type: Dict
        if client:
            settings.erase('client')
            # Migrate old keys
            for key, value in client.items():
                settings.set(key, value)
            return True
        return False

    @classmethod
    def on_client_configuration_ready(cls, configuration: Dict) -> None:
        """
        Called with default configuration object that contains merged default and user settings.

        Can be used to alter default configuration before registering it.
        """
        pass

    def on_start(self, window) -> bool:
        if not self._is_node_installed():
            sublime.status_message("{}: Please install Node.js for the server to work.".format(self.package_name))
            return False
        if not self.__server:
            return False
        return self.__server.ready

    def on_initialized(self, client) -> None:
        """
        This method should not be overridden. Use the `on_ready` abstraction.
        """
        wrapper = ApiWrapper(self if USE_NEW_API else client)
        self.on_ready(wrapper)

    def on_ready(self, api: ApiWrapper) -> None:
        pass

    def _is_node_installed(self):
        return shutil.which('node') is not None
