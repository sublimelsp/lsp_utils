from __future__ import annotations

from .setup import GeneratorAny
from .setup import TextDocumentTestCase
from .setup import TIMEOUT_TIME
from LSP.protocol import DiagnosticSeverity
from pathlib import Path
from typing import cast
from typing import TYPE_CHECKING
from typing_extensions import override

if TYPE_CHECKING:
    from LSP.plugin.session_view import SessionView

SCRIPT_DIR = Path(__file__).parent
TEST_FILE_PATH = str(SCRIPT_DIR / 'assets' / 'sample.py')


class NodeTestsuite(TextDocumentTestCase):

    @classmethod
    def get_test_file_path(cls) -> str:
        return TEST_FILE_PATH

    @classmethod
    def get_server_name(cls) -> str:
        return 'LSP-pyright'

    def test_diagnostics(self) -> GeneratorAny:
        session = self.session
        assert session, 'Expected Session'
        session_view = cast('SessionView', session.session_view_for_view_async(self.view))
        assert session_view is not None
        yield {'condition': lambda: len(session_view.session_buffer.diagnostics) == 1, 'timeout': TIMEOUT_TIME * 4}
        (diagnostic, _) = session_view.session_buffer.diagnostics[0]
        assert diagnostic.get('source') == 'pyright'
        error_region_key = f'{session_view.diagnostics_key(DiagnosticSeverity.Error, multiline=False)}_icon'
        error_regions = self.view.get_regions(error_region_key)
        assert len(error_regions) == 1
        region = error_regions[0]
        assert (region.a, region.b) == (6, 7)


class SystemRuntime(NodeTestsuite):

    @classmethod
    @override
    def setUpClass(cls) -> GeneratorAny:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['system'],
        })
        yield from super().setUpClass()


class LocalNodeRuntime(NodeTestsuite):

    @classmethod
    @override
    def setUpClass(cls) -> GeneratorAny:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['local'],
        })
        yield from super().setUpClass()
