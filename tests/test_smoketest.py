from __future__ import annotations

from .setup import GeneratorAny
from .setup import TextDocumentTestCase
from .setup import TIMEOUT_TIME
from typing import cast
from typing import TYPE_CHECKING
from typing_extensions import override

if TYPE_CHECKING:
    from LSP.plugin.session_view import SessionView


class BaseTestCase(TextDocumentTestCase):

    def test_diagnostics(self) -> GeneratorAny:
        session_view = cast('SessionView', self.session.session_view_for_view_async(self.view))
        assert session_view is not None
        error_region_key = f'{session_view.diagnostics_key(1, multiline=False)}_icon'
        yield {'condition': lambda: len(session_view.session_buffer.diagnostics) == 1, 'timeout': TIMEOUT_TIME * 4}
        error_regions = self.view.get_regions(error_region_key)
        assert len(error_regions) == 1
        region = error_regions[0]
        assert (region.a, region.b) == (6, 7)
        self.view.window().run_command('show_panel', {"panel": "console", "toggle": True})


class SystemRuntime(BaseTestCase):

    @classmethod
    @override
    def setUpClass(cls) -> GeneratorAny:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['system'],
        })
        yield from super().setUpClass()


class LocalNodeRuntime(BaseTestCase):

    @classmethod
    @override
    def setUpClass(cls) -> GeneratorAny:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['local'],
            'local_use_electron': False,
        })
        yield from super().setUpClass()


class LocalElectronRuntime(BaseTestCase):

    @classmethod
    @override
    def setUpClass(cls) -> GeneratorAny:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['local'],
            'local_use_electron': True,
        })
        yield from super().setUpClass()
