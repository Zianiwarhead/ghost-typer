"""
focus_guard_windows.py — Windows window focus tracking (win32gui).
Locks typing to the target window and pauses if user switches away.
"""

import threading
import time

try:
    import win32gui
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


def _get_active_window_id() -> int | None:
    return win32gui.GetForegroundWindow()


def _get_window_title(hwnd: int) -> str:
    return win32gui.GetWindowText(hwnd)


class WindowsFocusGuard:
    """Watches the active window during a typing session (win32gui)."""

    available = AVAILABLE
    unavailable_reason = "pywin32 not installed — run: pip install pywin32"

    def __init__(self, pause_flag: list, stop_flag: list):
        self.pause_flag = pause_flag
        self.stop_flag = stop_flag
        self.target_hwnd: int | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def lock_to_current_window(self) -> str:
        if not AVAILABLE:
            return f"unknown ({self.unavailable_reason})"
        self.target_hwnd = _get_active_window_id()
        return _get_window_title(self.target_hwnd)

    def start_watching(self) -> None:
        if not AVAILABLE:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop_watching(self) -> None:
        self._running = False

    def _watch_loop(self) -> None:
        was_paused_by_us = False
        while self._running and not self.stop_flag[0]:
            current = _get_active_window_id()
            if current != self.target_hwnd:
                if not self.pause_flag[0]:
                    self.pause_flag[0] = True
                    was_paused_by_us = True
                    title = _get_window_title(current) or "unknown window"
                    print(f"\n  [PAUSED] Focus lost -> switched to '{title}'")
                    print("  Switch back to continue typing.")
            else:
                if was_paused_by_us and self.pause_flag[0]:
                    self.pause_flag[0] = False
                    was_paused_by_us = False
                    print("\n  [RESUMED] Focus restored — resuming...")
            time.sleep(0.3)


# Picked up by the dispatcher (core/focus_guard.py).
# Always export the real class (even when AVAILABLE is False) so
# unavailable_reason keeps the helpful per-OS message instead of the
# generic NullFocusGuard one. lock_to_current_window() / start_watching()
# already degrade gracefully when AVAILABLE is False.
FocusGuard = WindowsFocusGuard
