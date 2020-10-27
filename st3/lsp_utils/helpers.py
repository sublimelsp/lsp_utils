from LSP.plugin.core.typing import Callable, List, Optional, Tuple
import re
import sublime
import subprocess
import threading

StringCallback = Callable[[str], None]
SemanticVersion = Tuple[int, int, int]


def run_command_sync(args: List[str]) -> Tuple[str, Optional[str]]:
    try:
        output = subprocess.check_output(
            args, shell=sublime.platform() == 'windows', stderr=subprocess.STDOUT)
        return (decode_bytes(output).strip(), None)
    except subprocess.CalledProcessError as error:
        return ('', decode_bytes(error.output).strip())


def run_command_async(popen_args, on_success: StringCallback, on_error: StringCallback) -> None:
    """
    Runs the given args in a subprocess.Popen, and then calls the function
    on_success when the subprocess completes.
    on_success is a callable object, and popen_args is a list/tuple of args that
    on_error when the subprocess throws an error
    would give to subprocess.Popen.
    """

    def execute(on_success, on_error, popen_args):
        result, error = run_command_sync(popen_args)
        on_error(error) if error is not None else on_success(result)

    thread = threading.Thread(target=execute, args=(on_success, on_error, popen_args))
    thread.start()


def decode_bytes(data: bytes) -> str:
    return data.decode('utf-8', 'ignore')


def parse_version(version: str) -> SemanticVersion:
    """Convert filename to version tuple (major, minor, patch)."""
    match = re.match(r'v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-.+)?', version)
    if match:
        major, minor, patch = match.groups()
        return int(major), int(minor), int(patch)
    else:
        return 0, 0, 0


def version_to_string(version: SemanticVersion) -> str:
    return '.'.join([str(c) for c in version])


def log_and_show_message(msg, additional_logs: str = None, show_in_status: bool = True) -> None:
    print(msg, '\n', additional_logs) if additional_logs else print(msg)
    if show_in_status:
        sublime.active_window().status_message(msg)
