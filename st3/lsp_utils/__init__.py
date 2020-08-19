try:
    from LSP.plugin import __version__ as lsp_version
except ImportError:
    lsp_version = (0, 0, 0)

from .api_wrapper import ApiWrapperInterface
from .server_npm_resource import ServerNpmResource

if lsp_version >= (1, 0, 0):
    from .npm_client_handler_v2 import NpmClientHandler
else:
    from .npm_client_handler import NpmClientHandler

__all__ = [
    'ApiWrapperInterface',
    'NpmClientHandler',
    'ServerNpmResource',
]
