from .api_decorator import notification_handler
from .api_decorator import request_handler
from LSP.plugin import __version__ as lsp_version


if lsp_version >= (1, 0, 0):
    from .abstract_plugin import ClientHandler
else:
    from .language_handler import ClientHandler

__all__ = [
    'ClientHandler',
    'notification_handler',
    'request_handler',
]
