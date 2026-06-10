from __future__ import annotations

from .setup import GeneratorAny
from .setup import TextDocumentTestCase
from .setup import TIMEOUT_TIME
from pathlib import Path
from typing import cast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from LSP.plugin.session_view import SessionView

SCRIPT_DIR = Path(__file__).parent
TEST_FILE_PATH = str(SCRIPT_DIR / 'assets' / 'sample.py')


class UvTestsuite(TextDocumentTestCase):

    @classmethod
    def get_test_file_path(cls) -> str:
        return TEST_FILE_PATH

    @classmethod
    def get_server_name(cls) -> str:
        return 'LSP-ruff'

    def test_diagnostics(self) -> GeneratorAny:
        session = self.session
        assert session, 'Expected Session'
        session_view = cast('SessionView', session.session_view_for_view_async(self.view))
        assert session_view is not None
        yield {'condition': lambda: len(session_view.session_buffer.diagnostics) == 1, 'timeout': TIMEOUT_TIME * 4}
        (diagnostic, _) = session_view.session_buffer.diagnostics[0]
        assert diagnostic.get('source') == 'Ruff'
