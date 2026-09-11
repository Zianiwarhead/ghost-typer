"""
focus_guard_linux.py — Linux window focus tracking via xdotool.

Works on X11 and XWayland-backed sessions (this covers Steam Deck / SteamOS
desktop mode via Gamescope's XWayland layer, and most X11 desktops).

Does NOT work on pure-Wayland compositors (GNOME Wayland, KDE Wayland
without XWayland) — Wayland's security model blocks apps from querying the
focused window without compositor-specific permissions. This is a platform
limitation, not something we can work around here. When it's unavailable we
degrade gracefully: typing still works, just without auto-pause-on-switch.
"""

import os
import shutil
import subprocess
import threading
import time

_XDOTOOL = shutil.which("xdotool")

# A pure-Wayland session (no XWayland) is the one case xdotool can't help
# with even if it's installed. XWayland-backed sessions (incl. SteamOS
# Gamescope) still work fine — we don't try to distinguish those here,
# we just let the first xdotool call fail and degrade at that point.
_SESSION_TYPE = os.environ.get("XDG_SESSION_TYPE", "").lower()
AVAILABLE = _XDOTOOL is not None


def _run(*args: str) -> str | None:
    try:
        result = subprocess.run(
            [_XDOTOOL, *args], capture_output=True, text=True, timeout=1.0, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.SubprocessError, OSError):
        return None


def _get_active_window_id() -> str | None:
    return _run("getactivewindow")


def _get_window_title(win_id: str | None) -> str:
    if not win_id:
        return ""
    return _run("getwindowname", win_id) or ""


class LinuxFocusGuard:
    """Watches the active window during a typing session (xdotool)."""

    available = AVAILABLE
    unavailable_reason = (
        "xdotool not found — run: sudo apt install xdotool (or your distro's "
        "equivalent). Note: pure-Wayland sessions aren't supported even with "
        "xdotool installed; XWayland sessions (incl. SteamOS desktop mode) work."
    )

    def __init__(self, pause_flag: list, stop_flag: list):
        self.pause_flag = pause_flag
        self.stop_flag = stop_flag
        self.target_id: str | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._confirmed_working = False

    def lock_to_current_window(self) -> str:
        if not AVAILABLE:
            return f"unknown ({self.unavailable_reason})"
        self.target_id = _get_active_window_id()
        if self.target_id is None:
            # xdotool is present but couldn't query the session — most
            # likely pure Wayland. Degrade for the rest of this session.
            self.available = False
            return "unknown (xdotool couldn't query this session — likely pure Wayland)"
        self._confirmed_working = True
        return _get_window_title(self.target_id)

    def start_watching(self) -> None:
        if not self.available or not self._confirmed_working:
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
            if current != self.target_id:
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


# Always export the real class (even when AVAILABLE is False) so
# unavailable_reason keeps the helpful xdotool message instead of the
# generic NullFocusGuard one. lock_to_current_window() / start_watching()
# already degrade gracefully when AVAILABLE is False.
FocusGuard = LinuxFocusGuard
