"""Regression tests: interference guard must ignore OUR presses
(including backspace corrections) and catch the USER's presses."""
import time

from pynput.keyboard import Key, KeyCode

from core.controller import SessionController
from core.engine import TypingEngine
from core.profiles import get_profile
from tests.conftest import patch_engine


class _AliveThread:
    def is_alive(self):
        return True


def _typing_controller():
    c = SessionController()
    c._typing_thread = _AliveThread()
    return c


def test_own_char_press_is_ignored():
    c = _typing_controller()
    c.mark_own_emit('q')
    assert c._handle_key_press(KeyCode(char='q')) is False
    assert c.pause_flag[0] is False


def test_own_press_matches_case_insensitively():
    c = _typing_controller()
    c.mark_own_emit('a')
    assert c._handle_key_press(KeyCode(char='A')) is False


def test_foreign_key_within_window_is_interference():
    c = _typing_controller()
    c.mark_own_emit('q')
    assert c._handle_key_press(KeyCode(char='z')) is True
    assert c.pause_flag[0] is True


def test_stale_mark_does_not_cover():
    c = _typing_controller()
    c._own_emits.append((time.time() - 10, 'q'))
    assert c._handle_key_press(KeyCode(char='q')) is True


def test_legacy_wildcard_mark_covers_any_key():
    c = _typing_controller()
    c.mark_own_emit()
    assert c._handle_key_press(KeyCode(char='z')) is False


def test_marked_backspace_is_ignored_unmarked_is_not():
    c = _typing_controller()
    c.mark_own_emit('key:backspace')
    assert c._handle_key_press(Key.backspace) is False
    c2 = _typing_controller()
    assert c2._handle_key_press(Key.backspace) is True


def test_space_heard_as_key_space_matches_mark():
    # Listener reports our typed space as Key.space, not KeyCode(' ').
    c = _typing_controller()
    c.mark_own_emit(' ')
    assert c._handle_key_press(Key.space) is False
    assert c.pause_flag[0] is False
    c2 = _typing_controller()
    assert c2._handle_key_press(Key.space) is True
    assert c2.pause_flag[0] is True


def test_no_pause_when_not_typing_or_paused():
    c = SessionController()  # no thread -> not typing
    assert c._handle_key_press(KeyCode(char='z')) is False
    c2 = _typing_controller()
    c2.pause_flag[0] = True
    assert c2._handle_key_press(KeyCode(char='z')) is False


def test_modifiers_never_count():
    c = _typing_controller()
    assert c._handle_key_press(Key.shift) is False
    assert c.pause_flag[0] is False


def test_unidentifiable_key_fails_open_with_recent_mark():
    c = _typing_controller()
    c.mark_own_emit('e')
    assert c._handle_key_press(object()) is False
    assert c.pause_flag[0] is False


def test_unidentifiable_key_with_no_marks_is_interference():
    c = _typing_controller()
    assert c._handle_key_press(object()) is True
    assert c.pause_flag[0] is True


def test_ctrl_or_alt_held_press_is_never_interference():
    # Hotkeys (Ctrl+Alt+P/S) and shortcuts (Ctrl+L, Ctrl+S) are not typing.
    for mod in ('ctrl', 'alt'):
        c = _typing_controller()
        c._held_mods.add(mod)
        assert c._handle_key_press(KeyCode(char='z')) is False
        assert c.pause_flag[0] is False


def test_shift_held_typing_still_counts():
    # Capitals (shift+letter) ARE typing — shift is deliberately not tracked.
    c = _typing_controller()
    assert c._handle_key_press(KeyCode(char='A')) is True


def test_mod_name_mapping():
    assert SessionController._mod_name(Key.ctrl_l) == 'ctrl'
    assert SessionController._mod_name(Key.ctrl_r) == 'ctrl'
    assert SessionController._mod_name(Key.alt) == 'alt'
    assert SessionController._mod_name(Key.shift) is None
    assert SessionController._mod_name(KeyCode(char='a')) is None


def test_display_key_names_control_chars():
    assert SessionController._display_key('\x0c') == 'Ctrl+L'
    assert SessionController._display_key('\x13') == 'Ctrl+S'
    assert SessionController._display_key('a') == 'a'
    assert SessionController._display_key(None) is None


def test_surrogate_half_maps_to_shared_id():
    # Emoji heard as lone-surrogate halves must match the engine's mark.
    assert SessionController._key_id(KeyCode(char='\ud83d')) == 'surrogate-half'
    assert SessionController._key_id(KeyCode(char='\ude0b')) == 'surrogate-half'
    assert SessionController._key_id(KeyCode(char='a')) == 'a'


def test_marked_surrogate_half_is_ignored():
    c = _typing_controller()
    c.mark_own_emit('surrogate-half')
    assert c._handle_key_press(KeyCode(char='\ud83d')) is False
    assert c.pause_flag[0] is False


def test_engine_marks_astral_as_surrogate_half(monkeypatch):
    from core.engine import TypingEngine
    from core.profiles import get_profile
    from tests.conftest import patch_engine
    dummy = patch_engine(monkeypatch)
    marks = []
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=marks.append)
    eng._press_char('😋')
    assert marks == ['surrogate-half']
    assert dummy.typed == ['😋']
    assert SessionController._display_key('key:backspace') == 'key:backspace'


def test_stop_watch_clears_held_mods():
    c = _typing_controller()
    c._held_mods.add('ctrl')
    c.stop_interference_watch()
    assert c._held_mods == set()


def test_correction_marks_backspace(monkeypatch):
    patch_engine(monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    marks = []
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=marks.append)
    eng._type_with_correction('e')
    assert 'key:backspace' in marks
    assert 'e' in marks


def test_transposition_marks_backspaces(monkeypatch):
    patch_engine(monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    marks = []
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=marks.append)
    eng._type_transposition('the', 'teh')
    assert marks.count('key:backspace') == 3


def test_press_char_marks_identities(monkeypatch):
    dummy = patch_engine(monkeypatch)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    marks = []
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=marks.append)
    eng._press_char('A')
    eng._press_char('\n')
    eng._press_char('\t')
    eng._press_char('\r')
    assert marks[0] == 'a'
    assert marks[1] == 'key:enter'
    assert marks[2] == ' '
    assert len(marks) == 3  # \r emits nothing -> marks nothing
    assert dummy is not None
