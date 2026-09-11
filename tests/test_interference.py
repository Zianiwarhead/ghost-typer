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
