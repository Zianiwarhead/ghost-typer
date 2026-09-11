"""
focus_guard.py — platform dispatcher.

Picks the right backend by OS and re-exports a single FocusGuard class with
an identical interface everywhere:
    .available              bool
    .unavailable_reason     str  (why, if not available)
    .lock_to_current_window() -> str
    .start_watching()       -> None
    .stop_watching()        -> None

Callers (main.py, gui.py) don't need to know which OS they're on — they just
import FocusGuard and BACKEND_AVAILABLE from here.
"""

import platform

_SYSTEM = platform.system()

if _SYSTEM == "Windows":
    from core.focus_guard_windows import FocusGuard
elif _SYSTEM == "Darwin":
    from core.focus_guard_macos import FocusGuard
elif _SYSTEM == "Linux":
    from core.focus_guard_linux import FocusGuard
else:
    from core.focus_guard_base import NullFocusGuard as FocusGuard

BACKEND_AVAILABLE = FocusGuard.available

# Back-compat alias — older code (and anyone who forked pre-v2.1) may still
# import WIN32_AVAILABLE by name. Same meaning now: "is a real focus-guard
# backend available on this machine", not literally win32-specific anymore.
WIN32_AVAILABLE = BACKEND_AVAILABLE
