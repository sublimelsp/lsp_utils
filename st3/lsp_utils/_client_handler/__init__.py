from .decorator import as_notification_handler, as_request_handler
from LSP.plugin import __version__ as lsp_version


if lsp_version >= (1, 0, 0):
    from .abstract_plugin import ClientHandler
else:
    from .language_handler import ClientHandler

__all__ = [
    'ClientHandler',
    # decorator-related
    'as_notification_handler',
    'as_request_handler',
]
