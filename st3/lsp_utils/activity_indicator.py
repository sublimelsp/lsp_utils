from abc import ABCMeta, abstractmethod
from LSP.plugin.core.typing import Optional, Union
from types import TracebackType
from uuid import uuid4
import sublime


__all__ = ['ActivityIndicator']


class StatusTarget(metaclass=ABCMeta):
    @abstractmethod
    def set(self, message: str) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...


class WindowTarget(StatusTarget):
    def __init__(self, window: sublime.Window) -> None:
        self.window = window

    def set(self, message: str) -> None:
        self.window.status_message(message)

    def clear(self) -> None:
        self.window.status_message("")


class ViewTarget(StatusTarget):
    def __init__(self, view: sublime.View, key: Optional[str] = None) -> None:
        self.view = view
        if key is None:
            self.key = '_{!s}'.format(uuid4())
        else:
            self.key = key

    def set(self, message: str) -> None:
        self.view.set_status(self.key, message)

    def clear(self) -> None:
        self.view.erase_status(self.key)


class ActivityIndicator:
    """
    An animated text-based indicator to show that some activity is in progress.

    The `target` argument should be a :class:`sublime.View` or :class:`sublime.Window`.
    The indicator will be shown in the status bar of that view or window.
    If `label` is provided, then it will be shown next to the animation.

    :class:`ActivityIndicator` can be used as a context manager.

    .. versionadded:: 1.11.0
    """
    width = 10  # type: int
    interval = 100  # type: float

    _target = None  # type: Optional[StatusTarget]

    def __init__(self, target: Union[StatusTarget, sublime.View, sublime.Window], label: Optional[str] = None) -> None:
        self._label = label

        if isinstance(target, sublime.View):
            self._target = ViewTarget(target)
        elif isinstance(target, sublime.Window):
            self._target = WindowTarget(target)
        else:
            self._target = target

        self._ticks = 0
        self._state = False

    def __del__(self) -> None:
        if self._state:
            self.stop()

    def __enter__(self) -> None:
        self.start()

    def __exit__(self, exc_type: type, exc_value: Exception, traceback: TracebackType) -> None:
        self.stop()

    def start(self) -> None:
        """
        Start displaying the indicator and animate it.

        :raise ValueError: if the indicator is already running.
        """
        if self._state:
            raise ValueError('Timer is already running')
        else:
            self._state = True
            self._update()
            self._run()

    def stop(self) -> None:
        """
        Stop displaying the indicator.

        If the indicator is not running, do nothing.
        """
        self._state = False
        self._target.clear()

    def set_label(self, label: str) -> None:
        """
        Updates the label of the indicator.

        :param label: The new label text
        """
        self._label = label
        if self._state:
            self._update()

    def _run(self) -> None:
        sublime.set_timeout(self._tick, self.interval)

    def _tick(self) -> None:
        if self._state:
            self._ticks += 1
            self._update()
            self._run()

    def _update(self) -> None:
        self._target.set(self._render(self._ticks))

    def _render(self, ticks: int) -> str:
        status = ticks % (2 * self.width)
        before = min(status, (2 * self.width) - status)
        after = self.width - before

        return "{}[{}={}]".format(self._label + ' ' if self._label else '', " " * before, " " * after)
