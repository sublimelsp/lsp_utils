import shutil
import sublime
import weakref
import os
import subprocess
from sublime_lib import ResourcePath
from LSP.plugin import AbstractPlugin
from LSP.plugin import ClientConfig
from LSP.plugin import Response
from LSP.plugin import Session
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.rpc import method2attr  # TODO: Remove this import
from LSP.plugin.core.typing import List, Optional, Dict, Callable, Any


def is_node_installed():
    return shutil.which('node') is not None


class ApiWrapper:
    def __init__(self, plugin: AbstractPlugin):
        self.__plugin = plugin

    def on_notification(self, method: str, handler: Callable) -> None:
        setattr(self.__plugin, method2attr(method), handler)

    def on_request(self, method: str, handler: Callable) -> None:

        def send_response(request_id, result):
            session = self.__plugin.weaksession()
            if session:
                session.send_response(Response(request_id, result))

        def on_response(params, request_id):
            handler(params, lambda result: send_response(request_id, result))

        setattr(self.__plugin, method2attr(method), on_response)


class NpmClientHandler(AbstractPlugin):
    # To be overridden by subclass.
    package_name = None  # type: Optional[str]
    server_directory = None  # type: Optional[str]
    server_binary_path = None  # type: Optional[str]
    # Internal
    _package_cache_path = None  # type: Optional[str]
    _cache_server_path = None  # type: Optional[str]

    @classmethod
    def setup(cls) -> None:
        assert cls.package_name
        assert cls.server_directory
        assert cls.server_binary_path
        if cls._package_cache_path:
            return
        cls._package_cache_path = os.path.join(sublime.cache_path(), cls.package_name)
        cls._cache_server_path = os.path.join(cls._package_cache_path, cls.server_directory)

    @classmethod
    def cleanup(cls) -> None:
        cls._package_cache_path = None
        cls._cache_server_path = None

    @classmethod
    def get_binary_arguments(cls):
        """
        Returns a list of extra arguments to append when starting server.
        """
        return ['--stdio']

    @classmethod
    def name(cls) -> str:
        assert cls.package_name
        return cls.package_name[len('LSP-'):]

    @classmethod
    def configuration(cls) -> sublime.Settings:
        if not cls._package_cache_path:
            # https://github.com/sublimelsp/LSP/issues/899
            cls.setup()
        settings = super().configuration()
        path = os.path.join(sublime.cache_path(), cls.package_name, cls.server_binary_path)
        settings.set('command', ['node', path] + cls.get_binary_arguments())
        # begin hacks for old API
        on_client_configuration_ready = getattr(cls, 'on_client_configuration_ready', None)
        if callable(on_client_configuration_ready):
            options = {'settings': {}, 'initializationOptions': {}}  # type: Dict[str, Any]
            # Do it once to get the keys
            on_client_configuration_ready(options)
            for key in options.keys():
                current_value = settings.get(key, None)
                if isinstance(current_value, dict):
                    options[key] = current_value
            # Now do it again to make the dicts merge
            on_client_configuration_ready(options)
            for k, v in options.items():
                # Commit changes
                settings.set(k, v)
        # end hacks for old API
        return settings

    @classmethod
    def needs_update_or_installation(cls) -> bool:
        cache_server_path = os.path.join(cls._package_cache_path, cls.server_directory)
        if os.path.isdir(cache_server_path):
            # Server already in cache. Check if version has changed and if so, update.
            try:
                src_path = 'Packages/{}/{}/'.format(cls.package_name, cls.server_directory)
                dst_path = 'Cache/{}/{}/'.format(cls.package_name, cls.server_directory)
                src_package_json = ResourcePath(src_path, 'package.json').read_text()
                dst_package_json = ResourcePath(dst_path, 'package.json').read_text()
                if src_package_json == dst_package_json:
                    return False
            except FileNotFoundError:
                pass
        return True

    @classmethod
    def install_or_update(cls) -> None:
        cache_server_path = os.path.join(cls._package_cache_path, cls.server_directory)
        src_path = 'Packages/{}/{}/'.format(cls.package_name, cls.server_directory)
        ResourcePath(src_path).copytree(cache_server_path, exist_ok=True)
        cmd = ["npm", "install", "--verbose", "--production", "--prefix",
               cls._cache_server_path, cls._cache_server_path]
        subprocess.check_call(cmd, shell=sublime.platform() == 'windows')

    @classmethod
    def can_start(cls, window: sublime.Window, initiating_view: sublime.View,
                  workspace_folders: List[WorkspaceFolder],
                  configuration: ClientConfig) -> Optional[str]:
        if not is_node_installed():
            return 'Please install Node.js for the server to work.'

    def __init__(self, weaksession: 'weakref.ref[Session]') -> None:
        """
        This method should not be overridden. Use the `on_ready` abstraction.
        """
        super().__init__(weaksession)
        assert self.package_name
        self.on_ready(ApiWrapper(self))

    def on_ready(self, api: ApiWrapper) -> None:
        pass
