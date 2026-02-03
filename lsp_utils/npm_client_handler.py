from __future__ import annotations
from .generic_client_handler import GenericClientHandler
from .server_npm_resource import ServerNpmResource
from .server_resource_interface import ServerResourceInterface
from LSP.plugin import ClientConfig
from LSP.plugin import WorkspaceFolder
from os import path
from typing_extensions import override
import sublime

__all__ = ['NpmClientHandler']


class NpmClientHandler(GenericClientHandler):
    """
    An implementation of :class:`GenericClientHandler` for handling NPM-based LSP plugins.

    Automatically manages an NPM-based server by installing and updating it in the package storage directory.
    """
    __server: ServerNpmResource | None = None

    server_directory: str = ''
    """
    The path to the server source directory, relative to the root directory of this package.

    :required: Yes
    """

    server_binary_path: str = ''
    """
    The path to the server "binary", relative to plugin's storage directory.

    :required: Yes
    """

    skip_npm_install: bool = False
    """
    Whether to skip the step that runs "npm install" in case the server doesn't need any dependencies.

    :required: No
    """

    # --- NpmClientHandler handlers -----------------------------------------------------------------------------------

    @classmethod
    def minimum_node_version(cls) -> tuple[int, int, int]:
        """
        .. deprecated:: 2.1.0
           Use :meth:`required_node_version` instead.

        The minimum Node version required for this plugin.

        :returns: The semantic version tuple with the minimum required version. Defaults to :code:`(8, 0, 0)`.
        """
        return (8, 0, 0)

    @classmethod
    def required_node_version(cls) -> str:
        """
        The NPM semantic version (typically a range) specifying which version of Node is required for this plugin.

        Examples:
         - `16.1.1` - only allows a single version
         - `16.x` - allows any build for major version 16
         - `>=16` - allows version 16 and above
         - `16 - 18` allows any version between version 16 and 18 (inclusive). It's important to have spaces around
           the dash in this case.

        Also see more examples and a testing playground at https://semver.npmjs.com/ .

        :returns: Required NPM semantic version. Defaults to :code:`0.0.0` which means "no restrictions".
        """
        return '0.0.0'

    # --- GenericClientHandler handlers -------------------------------------------------------------------------------

    @classmethod
    @override
    def get_additional_variables(cls) -> dict[str, str]:
        """
        Overrides :meth:`GenericClientHandler.get_additional_variables`, providing additional variable for use in the
        settings.

        The additional variables are:

        - `${node_bin}`: - holds the binary path of currently used Node.js runtime. This can resolve to just `node`
          when using Node.js runtime from the PATH or to a full filesystem path if using the local Node.js runtime.
        - `${server_directory_path}` - holds filesystem path to the server directory (only
          when :meth:`GenericClientHandler.manages_server()` is `True`).

        Remember to call the super class and merge the results if overriding.
        """
        variables = super().get_additional_variables()
        variables.update({
            'node_bin': cls._node_bin(),
            'server_directory_path': cls._server_directory_path(),
        })
        return variables

    @classmethod
    @override
    def get_additional_paths(cls) -> list[str]:
        node_bin = cls._node_bin()
        if node_bin:
            node_path = path.dirname(node_bin)
            if node_path:
                return [node_path]
        return []

    @classmethod
    @override
    def get_command(cls) -> list[str]:
        return [cls._node_bin(), cls.binary_path()] + cls.get_binary_arguments()

    @classmethod
    @override
    def get_binary_arguments(cls) -> list[str]:
        return ['--stdio']

    @classmethod
    @override
    def manages_server(cls) -> bool:
        return True

    @classmethod
    @override
    def get_server(cls) -> ServerResourceInterface | None:
        if not cls.__server:
            cls.__server = ServerNpmResource.create({
                'package_name': cls.package_name,
                'server_directory': cls.server_directory,
                'server_binary_path': cls.server_binary_path,
                'package_storage': cls.package_storage(),
                'minimum_node_version': cls.minimum_node_version(),
                'required_node_version': cls.required_node_version(),
                'storage_path': cls.storage_path(),
                'skip_npm_install': cls.skip_npm_install,
            })
        return cls.__server

    @classmethod
    @override
    def cleanup(cls) -> None:
        cls.__server = None
        super().cleanup()

    @classmethod
    @override
    def can_start(cls, window: sublime.Window, initiating_view: sublime.View,
                  workspace_folders: list[WorkspaceFolder], configuration: ClientConfig) -> str | None:
        reason = super().can_start(window, initiating_view, workspace_folders, configuration)
        if reason:
            return reason
        node_env = cls._node_env()
        if node_env:
            configuration.env.update(node_env)
        return None

    # --- Internal ----------------------------------------------------------------------------------------------------

    @classmethod
    def _server_directory_path(cls) -> str:
        if cls.__server:
            return cls.__server.server_directory_path
        return ''

    @classmethod
    def _node_bin(cls) -> str:
        if cls.__server:
            return cls.__server.node_bin
        return ''

    @classmethod
    def _node_env(cls) -> dict[str, str] | None:
        if cls.__server:
            return cls.__server.node_env
        return None
