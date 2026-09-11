"""
controller.py — Manages the typing session lifecycle.
Hotkeys, threading, pause/resume, soft-stop with in-memory resume,
and physical-typing interference auto-pause.
"""

import threading
import time
from collections import deque
from collections.abc import Callable

from pynput import keyboard as kb


class SessionController:
    def __init__(self):
        self.stop_flag = [False]
        self.pause_flag = [False]
        self._typing_thread: threading.Thread | None = None
        self._hotkey_listener: kb.GlobalHotKeys | None = None
        self._interference_listener = None

        # Typed as Optional[Callable] to satisfy Pylance
        self.on_start: Callable | None = None
        self.on_stop: Callable | None = None  # called on soft-stop; receives resume info dict
        self.on_pause_toggle: Callable | None = None
        self.on_interference: Callable | None = None

        # In-memory resume state (cleared on successful finish / new text)
        self.last_text: str | None = None
        self.last_profile: dict | None = None
        self.last_index: int = 0
        self.last_total: int = 0

        # Own-keypress ledger — engine calls mark_own_emit(key_id) before
        # each synthetic press so the interference guard doesn't flag our
        # own typing (including backspace corrections). Entries expire
        # after _own_emit_window seconds. key_id None = wildcard (legacy).
        self._own_emits: deque = deque(maxlen=32)
        self._own_emit_window: float = 0.6

    # ------------------------------------------------------------------ #
    #  SESSION STATE / RESUME                                              #
    # ------------------------------------------------------------------ #

    def is_typing(self) -> bool:
        return self._typing_thread is not None and self._typing_thread.is_alive()

    def is_paused(self) -> bool:
        return bool(self.pause_flag[0])

    def mark_own_emit(self, key_id: str | None = None) -> None:
        """Records an imminent synthetic press. Engine passes a normalized id
        ('key:backspace', 'key:enter', or the lowercase char); None matches
        any key within the window (backward compatible)."""
        self._own_emits.append((time.time(), key_id))

    def save_session(self, text: str, profile: dict) -> None:
        """Call when a fresh typing run begins."""
        self.last_text = text
        self.last_profile = dict(profile)
        self.last_index = 0
        self.last_total = len(text)

    def update_index(self, current: int, total: int) -> None:
        self.last_index = max(0, int(current))
        self.last_total = max(0, int(total))

    def has_resume(self) -> bool:
        return (
            self.last_text is not None
            and 0 < self.last_index < self.last_total
            and not self.is_typing()
        )

    def get_resume_info(self) -> dict:
        text = self.last_text or ""
        idx = max(0, min(self.last_index, len(text)))
        remaining = text[idx:idx + 80].replace("\n", " ")
        return {
            "index": self.last_index,
            "total": self.last_total,
            "remaining_preview": remaining,
            "profile_name": (self.last_profile or {}).get("name", "Custom"),
        }

    def get_remaining_text(self) -> str:
        if self.last_text is None:
            return ""
        return self.last_text[self.last_index:]

    def clear_session(self) -> None:
        self.last_text = None
        self.last_profile = None
        self.last_index = 0
        self.last_total = 0

    def start_session(self, fn: Callable, *args, **kwargs) -> None:
        """Runs fn in a background daemon thread (fresh start)."""
        if self.is_typing():
            print("[!] Already typing. Press Esc to stop first.")
            return

        self.stop_flag[0] = False
        self.pause_flag[0] = False
        self._typing_thread = threading.Thread(
            target=fn, args=args, kwargs=kwargs, daemon=True
        )
        self._typing_thread.start()

    def resume_session(self, fn: Callable, *args, **kwargs) -> bool:
        """Resume soft-stopped session from last_index. Returns False if nothing to resume."""
        if not self.has_resume():
            return False
        if self.is_typing():
            print("[!] Already typing.")
            return False
        self.stop_flag[0] = False
        self.pause_flag[0] = False
        kwargs.setdefault("start_index", self.last_index)
        self._typing_thread = threading.Thread(
            target=fn, args=args, kwargs=kwargs, daemon=True
        )
        self._typing_thread.start()
        return True

    def stop_session(self, soft: bool = True) -> dict:
        """Soft-stop (default): keep index for Resume. Hard-stop clears it."""
        self.stop_flag[0] = True
        self.pause_flag[0] = False
        if not soft:
            self.clear_session()
        return self.get_resume_info()

    def toggle_pause(self) -> None:
        self.pause_flag[0] = not self.pause_flag[0]
        state = "PAUSED" if self.pause_flag[0] else "RESUMED"
        print(f"\n  [{state}]  (Ctrl+Alt+P to toggle)\n")

    def wait_if_paused(self) -> None:
        """Called by engine each character — blocks while paused."""
        while self.pause_flag[0] and not self.stop_flag[0]:
            time.sleep(0.05)

    # ------------------------------------------------------------------ #
    #  INTERFERENCE GUARD — pause if the human physically types mid-run   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ignored_keys() -> frozenset:
        """Modifier / control keys that never count as interference."""
        try:
            from pynput.keyboard import Key
            return frozenset({Key.ctrl, Key.ctrl_l, Key.ctrl_r, Key.alt, Key.alt_l,
                              Key.alt_r, Key.shift, Key.shift_l, Key.shift_r, Key.esc})
        except Exception:
            return frozenset()

    @staticmethod
    def _key_id(key) -> str:
        """Normalizes a pynput key to the id scheme engine marks use."""
        try:
            ch = getattr(key, 'char', None)
            if ch:
                return ch.lower()
        except Exception:
            pass
        try:
            return f"key:{key.name}"
        except Exception:
            return str(key)

    def _is_own_press(self, key) -> bool:
        """True if this press matches a recent synthetic emit (time + identity)."""
        now = time.time()
        while self._own_emits and now - self._own_emits[0][0] > self._own_emit_window:
            self._own_emits.popleft()
        kid = self._key_id(key)
        for _, eid in self._own_emits:
            if eid is None or eid == kid:
                return True
        return False

    def _handle_key_press(self, key) -> bool:
        """Core interference decision. Returns True if it paused (user typed)."""
        if not self.is_typing() or self.pause_flag[0] or self.stop_flag[0]:
            return False
        try:
            if key in self._ignored_keys():
                return False
        except Exception:
            pass
        if self._is_own_press(key):
            return False
        self.pause_flag[0] = True
        print("\n  [PAUSED] You typed — auto-paused. Ctrl+Alt+P to resume.\n")
        if self.on_interference is not None:
            try:
                self.on_interference()
            except Exception:
                pass
        return True

    def start_interference_watch(self) -> None:
        """Auto-pause when a physical keypress (not our own) is detected."""
        if self._interference_listener is not None:
            return

        def _on_press(key):
            try:
                self._handle_key_press(key)
            except Exception:
                pass

        try:
            listener = kb.Listener(on_press=_on_press, daemon=True)
            listener.start()
            self._interference_listener = listener
        except Exception:
            self._interference_listener = None

    def stop_interference_watch(self) -> None:
        try:
            if self._interference_listener is not None:
                self._interference_listener.stop()
        except Exception:
            pass
        finally:
            self._interference_listener = None

    # ------------------------------------------------------------------ #
    #  HOTKEYS — using GlobalHotKeys (reliable on Windows)               #
    # ------------------------------------------------------------------ #

    def start_listening(self) -> None:
        """
        Registers global hotkeys via pynput.GlobalHotKeys.
        Runs in a background daemon thread.

        Hotkeys:
          Ctrl + Alt + s  →  Start / Resume
          Ctrl + Alt + p  →  Pause / Resume
          Esc             →  Soft-stop (keeps place for Resume)
        """
        def _start():
            if self.on_start:
                # Run on_start in its own thread so the hotkey listener
                # doesn't block waiting for the countdown + typing
                threading.Thread(target=self.on_start, daemon=True).start()

        def _pause():
            self.toggle_pause()
            if self.on_pause_toggle:
                self.on_pause_toggle()

        def _stop():
            info = self.stop_session(soft=True)
            if self.on_stop:
                try:
                    self.on_stop(info)
                except TypeError:
                    self.on_stop()

        hotkeys = {
            '<ctrl>+<alt>+s': _start,
            '<ctrl>+<alt>+p': _pause,
            '<esc>': _stop,
        }

        self._hotkey_listener = kb.GlobalHotKeys(hotkeys)
        # daemon=True so it dies when main thread exits
        self._hotkey_listener.daemon = True  # type: ignore[attr-defined]
        self._hotkey_listener.start()
        print("  Hotkey listener active.\n")

    def stop_listening(self) -> None:
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self.stop_interference_watch()
