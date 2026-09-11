"""
focus_guard_macos.py — macOS focus tracking via NSWorkspace (app-level).

Deliberately app-level, not window-level:
  - NSWorkspace.frontmostApplication needs zero permissions, works instantly.
  - True window-level tracking needs the Accessibility API (AXUIElement),
    which requires the user to grant Accessibility permission in
    System Settings -> Privacy & Security -> Accessibility. That's real
    friction for a tool people are trying out casually, so it's not the
    default. (Leaving the door open for a future --strict-focus flag that
    opts into the Accessibility API for people who need per-window precision.)

Blind spot of app-level tracking: switching between two windows of the SAME
app (e.g. two Chrome windows) won't register as a focus change. Acceptable
trade-off for the zero-friction default.
"""

import threading
import time

try:
    from AppKit import NSWorkspace
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


def _get_frontmost_app_id() -> str | None:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return None
    return app.bundleIdentifier() or app.localizedName()


def _get_frontmost_app_name() -> str:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.localizedName() if app else ""


class MacOSFocusGuard:
    """Watches the frontmost app during a typing session (NSWorkspace, app-level)."""

    available = AVAILABLE
    unavailable_reason = "pyobjc not installed — run: pip install pyobjc-framework-Cocoa"

    def __init__(self, pause_flag: list, stop_flag: list):
        self.pause_flag = pause_flag
        self.stop_flag = stop_flag
        self.target_id: str | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def lock_to_current_window(self) -> str:
        if not AVAILABLE:
            return f"unknown ({self.unavailable_reason})"
        self.target_id = _get_frontmost_app_id()
        return _get_frontmost_app_name()

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
            current = _get_frontmost_app_id()
            if current != self.target_id:
                if not self.pause_flag[0]:
                    self.pause_flag[0] = True
                    was_paused_by_us = True
                    name = _get_frontmost_app_name() or "unknown app"
                    print(f"\n  [PAUSED] Focus lost -> switched to '{name}'")
                    print("  Switch back to continue typing.")
            else:
                if was_paused_by_us and self.pause_flag[0]:
                    self.pause_flag[0] = False
                    was_paused_by_us = False
                    print("\n  [RESUMED] Focus restored — resuming...")
            time.sleep(0.3)


# Always export the real class (even when AVAILABLE is False) so
# unavailable_reason keeps the helpful pyobjc message instead of the
# generic NullFocusGuard one. lock_to_current_window() / start_watching()
# already degrade gracefully when AVAILABLE is False.
FocusGuard = MacOSFocusGuard
