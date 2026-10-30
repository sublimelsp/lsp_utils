from __future__ import annotations

from ._util import get_host_arch

HOST_ARCH = get_host_arch()
"""
The native architecture of the host machine: `"x32"`, `"x64"` or `"arm64"`.

Unlike `sublime.arch()`, it reports the architecture of the machine rather than of Sublime Text on Windows, for
example when an x64 build of Sublime Text runs emulated on an ARM64 machine.
"""
INSTALLING_MARKER_FILE = '.installing'
SETTINGS_FILENAME = 'lsp_utils.sublime-settings'
"""The name of the lsp_utils settings file."""
