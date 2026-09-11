"""
focus_guard_base.py — shared interface + no-op fallback backend.

Every platform backend (windows/linux/macos) implements this same shape:
    .available            bool
    .lock_to_current_window() -> str   (window/app title, or explanation)
    .start_watching()      -> None
    .stop_watching()       -> None

NullFocusGuard is used when the platform isn't supported, or the platform's
optional dependency (pywin32 / xdotool / pyobjc) isn't installed. Typing
still works — it just runs without the auto-pause-on-switch safety net.
"""


class NullFocusGuard:
    available = False
    unavailable_reason = "focus lock not supported on this platform"

    def __init__(self, pause_flag: list, stop_flag: list):
        self.pause_flag = pause_flag
        self.stop_flag = stop_flag

    def lock_to_current_window(self) -> str:
        return f"unknown ({self.unavailable_reason})"

    def start_watching(self) -> None:
        return None

    def stop_watching(self) -> None:
        return None
