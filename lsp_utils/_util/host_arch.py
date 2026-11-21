from __future__ import annotations

from enum import IntEnum
from typing import cast
from typing import Literal
import ctypes
import sublime

Architecture = Literal["x32", "x64", "arm64"]


class ImageFileMachine(IntEnum):
    IMAGE_FILE_MACHINE_AMD64 = 0x8664
    IMAGE_FILE_MACHINE_ARM64 = 0xAA64
    IMAGE_FILE_MACHINE_I386 = 0x014C
    IMAGE_FILE_MACHINE_UNKNOWN = 0x0000


MACHINE_NAMES: dict[ImageFileMachine, Architecture] = {
    ImageFileMachine.IMAGE_FILE_MACHINE_AMD64: "x64",
    ImageFileMachine.IMAGE_FILE_MACHINE_ARM64: "arm64",
    ImageFileMachine.IMAGE_FILE_MACHINE_I386: "x32",
    ImageFileMachine.IMAGE_FILE_MACHINE_UNKNOWN: "x64",
}


def get_host_arch() -> Architecture:
    if sublime.platform() == "windows":
        kernel32 = ctypes.windll.kernel32
        if not hasattr(kernel32, "IsWow64Process2"):
            # IsWow64Process2 is only available since Windows 10 1703. Older versions don't run x86/x64 apps on ARM64
            # so the host is x64 if this process runs under WOW64 and the same as the process architecture otherwise.
            is_wow64 = ctypes.c_int(0)
            kernel32.IsWow64Process.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
            if kernel32.IsWow64Process(kernel32.GetCurrentProcess(), ctypes.byref(is_wow64)) and is_wow64.value:
                return "x64"
            return sublime.arch()
        c_ushort_p = ctypes.POINTER(ctypes.c_ushort)
        kernel32.IsWow64Process2.argtypes = (ctypes.c_void_p, c_ushort_p, c_ushort_p)
        process_machine = ctypes.c_ushort(0)
        native_machine = ctypes.c_ushort(0)
        success = kernel32.IsWow64Process2(
            kernel32.GetCurrentProcess(), ctypes.byref(process_machine), ctypes.byref(native_machine))
        if success:
            return MACHINE_NAMES[cast("ImageFileMachine", native_machine.value)]
    return sublime.arch()
