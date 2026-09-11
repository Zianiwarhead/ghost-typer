"""
focus_guard.py — Windows window focus tracking.
Locks typing to the target window and pauses if user switches away.
"""

import threading
import time

try:
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


def get_active_window_id() -> int | None:
    """Returns the handle of the currently focused window."""
    if not WIN32_AVAILABLE:
        return None
    return win32gui.GetForegroundWindow()


def get_window_title(hwnd: int) -> str:
    if not WIN32_AVAILABLE:
        return ""
    return win32gui.GetWindowText(hwnd)


class FocusGuard:
    """
    Watches the active window during a typing session.
    If the user switches away, typing PAUSES until they return.
    """

    def __init__(self, pause_flag: list, stop_flag: list):
        self.pause_flag = pause_flag
        self.stop_flag = stop_flag
        self.target_hwnd: int | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self.available = WIN32_AVAILABLE

    def lock_to_current_window(self) -> str:
        """
        Call this right before typing starts.
        Records the current window as the target.
        Returns the window title for display.
        """
        if not WIN32_AVAILABLE:
            return "unknown (pywin32 not installed)"
        self.target_hwnd = get_active_window_id()
        return get_window_title(self.target_hwnd)

    def start_watching(self) -> None:
        """Starts the focus watcher in a background thread."""
        if not WIN32_AVAILABLE:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop_watching(self) -> None:
        self._running = False

    def _watch_loop(self) -> None:
        was_paused_by_us = False
        while self._running and not self.stop_flag[0]:
            current = get_active_window_id()
            if current != self.target_hwnd:
                # User switched away — pause typing
                if not self.pause_flag[0]:
                    self.pause_flag[0] = True
                    was_paused_by_us = True
                    title = get_window_title(current) or "unknown window"
                    print(f"\n  [PAUSED] Focus lost -> switched to '{title}'")
                    print("  Switch back to continue typing.")
            else:
                # Back on target — resume if we paused it
                if was_paused_by_us and self.pause_flag[0]:
                    self.pause_flag[0] = False
                    was_paused_by_us = False
                    print("\n  [RESUMED] Focus restored — resuming...")
            time.sleep(0.3)