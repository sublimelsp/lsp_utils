"""
Versioned installation directories.

Every installation goes into its own directory, named after a hash of everything that affects the installation.
Updating never touches the directory of the previous version, which might still be in use by a running server
(and on Windows can't be removed while it is). Directories that are no longer current are removed only once they
were last used by an earlier run of Sublime Text.
"""

from __future__ import annotations

from ._util import logger
from .helpers import try_rmtree
from hashlib import md5
from typing import Callable
from typing import TYPE_CHECKING
import os
import re
import threading

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

__all__ = [
    'INSTALLED_MARKER_FILE',
    'InstallDirectory',
    'compute_install_hash',
    'mark_in_use',
    'remove_unused_install_dirs_async',
]

# Bump to force re-installation into new directories.
INSTALL_LAYOUT_VERSION = '1'
INSTALLED_MARKER_FILE = '.lsp_utils-installed'
LAST_USED_MARKER_FILE = '.lsp_utils-last-used'

_swept_patterns: set[str] = set()


def _get_run_id() -> str:
    # The PID of the Sublime Text process. Shared by all plugin hosts since those are its child processes.
    return str(os.getppid())


def compute_install_hash(*parts: bytes | str) -> str:
    """Return a short hash of all inputs that affect an installation."""
    digest = md5(INSTALL_LAYOUT_VERSION.encode('utf-8'))  # noqa: S324
    for part in parts:
        data = part.encode('utf-8') if isinstance(part, str) else part
        digest.update(len(data).to_bytes(8, 'little'))
        digest.update(data)
    return digest.hexdigest()[:8]


def mark_in_use(path: Path) -> None:
    """Record that the installation directory is used by the current run of Sublime Text."""
    marker = path / LAST_USED_MARKER_FILE
    run_id = _get_run_id()
    try:
        if marker.read_text(encoding='utf-8') == run_id:
            return
    except OSError:
        pass
    try:
        marker.write_text(run_id, encoding='utf-8')
    except OSError as error:
        logger.warning(f'Failed marking "{path}" as used: {error}')


def _is_used_in_this_run(path: Path) -> bool:
    try:
        return (path / LAST_USED_MARKER_FILE).read_text(encoding='utf-8') == _get_run_id()
    except FileNotFoundError:
        # Not known when it was last used (installed by an older lsp_utils version, for example). Claim it for this
        # run so that it gets removed during the next one.
        mark_in_use(path)
        return True
    except OSError:
        return True


class InstallDirectory:
    """
    A versioned installation directory of a server, named `<parent>/<name>-<hash>`.

    The hash covers everything that affects the installation (for example the server version, the platform or the
    contents of a lock file) so an update installs into a new directory instead of replacing files of a server that
    might still be running. Installation directories of the same `name` that are no longer current are removed in
    the background once they were last used by an earlier run of Sublime Text. Removal that fails (for example
    because files are locked on Windows) is retried during the next run.

    Example of a :class:`ServerResourceInterface` implementation that downloads a server:

    .. code:: py

        class MyServer(ServerResourceInterface):
            def __init__(self, storage_path: Path) -> None:
                self._install_dir = InstallDirectory(storage_path, 'server', SERVER_VERSION, sublime.platform())
                ...

            def needs_installation(self) -> bool:
                return self._install_dir.needs_installation()

            def install_or_update(self) -> None:
                self._install_dir.install(download_and_extract_server)

            @property
            def binary_path(self) -> str:
                return str(self._install_dir.path / 'bin' / 'server')
    """

    def __init__(self, parent: Path, name: str, *hash_parts: bytes | str, legacy_dirs: Sequence[Path] = ()) -> None:
        """
        Create an installation directory of the given name, with a hash of `hash_parts`.

        :param parent: The directory containing the installation directories. Typically the package storage.
        :param name: The name of the installation directories, without the hash. Must not be shared with other kinds
                     of installations within the same `parent`.
        :param hash_parts: All inputs that affect the installation.
        :param legacy_dirs: Unversioned installation directories used previously, to remove once unused.
        """
        self._parent = parent
        self._name = name
        self._legacy_dirs = legacy_dirs
        self.path = parent / f'{name}-{compute_install_hash(*hash_parts)}'
        """The path to the installation directory. Depends on the hash."""

    def is_installed(self) -> bool:
        """Return whether the installation into :attr:`path` has completed."""
        return (self.path / INSTALLED_MARKER_FILE).is_file()

    def needs_installation(self) -> bool:
        """
        Return whether :meth:`install` needs to be called.

        If the installation is complete, it is recorded as used instead, the same as :meth:`install` would do. Call
        this or :meth:`install` before every start of the server so that the directory isn't removed while in use.
        """
        if not self.is_installed():
            return True
        self._use()
        return False

    def install(self, install: Callable[[Path], None]) -> Path:
        """
        Install into :attr:`path` unless already installed, and record it as used.

        :param install: Called with the empty installation directory to install into. Should raise on failure.
        :returns: The path to the complete installation.
        """
        if not self.is_installed():
            # A directory without the marker is a leftover of an interrupted installation or removal.
            if not try_rmtree(self.path):
                msg = f'Failed removing incomplete installation directory "{self.path}"'
                raise RuntimeError(msg)
            self.path.mkdir(parents=True)
            install(self.path)
            (self.path / INSTALLED_MARKER_FILE).touch()
        self._use()
        return self.path

    def _use(self) -> None:
        mark_in_use(self.path)
        pattern = re.compile(rf'{re.escape(self._name)}-[0-9a-f]{{8}}')
        remove_unused_install_dirs_async(self._parent, pattern, keep=self.path, legacy_dirs=self._legacy_dirs)


def remove_unused_install_dirs_async(
    parent: Path, pattern: re.Pattern[str], *, keep: Path, legacy_dirs: Sequence[Path] = (),
) -> None:
    """
    Remove directories within `parent` matching `pattern` that were not used during the current run of Sublime Text.

    Runs in the background, once per run for the given `parent` and `pattern`. Directories that can't be removed are
    retried during the next run.

    :param parent: The directory containing the installation directories.
    :param pattern: Matches the names of the installation directories.
    :param keep: The current installation directory which is never removed.
    :param legacy_dirs: Additional directories to remove once unused.
    """
    key = f'{parent}\n{pattern.pattern}'
    if key in _swept_patterns:
        return
    _swept_patterns.add(key)
    try:
        entries = [path for path in parent.iterdir() if path.is_dir() and pattern.fullmatch(path.name)]
    except OSError:
        entries = []
    entries.extend(path for path in legacy_dirs if path.is_dir())
    unused = [path for path in entries if path != keep and not _is_used_in_this_run(path)]
    if not unused:
        return

    def remove() -> None:
        for path in unused:
            logger.info(f'Removing unused installation: {path}')
            try:
                # Invalidate the installation first so that a partial removal is never mistaken for a valid one.
                (path / INSTALLED_MARKER_FILE).unlink(missing_ok=True)
            except OSError:
                continue
            try_rmtree(path)

    threading.Thread(target=remove, daemon=True).start()
