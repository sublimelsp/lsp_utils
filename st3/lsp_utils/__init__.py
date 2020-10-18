try:
    from LSP.plugin import __version__ as lsp_version
except ImportError:
    lsp_version = (0, 0, 0)

from .api_wrapper import ApiWrapperInterface
from .server_npm_resource import ServerNpmResource
from .server_vscode_marketplace_resource import ServerVscodeMarketplaceResource

if lsp_version >= (1, 0, 0):
    from .npm_client_handler_v2 import NpmClientHandler
    from .vscode_marketplace_client_handler_v2 import VscodeMarketplaceClientHandler
else:
    from .npm_client_handler import NpmClientHandler
    from .vscode_marketplace_client_handler import VscodeMarketplaceClientHandler

__all__ = [
    'ApiWrapperInterface',
    'NpmClientHandler',
    'ServerNpmResource',
    'VscodeMarketplaceClientHandler',
    'ServerVscodeMarketplaceResource',
]
