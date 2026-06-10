from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from LSP.plugin.core.registry import windows
from LSP.plugin.core.types import ClientStates
from LSP.plugin.core.windows import get_plugin
from LSP.plugin.core.windows import WindowManager
from LSP.plugin.documents import DocumentSyncListener
from lsp_utils import SETTINGS_FILENAME
from pathlib import Path
from sublime_plugin import view_event_listeners
from typing import Any
from typing import Generator
from typing import TYPE_CHECKING
from typing_extensions import TypeAlias
from unittesting import DeferrableTestCase
import sublime

if TYPE_CHECKING:
    from LSP.plugin import Session

TIMEOUT_TIME = 2000
INSTALL_SERVER_TIMEOUT = 30000
PACKAGE_NAME = str(__package__).partition(".")[0]
SCRIPT_DIR = Path(__file__).parent

GeneratorAny: TypeAlias = Generator[Any, None, None]


def close_test_view(view: sublime.View | None) -> GeneratorAny:
    if view:
        view.set_scratch(True)
        yield {'condition': lambda: not view.is_loading(), 'timeout': TIMEOUT_TIME}
        view.close()


class TextDocumentTestCase(DeferrableTestCase, ABC):

    session: Session | None = None

    @classmethod
    @abstractmethod
    def get_test_file_path(cls) -> str:
        ...

    @classmethod
    @abstractmethod
    def get_server_name(cls) -> str:
        ...

    @classmethod
    def setUpClass(cls) -> GeneratorAny:
        super().setUpClass()
        server_name = cls.get_server_name()
        test_file_path = cls.get_test_file_path()
        if not get_plugin(server_name):
            msg = f'Plugin {server_name} not found'
            raise RuntimeError(msg)
        window = sublime.active_window()
        open_view = window.find_open_file(test_file_path)
        yield from close_test_view(open_view)
        cls.view = window.open_file(test_file_path)
        yield {'condition': lambda: not cls.view.is_loading(), 'timeout': TIMEOUT_TIME}
        yield cls.ensure_document_listener_created
        # First start needs time to install the dependencies.
        yield {
            'condition': lambda: cls.wm().get_session(server_name, test_file_path) is not None,
            'timeout': INSTALL_SERVER_TIMEOUT,
        }
        session = cls.session = cls.wm().get_session(server_name, test_file_path)
        if not session:
            msg = 'Session not found'
            raise RuntimeError(msg)
        yield {'condition': lambda: session.state == ClientStates.READY, 'timeout': TIMEOUT_TIME}
        # Ensure SessionView is created.
        yield {'condition': lambda: session.session_view_for_view_async(cls.view), 'timeout': TIMEOUT_TIME}
        yield from close_test_view(cls.view)

    @classmethod
    def wm(cls) -> WindowManager:
        window = sublime.active_window()
        if wm := windows.lookup(window):
            return wm
        msg = 'Window Manager not found'
        raise RuntimeError(msg)

    def setUp(self) -> GeneratorAny:
        window = sublime.active_window()
        open_view = window.find_open_file(self.get_test_file_path())
        if not open_view:
            self.__class__.view = window.open_file(self.get_test_file_path())
            yield {'condition': lambda: not self.view.is_loading(), 'timeout': TIMEOUT_TIME}
            assert self.wm().get_config_manager().match_view(self.view, [])
        self.init_view_settings()
        yield self.ensure_document_listener_created
        # Ensure SessionView is created.
        session = self.session
        assert session, 'Expected Session'
        yield {'condition': lambda: session.session_view_for_view_async(self.view), 'timeout': TIMEOUT_TIME}

    @classmethod
    def init_view_settings(cls) -> None:
        s = cls.view.settings().set
        s('auto_complete_selector', value='text')
        s('ensure_newline_at_eof_on_save', value=False)
        s('rulers', value=[])
        s('tab_size', value=4)
        s('translate_tabs_to_spaces', value=False)
        s('word_wrap', value=False)
        s('lsp_format_on_save', value=False)

    @classmethod
    def ensure_document_listener_created(cls) -> bool:
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
    def set_lsp_utils_settings(cls, value: dict[str, Any]) -> None:
        settings = sublime.load_settings(SETTINGS_FILENAME)
        for key, val in value.items():
            settings.set(key, val)
        sublime.save_settings(SETTINGS_FILENAME)

    @classmethod
    def remove_lsp_utils_settings(cls) -> None:
        settings_filepath = Path(sublime.packages_path(), 'User', SETTINGS_FILENAME)
        if settings_filepath.is_file():
            settings_filepath.unlink()
        sublime.save_settings(SETTINGS_FILENAME)

    @classmethod
    def tearDownClass(cls) -> GeneratorAny:
        wm = cls.wm()
        if (session := cls.session):
            cls.session = None
            sublime.set_timeout_async(session.end_async)
            yield lambda: session.state == ClientStates.STOPPING
            if cls.view:
                yield lambda: wm.get_session(cls.get_server_name(), cls.view.file_name()) is None
        cls.remove_lsp_utils_settings()
        super().tearDownClass()

    def doCleanups(self) -> GeneratorAny:  # noqa: N802
        if self.view and self.view.is_valid():
            yield from close_test_view(self.view)
        yield from super().doCleanups()
