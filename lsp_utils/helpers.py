from __future__ import annotations

from hashlib import md5
from os import PathLike
from typing import Any
from typing import Callable
from typing import Tuple
from typing import TYPE_CHECKING
import os
import shutil
import sublime
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import threading

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from sublime_lib import ResourcePath

StringCallback = Callable[[str], None]
SemanticVersion = Tuple[int, int, int]

is_windows = sublime.platform() == 'windows'


def prepend_to_path(path: str | list[str] | None, extra_paths: Sequence[str]) -> str:
    """
    Return `path` (a `PATH` string or a list of its entries) with `extra_paths` put first.

    Empty entries are dropped and entries of `extra_paths` that are already in `path` are moved to the front instead
    of being added again.
    """
    original_paths = path.split(os.pathsep) if isinstance(path, str) else (path or [])
    return os.pathsep.join([*extra_paths, *(p for p in original_paths if p and p not in extra_paths)])


def start_process(
    args: Sequence[str | PathLike[str]],
    *,
    stdin: int = subprocess.PIPE,
    stdout: int = subprocess.PIPE,
    stderr: int = subprocess.PIPE,
    cwd: str | PathLike[str] | None = None,
    extra_env: dict[str, str] | None = None,  # merged with envs obtained from current process
    extra_paths: list[str] | None = None,  # prepended to the PATH
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    if extra_paths:
        env['PATH'] = prepend_to_path(env.get('PATH'), extra_paths)
    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
    return subprocess.Popen(  # ruff: ignore[subprocess-without-shell-equals-true]
        args, stdin=stdin, stdout=stdout, stderr=stderr, cwd=cwd, env=env, startupinfo=startupinfo)


def run_command_sync(
    args: Sequence[str | PathLike[str]],
    cwd: str | PathLike[str] | None = None,
    env: dict[str, str] | None = None,  # used as is, without merging with process envs
    extra_env: dict[str, str] | None = None,  # merged with envs obtained from current process
    extra_paths: list[str] | None = None,
    *,
    shell: bool = is_windows,
) -> tuple[str, str | None]:
    """
    Run the given command synchronously.

    :returns: A two-element tuple with the returned value and an optional error. If running the command has failed, the
              first tuple element will be empty string and the second will contain the potential `stderr` output. If the
              command has succeeded then the second tuple element will be `None`.
    """
    if extra_paths is None:
        extra_paths = []
    final_env = None
    if env:
        final_env = env
    elif extra_env or extra_paths:
        final_env = os.environ.copy()
        if extra_env:
            final_env.update(extra_env)
        if extra_paths:
            final_env['PATH'] = prepend_to_path(final_env.get('PATH'), extra_paths)
    startupinfo = None
    if is_windows:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
    try:
        output = subprocess.check_output(  # ruff: ignore[subprocess-without-shell-equals-true]
            args, cwd=cwd, shell=shell, stderr=subprocess.STDOUT, env=final_env, startupinfo=startupinfo)
    except subprocess.CalledProcessError as error:
        return ('', decode_bytes(error.output).strip())
    return (decode_bytes(output).strip(), None)


def run_command_async(
    args: Sequence[str | PathLike[str]], on_success: StringCallback, on_error: StringCallback, **kwargs: Any,
) -> None:
    """
    Run the given command asynchronously.

    On success calls the provided `on_success` callback with the value the the command has returned.
    On error calls the provided `on_error` callback with the potential `stderr` output.
    """

    def execute(on_success: StringCallback, on_error: StringCallback, args: list[str | PathLike[str]]) -> None:
        result, error = run_command_sync(args, **kwargs)
        on_error(error) if error is not None else on_success(result)

    thread = threading.Thread(target=execute, args=(on_success, on_error, args))
    thread.start()


def run_command_ex(*cmd: str | PathLike[str], cwd: str | PathLike[str] | None = None) -> str:
    output, error = run_command_sync(list(cmd), cwd=cwd)
    if error:
        raise Exception(error)
    return output


def decode_bytes(data: bytes) -> str:
    """Decode provided bytes using `utf-8` decoding, ignoring potential decoding errors."""
    return data.decode('utf-8', 'ignore')


def rmtree_ex(path: str | Path, *, ignore_errors: bool = False) -> None:
    # On Windows, "shutil.rmtree" will raise file not found errors when deleting a long path (>255 chars).
    # See https://stackoverflow.com/a/14076169/4643765
    # See https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation
    path = fR'\\?\{path}' if sublime.platform() == 'windows' else path
    shutil.rmtree(path, ignore_errors)


def version_to_string(version: SemanticVersion) -> str:
    """Return a string representation of a version tuple."""
    return '.'.join([str(c) for c in version])


def is_hash_equal(resource_path: ResourcePath, filesystem_path: Path, *, ignore_missing_source: bool = False) -> bool:
    if not resource_path.exists():
        if ignore_missing_source:
            return True
        msg = f'Resource "{resource_path}" does not exist inside the package'
        raise RuntimeError(msg)
    if not filesystem_path.exists():
        return False
    source_hash = md5(resource_path.read_bytes()).hexdigest()  # ruff: ignore[hashlib-insecure-hash-function]
    try:
        return source_hash == md5(filesystem_path.read_bytes()).hexdigest()  # ruff: ignore[hashlib-insecure-hash-function]
    except FileNotFoundError:
        pass
    return False
