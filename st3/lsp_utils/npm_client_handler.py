from .generic_client_handler import GenericClientHandler
from .server_npm_resource import ServerNpmResource
from .server_resource_interface import ServerResourceInterface
from LSP.plugin.core.typing import Dict, List, Optional, Tuple
import sublime

__all__ = ['NpmClientHandler']


class NpmClientHandler(GenericClientHandler):
    """
    An implementation of :class:`GenericClientHandler` for handling NPM-based LSP plugins.

    Automatically manages an NPM-based server by installing and updating it in the package storage directory.
    """
    __server = None  # type: Optional[ServerNpmResource]

    server_directory = ''
    """
    The path to the server source directory, relative to the root directory of this package.

    :required: Yes
    """

    server_binary_path = ''
    """
    The path to the server "binary", relative to plugin's storage directory.

    :required: Yes
    """

    # --- NpmClientHandler handlers -----------------------------------------------------------------------------------

    @classmethod
    def minimum_node_version(cls) -> Tuple[int, int, int]:
        """
        The minimum Node version required for this plugin.

        :returns: The semantic version tuple with the minimum required version. Defaults to :code:`(8, 0, 0)`.
        """
        return (8, 0, 0)

    @classmethod
    def get_additional_variables(cls) -> Dict[str, str]:
        """
        Overrides :meth:`GenericClientHandler.get_additional_variables`, providing additional variable for use in the
        settings.

        The additional variables are:

        - `${server_path}` - holds filesystem path to the server binary (only
          when :meth:`GenericClientHandler.manages_server()` is `True`).

        Remember to call the super class and merge the results if overriding.
        """
        variables = super().get_additional_variables()
        variables.update({
            'server_directory_path': cls._server_directory_path(),
        })
        return variables

    # --- GenericClientHandler handlers -------------------------------------------------------------------------------

    @classmethod
    def get_command(cls) -> List[str]:
        return ['node', cls.binary_path()] + cls.get_binary_arguments()

    @classmethod
    def get_binary_arguments(cls) -> List[str]:
        return ['--stdio']

    @classmethod
    def manages_server(cls) -> bool:
        return True

    @classmethod
    def get_server(cls) -> Optional[ServerResourceInterface]:
        if not cls.__server:
            cls.__server = ServerNpmResource.create({
                'package_name': cls.package_name,
                'server_directory': cls.server_directory,
                'server_binary_path': cls.server_binary_path,
                'package_storage': cls.package_storage(),
                'minimum_node_version': cls.minimum_node_version(),
            })
        return cls.__server

    @classmethod
    def _server_directory_path(cls) -> str:
        if cls.__server:
            return cls.__server.server_directory_path
        return ''
