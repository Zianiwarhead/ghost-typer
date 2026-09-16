"""
doctor.py — environment self-check (python main.py --doctor).

Reports each capability as OK or DEGRADED with the fix, so a failing setup
explains itself instead of dying mysteriously. Returns process exit code.
"""

import os
import platform
import sys


def _try_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def run() -> int:
    print("\n  GhostTyper doctor — environment check\n")
    ok_all = True

    def line(ok: bool, label: str, hint: str = "") -> None:
        nonlocal ok_all
        ok_all = ok_all and ok
        status = "OK      " if ok else "DEGRADED"
        print(f"  [{status}] {label}" + (f" — {hint}" if hint and not ok else ""))

    line(sys.version_info >= (3, 10),
         f"Python {platform.python_version()}",
         "need Python 3.10+ from python.org")
    line(_try_import("pynput"), "pynput (keystroke injection)",
         "run: pip install pynput")
    line(_try_import("pyperclip"), "pyperclip (clipboard)",
         "run: pip install pyperclip")
    line(_try_import("tkinter"), "tkinter (GUI)",
         "reinstall Python with 'tcl/tk and IDLE' checked")
    line(_try_import("PIL"), "Pillow (icon generation)",
         "run: pip install Pillow")

    system = platform.system()
    if system == "Windows":
        line(_try_import("win32gui"), "pywin32 (focus lock, background mode)",
             "run: pip install pywin32")
    elif system == "Darwin":
        line(_try_import("AppKit"), "pyobjc (macOS focus lock)",
             "run: pip install pyobjc-framework-Cocoa (optional)")
    else:
        import shutil
        line(shutil.which("xdotool") is not None, "xdotool (Linux focus lock)",
             "run: sudo apt install xdotool (optional)")
        session = os.environ.get("XDG_SESSION_TYPE", "")
        if session.lower() == "wayland":
            print("  [INFO   ] Pure Wayland session: focus lock unavailable, "
                  "typing still works")

    # Clipboard round-trip (save, sentinel, restore).
    clip_ok, clip_hint = False, "copy/paste failed"
    try:
        import pyperclip
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = ""
        pyperclip.copy("__ghost_doctor__")
        clip_ok = pyperclip.paste() == "__ghost_doctor__"
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
        if not clip_ok and system == "Linux":
            clip_hint += " — need xclip or xsel: sudo apt install xclip"
    except Exception:
        pass
    line(clip_ok, "clipboard round-trip", clip_hint)

    try:
        from core.focus_guard import BACKEND_AVAILABLE, FocusGuard
        guard = FocusGuard([False], [False])
        reason = getattr(guard, "unavailable_reason", "")
        line(bool(BACKEND_AVAILABLE),
             f"focus lock backend ({FocusGuard.__name__})",
             reason or "backend unavailable")
    except Exception as e:
        line(False, "focus lock backend", str(e))

    try:
        from core import background as bg
        line(bg.available(), "background delivery (HWND/WM_PASTE)",
             "Windows + pywin32 only" if system != "Windows" else "install pywin32")
    except Exception as e:
        line(False, "background delivery", str(e))

    print()
    print("  Result:", "all systems go." if ok_all else "some checks degraded (see hints).")
    print()
    return 0 if ok_all else 1
