import shutil
import sublime
from LSP.plugin.core.handlers import LanguageHandler
from LSP.plugin.core.protocol import Response
from LSP.plugin.core.settings import ClientConfig, read_client_config
from LSP.plugin.core.typing import Callable, Dict
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
        self.__client.on_notification(method, handler)

    def on_request(self, method: str, handler: Callable) -> None:
        def on_response(params, request_id):
            handler(params, lambda result: send_response(request_id, result))

        def send_response(request_id, result):
            self.__client.send_response(Response(request_id, result))

        self.__client.on_request(method, on_response)


class NpmClientHandler(LanguageHandler):
    # To be overridden by subclass.
    package_name = None
    server_directory = None
    server_binary_path = None
    # Internal
    __server = None

    def __init__(self):
        super().__init__()
        assert self.package_name
        self.settings_filename = '{}.sublime-settings'.format(self.package_name)
        # Calling setup() also here as this might run before `plugin_loaded`.
        # Will be a no-op if already ran.
        # See https://github.com/sublimelsp/LSP/issues/899
        self.setup()

    @classmethod
    def setup(cls) -> None:
        assert cls.package_name
        assert cls.server_directory
        assert cls.server_binary_path
        if not cls.__server:
            cls.__server = ServerNpmResource(cls.package_name, cls.server_directory, cls.server_binary_path)
        cls.__server.setup()

    @classmethod
    def cleanup(cls) -> None:
        if cls.__server:
            cls.__server.cleanup()

    @property
    def name(self) -> str:
        return self.package_name.lower()  # type: ignore

    @property
    def config(self) -> ClientConfig:
        assert self.__server

        configuration = {
            'enabled': True,
            'command': ['node', self.__server.binary_path] + self.get_binary_arguments(),
        }

        configuration.update(self._read_configuration())
        self.on_client_configuration_ready(configuration)
        return read_client_config(self.name, configuration)

    @classmethod
    def get_binary_arguments(cls):
        """
        Returns a list of extra arguments to append when starting server.
        """
        return ['--stdio']

    def _read_configuration(self) -> Dict:
        settings = {}  # type: Dict
        loaded_settings = sublime.load_settings(self.settings_filename)

        if loaded_settings:
            migrated = self._migrate_obsolete_settings(loaded_settings)
            changed = self.on_settings_read(loaded_settings)
            if migrated or changed:
                sublime.save_settings(self.settings_filename)

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

    def _migrate_obsolete_settings(self, settings: sublime.Settings):
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

    @classmethod
    def on_start(cls, window) -> bool:
        if not is_node_installed():
            sublime.status_message("{}: Please install Node.js for the server to work.".format(cls.package_name))
            return False
        if not cls.__server:
            return False
        return cls.__server.ready

    def on_initialized(self, client) -> None:
        """
        This method should not be overridden. Use the `on_ready` abstraction.
        """
        self.on_ready(ApiWrapper(client))

    def on_ready(self, api: ApiWrapper) -> None:
        pass
