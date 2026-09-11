"""
Tests for the focus-guard dispatcher and per-OS backends.

Runs on whichever OS the CI matrix executes it on — each backend degrades
gracefully to NullFocusGuard-like behavior when its optional dependency
(pywin32 / xdotool / pyobjc) isn't installed, so these tests never require
special OS setup to pass.
"""

import platform

from core.focus_guard import FocusGuard
from core.focus_guard_base import NullFocusGuard


def test_dispatcher_picks_a_backend_for_current_os():
    # Whatever backend is picked, it must expose the shared interface.
    assert hasattr(FocusGuard, "available")
    assert hasattr(FocusGuard, "lock_to_current_window")
    assert hasattr(FocusGuard, "start_watching")
    assert hasattr(FocusGuard, "stop_watching")


def test_dispatcher_matches_running_platform():
    system = platform.system()
    name = FocusGuard.__name__
    if system == "Windows":
        assert name in ("WindowsFocusGuard", "NullFocusGuard")
    elif system == "Darwin":
        assert name in ("MacOSFocusGuard", "NullFocusGuard")
    elif system == "Linux":
        assert name in ("LinuxFocusGuard", "NullFocusGuard")
    else:
        assert name == "NullFocusGuard"


def test_focus_guard_never_crashes_when_unavailable():
    """If the backend isn't available, calls must degrade, never raise."""
    pause_flag = [False]
    stop_flag = [False]
    guard = FocusGuard(pause_flag, stop_flag)

    title = guard.lock_to_current_window()
    assert isinstance(title, str)

    if not guard.available:
        # Should be a no-op, not an exception.
        guard.start_watching()
        guard.stop_watching()


def test_null_focus_guard_interface():
    guard = NullFocusGuard([False], [False])
    assert guard.available is False
    assert "not supported" in guard.lock_to_current_window()
    guard.start_watching()  # no-op, must not raise
    guard.stop_watching()  # no-op, must not raise
