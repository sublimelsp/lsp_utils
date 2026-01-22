from __future__ import annotations
from .setup import TextDocumentTestCase, TIMEOUT_TIME
from LSP.plugin.session_view import SessionView
from typing import cast, Generator


class BaseTestCase(TextDocumentTestCase):

    def test_diagnostics(self) -> Generator:
        session_view = cast(SessionView, self.session.session_view_for_view_async(self.view))
        self.assertIsNotNone(session_view)
        error_region_key = '{}_icon'.format(session_view.diagnostics_key(1, multiline=False))
        yield {'condition': lambda: len(session_view.session_buffer.diagnostics) == 1, 'timeout': TIMEOUT_TIME * 4}
        print(session_view.session_buffer.diagnostics)
        error_regions = self.view.get_regions(error_region_key)
        self.assertEqual(len(error_regions), 1)
        region = error_regions[0]
        self.assertEqual((region.a, region.b), (6, 7))
        self.view.window().run_command('show_panel', {"panel": "console", "toggle": True})


class SystemRuntime(BaseTestCase):

    @classmethod
    def setUpClass(cls) -> Generator:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['system'],
        })
        yield from super().setUpClass()


class LocalNodeRuntime(BaseTestCase):

    @classmethod
    def setUpClass(cls) -> Generator:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['local'],
            'local_use_electron': False
        })
        yield from super().setUpClass()


class LocalElectronRuntime(BaseTestCase):

    @classmethod
    def setUpClass(cls) -> Generator:
        cls.set_lsp_utils_settings({
            'nodejs_runtime': ['local'],
            'local_use_electron': True
        })
        yield from super().setUpClass()
