import shutil
import sublime
from LSP.plugin.core.sessions import Session
from LSP.plugin.core.protocol import Response, WorkspaceFolder
from LSP.plugin.core.settings import ClientConfig, read_client_config
from LSP.plugin.core.typing import Callable, Dict, List, Optional
from .server_npm_resource import ServerNpmResource

# Keys to read and their fallbacks.
CLIENT_SETTING_KEYS = {
    'env': {},
    'experimental_capabilities': {},
    'languages': [],
    'initializationOptions': {},
    'settings': {},
}  # type: ignore


def is_node_installed():
    return shutil.which('node') is not None


class ApiWrapper(object):
    def __init__(self, client):
        self.__client = client

    def on_notification(self, method: str, handler: Callable) -> None:
        pass
        # self.__client.on_notification(method, handler)

    def on_request(self, method: str, handler: Callable) -> None:
        pass
        # def on_response(params, request_id):
        #     handler(params, lambda result: send_response(request_id, result))

        # def send_response(request_id, result):
        #     self.__client.send_response(Response(request_id, result))

        # self.__client.on_request(method, on_response)


class NpmClientHandler(Session):
    package_name = ''  # type: str
    server_directory = ''  # type: str
    server_binary_path = ''  # type: str
    # Internal
    __server = None  # type: ServerNpmResource
    __settings_filename = None

    @classmethod
    def setup(cls) -> None:
        if not cls.__server:
            cls.__settings_filename = '{}.sublime-settings'.format(cls.package_name)
            cls.__server = ServerNpmResource(cls.package_name, cls.server_directory, cls.server_binary_path)
            cls.__server.setup()

    @classmethod
    def cleanup(cls) -> None:
        cls.__server.cleanup()

    @classmethod
    def name(cls) -> str:
        return cls.package_name.lower()

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        return False

    @classmethod
    def install_or_update(cls) -> None:
        pass

    @classmethod
    def standard_configuration(cls) -> ClientConfig:
        cls.setup()

        assert cls.__server

        configuration = {
            'enabled': True,
            'command': ['node', cls.__server.binary_path] + cls.get_binary_arguments(),
        }

        configuration.update(cls._read_configuration())
        cls.on_client_configuration_ready(configuration)
        return read_client_config(cls.name(), configuration)

    @classmethod
    def get_binary_arguments(cls):
        """
        Returns a list of extra arguments to append when starting server.
        """
        return ['--stdio']

    @classmethod
    def _read_configuration(cls) -> Dict:
        settings = {}  # type: Dict
        loaded_settings = sublime.load_settings(cls.__settings_filename)

        if loaded_settings:
            migrated = cls._migrate_obsolete_settings(loaded_settings)
            changed = cls.on_settings_read(loaded_settings)
            if migrated or changed:
                sublime.save_settings(cls.__settings_filename)

            for key, default in CLIENT_SETTING_KEYS.items():
                settings[key] = loaded_settings.get(key, default)

        return settings

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
    def adjust_configuration(cls, configuration: ClientConfig) -> ClientConfig:
        return configuration

    @classmethod
    def can_start(cls, window: sublime.Window, initiating_view: sublime.View,
                  workspace_folders: List[WorkspaceFolder], configuration: ClientConfig) -> Optional[str]:
        return cls.on_start(window)

    @classmethod
    def on_start(cls, window) -> bool:
        if not is_node_installed():
            sublime.status_message("{}: Please install Node.js for the server to work.".format(cls.package_name))
            return False
        if not cls.__server:
            return False
        return cls.__server.ready

    def on_initialized(self) -> None:
        """
        This method should not be overridden. Use the `on_ready` abstraction.
        """
        self.on_ready(ApiWrapper(self))

    def on_ready(self, api: ApiWrapper) -> None:
        pass

    def on_shutdown(self) -> None:
        pass
