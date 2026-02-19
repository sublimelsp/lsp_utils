from __future__ import annotations

from os import PathLike
from typing import Any
from typing import Callable
from typing import Tuple
from typing import TYPE_CHECKING
import os
import shutil
import sublime
import subprocess  # noqa: S404
import threading

if TYPE_CHECKING:
    from pathlib import Path

StringCallback = Callable[[str], None]
SemanticVersion = Tuple[int, int, int]

is_windows = sublime.platform() == 'windows'


def platform_program_file_extension() -> str:
    return '.exe' if sublime.platform() == 'windows' else ''


def run_command_sync(
    args: list[str | PathLike[str]],
    cwd: str | PathLike[str] | None = None,
    extra_env: dict[str, str] | None = None,
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
    try:
        env = None
        if extra_env or extra_paths:
            env = os.environ.copy()
            if extra_env:
                env.update(extra_env)
            if extra_paths:
                env['PATH'] = os.path.pathsep.join(extra_paths) + os.path.pathsep + env['PATH']
        startupinfo = None
        if is_windows:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
        output = subprocess.check_output(  # noqa: S603
            args, cwd=cwd, shell=shell, stderr=subprocess.STDOUT, env=env, startupinfo=startupinfo)
        return (decode_bytes(output).strip(), None)
    except subprocess.CalledProcessError as error:
        return ('', decode_bytes(error.output).strip())


def run_command_async(
    args: list[str | PathLike[str]], on_success: StringCallback, on_error: StringCallback, **kwargs: Any,
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
