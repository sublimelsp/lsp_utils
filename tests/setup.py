from __future__ import annotations
from LSP.plugin.core.registry import windows
from LSP.plugin.core.sessions import Session
from LSP.plugin.core.types import ClientStates
from LSP.plugin.core.typing import Any, Dict, Generator, Optional
from lsp_utils import NodeRuntime
from lsp_utils import SETTINGS_FILENAME
from os import remove
from os.path import isfile, join
from sublime_plugin import view_event_listeners
from unittesting import DeferrableTestCase
import sublime

try:
    from LSP.plugin.documents import DocumentSyncListener
    from LSP.plugin.core.sessions import get_plugin
    lsp_pyright_class = get_plugin('LSP-pyright')
    ST3 = False
except ImportError:
    from LSP.plugin.core.documents import DocumentSyncListener
    ST3 = True

TIMEOUT_TIME = 2000


def close_test_view(view: Optional[sublime.View]) -> 'Generator':
    if view:
        view.set_scratch(True)
        yield {'condition': lambda: not view.is_loading(), 'timeout': TIMEOUT_TIME}
        view.close()


def expand(s: str, w: sublime.Window) -> str:
    return sublime.expand_variables(s, w.extract_variables())


class TextDocumentTestCase(DeferrableTestCase):

    session: Session | None = None

    @classmethod
    def get_test_file_name(cls) -> str:
        return 'sample.py'

    @classmethod
    def get_session_name(cls) -> str:
        return 'lsp-pyright' if ST3 else 'LSP-pyright'

    @classmethod
    def setUpClass(cls) -> Generator:
        super().setUpClass()
        if not ST3:
            lsp_pyright_class.setup()
        window = sublime.active_window()
        filename = expand(join('$packages', 'lsp_utils', 'tests', cls.get_test_file_name()), window)
        open_view = window.find_open_file(filename)
        yield from close_test_view(open_view)
        cls.wm = windows.lookup(window)
        cls.view = window.open_file(filename)
        yield {'condition': lambda: not cls.view.is_loading(), 'timeout': TIMEOUT_TIME}
        yield cls.ensure_document_listener_created
        # First start needs time to install the dependencies.
        INSTALL_TIMEOUT = 30000
        yield {
            'condition': lambda: cls.wm.get_session(cls.get_session_name(), filename) is not None,
            'timeout': INSTALL_TIMEOUT
        }
        cls.session = cls.wm.get_session(cls.get_session_name(), filename)
        yield {'condition': lambda: cls.session.state == ClientStates.READY, 'timeout': TIMEOUT_TIME}
        if not ST3:
            # Ensure SessionView is created.
            yield {'condition': lambda: cls.session.session_view_for_view_async(cls.view), 'timeout': TIMEOUT_TIME}
        yield from close_test_view(cls.view)

    def setUp(self) -> Generator:
        window = sublime.active_window()
        filename = expand(join('$packages', 'lsp_utils', 'tests', self.get_test_file_name()), window)
        open_view = window.find_open_file(filename)
        if not open_view:
            self.__class__.view = window.open_file(filename)
            yield {'condition': lambda: not self.view.is_loading(), 'timeout': TIMEOUT_TIME}
            if ST3:
                self.assertTrue(self.wm._configs.syntax_supported(self.view))
            else:
                self.assertTrue(self.wm.get_config_manager().match_view(self.view))
        self.init_view_settings()
        yield self.ensure_document_listener_created
        if not ST3:
            # Ensure SessionView is created.
            yield {'condition': lambda: self.session.session_view_for_view_async(self.view), 'timeout': TIMEOUT_TIME}

    @classmethod
    def init_view_settings(cls) -> None:
        s = cls.view.settings().set
        s('auto_complete_selector', 'text')
        s('ensure_newline_at_eof_on_save', False)
        s('rulers', [])
        s('tab_size', 4)
        s('translate_tabs_to_spaces', False)
        s('word_wrap', False)
        s('lsp_format_on_save', False)

    @classmethod
    def ensure_document_listener_created(cls) -> bool:
        assert cls.view
        # Bug in ST3? Either that, or CI runs with ST window not in focus and that makes ST3 not trigger some
        # events like on_load_async, on_activated, on_deactivated. That makes things not properly initialize on
        # opening file (manager missing in DocumentSyncListener)
        # Revisit this once we're on ST4.
        for listener in view_event_listeners[cls.view.id()]:
            if isinstance(listener, DocumentSyncListener):
                sublime.set_timeout_async(listener.on_activated_async)
                return True
        return False

    @classmethod
    def set_lsp_utils_settings(cls, value: Dict[str, Any]) -> None:
        settings = sublime.load_settings(SETTINGS_FILENAME)
        for key, value in value.items():
            settings.set(key, value)
        sublime.save_settings(SETTINGS_FILENAME)

    @classmethod
    def remove_lsp_utils_settings(cls) -> None:
        settings_filepath = join(sublime.packages_path(), 'User', SETTINGS_FILENAME)
        if isfile(settings_filepath):
            remove(settings_filepath)
        sublime.save_settings(SETTINGS_FILENAME)
        NodeRuntime._node_runtime_resolved = False

    @classmethod
    def tearDownClass(cls) -> 'Generator':
        if cls.session and cls.wm:
            if ST3:
                cls.wm.end_config_sessions(cls.get_session_name())
            else:
                sublime.set_timeout_async(cls.session.end_async)
            yield lambda: cls.session.state == ClientStates.STOPPING
            if cls.view:
                yield lambda: cls.wm.get_session(cls.get_session_name(), cls.view.file_name()) is None
        cls.session = None
        cls.wm = None
        cls.remove_lsp_utils_settings()
        if not ST3:
            lsp_pyright_class.cleanup()
        super().tearDownClass()

    def doCleanups(self) -> 'Generator':
        if self.view and self.view.is_valid():
            yield from close_test_view(self.view)
        yield from super().doCleanups()
