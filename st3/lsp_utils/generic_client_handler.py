from ._client_handler import ClientHandler
from .api_wrapper_interface import ApiWrapperInterface
from .server_resource_interface import ServerResourceInterface
from abc import ABCMeta
from LSP.plugin import ClientConfig
from LSP.plugin import WorkspaceFolder
from LSP.plugin.core.typing import Dict, List, Optional, Tuple
import os
import shutil
import sublime

__all__ = ['GenericClientHandler']


class GenericClientHandler(ClientHandler, metaclass=ABCMeta):
    """
    An generic implementation of an LSP plugin handler.
    """

    package_name = ''
    """
    The name of the released package. Also used for the name of the LSP client and for reading package settings.

    This name must be set and must match the basename of the corresponding `*.sublime-settings` file.
    It's also used as a directory name for package storage when implementing a server resource interface.

    :required: Yes
    """

    # --- ClientHandler handlers --------------------------------------------------------------------------------------

    @classmethod
    def setup(cls) -> None:
        if not cls.package_name:
            raise Exception('ERROR: [lsp_utils] package_name is required to instantiate an instance of {}'.format(cls))
        super().setup()

    @classmethod
    def cleanup(cls) -> None:
        if os.path.isdir(cls.package_storage()):
            shutil.rmtree(cls.package_storage())
        super().cleanup()

    @classmethod
    def get_displayed_name(cls) -> str:
        """
        Returns the name the server will that will be shown in the ST UI (for example in the status field).

        Defaults to the value of :attr:`package_name`.
        """
        return cls.package_name

    @classmethod
    def package_storage(cls) -> str:
        return os.path.join(cls.get_storage_path(), cls.package_name)

    @classmethod
    def get_command(cls) -> List[str]:
        """
        Returns a list of arguments to use to start the server. The default implementation returns combined result of
        :meth:`binary_path()` and :meth:`get_binary_arguments()`.
        """
        return [cls.binary_path()] + cls.get_binary_arguments()

    @classmethod
    def binary_path(cls) -> str:
        """
        The filesystem path to the server executable.

        The default implementation returns `binary_path` property of the server instance (returned from
        :meth:`get_server()`), if available.
        """
        if cls.manages_server():
            server = cls.get_server()
            if server:
                return server.binary_path
        return ''

    @classmethod
    def get_binary_arguments(cls) -> List[str]:
        """
        Returns a list of extra arguments to append to the `command` when starting the server.

        See :meth:`get_command()`.
        """
        return []

    @classmethod
    def read_settings(cls) -> Tuple[sublime.Settings, str]:
        filename = "{}.sublime-settings".format(cls.package_name)
        loaded_settings = sublime.load_settings(filename)
        cls.on_settings_read_internal(loaded_settings)
        changed = cls.on_settings_read(loaded_settings)
        if changed:
            sublime.save_settings(filename)
        settings = {}
        for key, default in cls.get_default_settings_schema().items():
            settings[key] = loaded_settings.get(key, default)
        # Pass a copy of the settings to the "on_client_configuration_ready" and copy back returned values.
        settings_copy = {}
        for key, default in cls.get_default_settings_schema().items():
            settings_copy[key] = settings.get(key, default)
        cls.on_client_configuration_ready(settings_copy)
        for key in cls.get_default_settings_schema().keys():
            loaded_settings.set(key, settings_copy[key])
        filepath = "Packages/{}/{}".format(cls.package_name, filename)
        return (loaded_settings, filepath)

    @classmethod
    def get_additional_variables(cls) -> Optional[Dict[str, str]]:
        """
        Override to add more variables here to be expanded when reading settings.

        Default implementation adds a `${server_path}` variable that holds filesystem path to the server
        binary (only when :meth:`manages_server` is `True`).

        Remember to call the super class and merge the results if overriding.
        """
        return {
            'server_path': cls.binary_path(),
        }

    @classmethod
    def manages_server(cls) -> bool:
        """
        Whether this handler manages a server. If the response is `True` then the :meth:`get_server()` should also be
        implemented.
        """
        return False

    @classmethod
    def get_server(cls) -> Optional[ServerResourceInterface]:
        """
        :returns: The instance of the server managed by this plugin. Only used when :meth:`manages_server()`
                  returns `True`.
        """
        return None

    @classmethod
    def on_settings_read(cls, settings: sublime.Settings) -> bool:
        """
        Called when package settings were read. Receives a `sublime.Settings` object.

        Can be used to change or just read the user settings.

        :returns: `True` to save modifications back into the settings file. It's not customary to save your changes.
        """
        return False

    @classmethod
    def on_client_configuration_ready(cls, configuration: Dict) -> None:
        """
        Called with default configuration object that contains merged default and user settings.

        Can be used to alter default configuration before registering it.

        .. deprecated:: 1.8
           Use :func:`on_settings_read()` instead.
        """
        pass

    @classmethod
    def is_allowed_to_start(
        cls,
        window: sublime.Window,
        initiating_view: Optional[sublime.View] = None,
        workspace_folders: Optional[List[WorkspaceFolder]] = None,
        configuration: Optional[ClientConfig] = None
    ) -> Optional[str]:
        """
        Determines if the session is allowed to start.

        :returns: A string describing the reason why we should not start a language server session, or `None` if we
                  should go ahead and start a session.
        """
        return None

    def __init__(self, *args, **kwargs) -> None:
        # Seems unnecessary to override but it's to hide the original argument from the documentation.
        super().__init__(*args, **kwargs)

    def on_ready(self, api: ApiWrapperInterface) -> None:
        """
        Called when the instance is ready.

        :param api: The API instance for interacting with the server.
        """
        pass
