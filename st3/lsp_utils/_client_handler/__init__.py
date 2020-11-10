from LSP.plugin import __version__ as lsp_version


major_version = lsp_version[0]

if major_version == 1:  # types are problematic when comparing tuples with ">=".
    from .abstract_plugin import ClientHandler
elif major_version == 0:
    from .language_handler import ClientHandler
else:
    raise Exception('Unsupported LSP version {}'.format(lsp_version))

__all__ = [
    'ClientHandler',
]
