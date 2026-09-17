"""
webapp.py — Ghost Typer desktop UI entry point.

Loads webui/index.html in a native window via pywebview and exposes a
small JS-callable Api that drives the existing core/ engine. This is an
additional front end, not a replacement — main.py (CLI) and gui.py
(Tk mini-GUI) are untouched and still work.

Run:  python webapp.py
Needs:  pip install -e ".[webui]"   (pywebview; everything else is base deps)
"""

import os
import threading
import time

from core.controller import SessionController
from core.engine import TypingEngine
from core.focus_guard import BACKEND_AVAILABLE, FocusGuard
from core.profiles import clamp_wpm, get_profile

WEBUI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webui")


class Api:
    """Methods here are callable from JS as window.pywebview.api.<name>(...)."""

    def __init__(self):
        self.controller = SessionController()
        self._status_message = "Paste text, pick a feel, press Start."
        self._running = False  # True for the whole countdown + typing lifecycle
        self._lock = threading.Lock()

    # ---------------- text input helpers ---------------- #

    def paste_clipboard(self):
        try:
            import pyperclip
            return pyperclip.paste()
        except Exception:
            return ""

    def load_file(self):
        import webview

        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Text files (*.txt;*.md)", "All files (*.*)"),
        )
        if not result:
            return None
        path = result[0]
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    # ---------------- environment check ---------------- #

    def run_doctor(self):
        import contextlib
        import io

        from core.doctor import run

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                run()
        except Exception as e:
            return f"Check failed: {e}"
        return buf.getvalue() or "No issues found."

    # ---------------- session control ---------------- #

    def start(self, payload: dict):
        if self._running:
            return False

        text = payload.get("text", "")
        profile = get_profile(payload.get("profile", "normal"))
        profile["wpm"] = clamp_wpm(int(payload.get("wpm", profile["wpm"])))
        profile["chat_mode"] = bool(payload.get("chat_mode", False))
        use_focus_lock = bool(payload.get("focus_lock", True))
        countdown = max(2, int(payload.get("countdown", 5)))
        resume = bool(payload.get("resume", False)) and self.controller.has_resume()

        self._running = True
        self._set_status(f"Starting in {countdown}s — click your target now…")
        threading.Thread(
            target=self._run,
            args=(text, profile, use_focus_lock, countdown, resume),
            daemon=True,
        ).start()
        return True

    def pause(self):
        self.controller.toggle_pause()
        return self.controller.is_paused()

    def stop(self):
        self.controller.stop_session(soft=True)
        return True

    def get_status(self):
        total = self.controller.last_total or 0
        idx = self.controller.last_index or 0
        return {
            "typing": self._running,
            "paused": self.controller.is_paused(),
            "index": idx,
            "total": total,
            "has_resume": self.controller.has_resume(),
            "message": self._status_message,
        }

    # ---------------- internals ---------------- #

    def _set_status(self, msg: str):
        with self._lock:
            self._status_message = msg

    def _run(self, text, profile, use_focus_lock, countdown, resume):
        try:
            self._run_inner(text, profile, use_focus_lock, countdown, resume)
        finally:
            # Never leave the UI stuck on "typing" if something blew up.
            self._running = False

    def _run_inner(self, text, profile, use_focus_lock, countdown, resume):
        for i in range(countdown, 0, -1):
            if self.controller.stop_flag[0]:
                self._set_status("Cancelled.")
                return
            self._set_status(f"Starting in {i}s — click your target now…")
            time.sleep(1)

        start_index = 0
        if resume and self.controller.has_resume():
            start_index = self.controller.last_index
            text = self.controller.last_text
            profile = self.controller.last_profile or profile

        self.controller.stop_flag[0] = False
        self.controller.pause_flag[0] = False
        if not resume:
            self.controller.save_session(text, profile)
        else:
            self.controller.last_profile = dict(profile)

        focus_guard = FocusGuard(self.controller.pause_flag, self.controller.stop_flag)
        if use_focus_lock and BACKEND_AVAILABLE:
            try:
                focus_guard.lock_to_current_window()
                focus_guard.start_watching()
            except Exception:
                pass

        engine = TypingEngine(profile, self.controller.stop_flag, emit_hook=self.controller.mark_own_emit)
        self.controller.start_interference_watch()

        def progress(cur, tot):
            self.controller.wait_if_paused()
            self.controller.update_index(cur, tot)
            self._set_status(f"Typing… {cur}/{tot} characters")

        # Mark as "typing" for is_typing() to report True during this run.
        self.controller._typing_thread = threading.current_thread()

        ok = engine.type_text(text, progress_callback=progress, start_index=start_index)

        try:
            focus_guard.stop_watching()
        except Exception:
            pass
        try:
            self.controller.stop_interference_watch()
        except Exception:
            pass

        if ok:
            self.controller.clear_session()
            self._set_status("Done.")
        else:
            info = self.controller.get_resume_info()
            self._set_status(f"Stopped at {info['index']}/{info['total']} characters — press Resume to continue.")


def main():
    import webview

    api = Api()
    webview.create_window(
        "Ghost Typer",
        os.path.join(WEBUI_DIR, "index.html"),
        js_api=api,
        width=780,
        height=820,
        min_size=(560, 640),
        background_color="#171B24",
    )
    webview.start()


if __name__ == "__main__":
    main()
