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
    'compute_install_hash',
    'mark_in_use',
    'prepare_install_dir',
    'remove_unused_install_dirs_async',
]

# Bump to force re-installation into new directories.
INSTALL_LAYOUT_VERSION = '1'
INSTALLED_MARKER_FILE = '.lsp_utils-installed'
LAST_USED_MARKER_FILE = '.lsp_utils-last-used'
# How many alternative directories to try when a directory of an interrupted installation can't be removed.
MAX_INSTALL_DIR_SUFFIX = 5

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


def prepare_install_dir(
    parent: Path,
    name: str,
    install_hash: str,
    install: Callable[[Path], None],
    *,
    legacy_dirs: Sequence[Path] = (),
) -> Path:
    """
    Return the `<parent>/<name>-<install_hash>` installation directory, installing into it first if needed.

    Also starts removal of other installation directories of the same `name` that are no longer used.

    :param parent: The directory containing the installation directories.
    :param name: The name of the installation directories, without the hash.
    :param install_hash: The hash returned from :func:`compute_install_hash`.
    :param install: Called with the empty installation directory to install into. Should raise on failure.
    :param legacy_dirs: Unversioned installation directories of older lsp_utils versions to remove once unused.
    :returns: The path to the complete installation.
    """
    base_name = f'{name}-{install_hash}'
    candidates = [parent / base_name, *(parent / f'{base_name}-{i}' for i in range(1, MAX_INSTALL_DIR_SUFFIX + 1))]
    target = next((path for path in candidates if (path / INSTALLED_MARKER_FILE).is_file()), None)
    if not target:
        # Directories without the marker are leftovers of interrupted installations or removals.
        target = next((path for path in candidates if try_rmtree(path, attempts=1)), None)
        if not target:
            msg = f'Failed preparing installation directory "{parent / base_name}"'
            raise RuntimeError(msg)
        target.mkdir(parents=True)
        install(target)
        (target / INSTALLED_MARKER_FILE).touch()
    mark_in_use(target)
    pattern = re.compile(rf'{re.escape(name)}-[0-9a-f]{{8}}(-\d+)?')
    remove_unused_install_dirs_async(parent, pattern, keep=target, legacy_dirs=legacy_dirs)
    return target


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
