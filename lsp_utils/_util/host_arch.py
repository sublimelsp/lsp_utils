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
        c_ushort_p = ctypes.POINTER(ctypes.c_ushort)
        kernel32.IsWow64Process2.argtypes = (ctypes.c_void_p, c_ushort_p, c_ushort_p)
        process_machine = ctypes.c_ushort(0)
        native_machine = ctypes.c_ushort(0)
        success = kernel32.IsWow64Process2(
            kernel32.GetCurrentProcess(), ctypes.byref(process_machine), ctypes.byref(native_machine))
        if success:
            return MACHINE_NAMES[cast("ImageFileMachine", native_machine.value)]
    return sublime.arch()
