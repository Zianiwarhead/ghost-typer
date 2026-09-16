"""Word tracking, word-snapped resume, and insane-speed preset."""
import time

from core.controller import SessionController
from core.engine import TypingEngine, count_words, snap_to_word_start
from core.profiles import get_profile
from main import make_progress_bar, run_countdown
from tests.conftest import patch_engine


def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_snap_mid_word_to_start():
    assert snap_to_word_start("hello world", 8) == 6


def test_snap_leaves_boundaries_alone():
    assert snap_to_word_start("hello world", 0) == 0
    assert snap_to_word_start("hello world", 5) == 5  # the space
    assert snap_to_word_start("hello world", 6) == 6  # word start
    assert snap_to_word_start("hello world", 11) == 11
    assert snap_to_word_start("hello world", 99) == 11
    assert snap_to_word_start("", 5) == 0


def test_count_words():
    assert count_words("hello world") == 2
    assert count_words("  one   two\nthree  ") == 3
    assert count_words("") == 0


def test_engine_word_progress(monkeypatch):
    patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False])
    assert eng.type_text("hello world") is True
    assert eng.get_word_progress() == (2, 2)


def test_resume_snaps_to_word_start(monkeypatch):
    patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    profile = get_profile("flawless")
    seen = []
    eng = TypingEngine(profile, [False])
    # "hello brave world": index 8 is inside "brave" (starts at 6).
    assert eng.type_text("hello brave world", progress_callback=lambda c, t: seen.append(c),
                         start_index=8) is True
    assert seen[0] == 7  # first completed step after snapped start 6
    assert eng.get_word_progress() == (3, 3)


def test_soft_stop_then_word_snapped_resume(monkeypatch):
    patch_engine(monkeypatch)
    import time as _time
    real_sleep = _time.sleep
    monkeypatch.setattr(_time, "sleep", lambda s: real_sleep(0))
    profile = get_profile("flawless")
    stop = [False]
    eng = TypingEngine(profile, stop)

    def progress(cur, tot):
        if cur >= 8:
            stop[0] = True

    assert eng.type_text("hello brave world", progress_callback=progress) is False
    assert eng.current_index == 8
    # Resume: engine snaps 8 -> 6 and retypes "brave" cleanly.
    eng2 = TypingEngine(profile, [False])
    assert eng2.type_text("hello brave world", start_index=eng.current_index) is True
    assert eng2.get_word_progress() == (3, 3)


def test_insane_preset_is_max_speed_no_humanization():
    p = get_profile("insane")
    assert p["wpm"] == 300
    assert p["errors_enabled"] is False
    assert p["thinking_chance"] == 0.0
    assert p["burst_chance"] == 0.0
    assert p["fatigue_enabled"] is False


def test_controller_resume_info_carries_words():
    c = SessionController()
    c.save_session("hello world", {"name": "x"})
    c.update_index(8, 11, 1, 2)
    info = c.get_resume_info()
    assert info["word_index"] == 1 and info["word_total"] == 2
    c.clear_session()
    assert c.get_resume_info()["word_total"] == 0


def test_progress_bar_shows_words():
    bar = make_progress_bar(8, 11, words=(1, 2))
    assert "word 1/2" in bar
    assert "word" not in make_progress_bar(8, 11)


def test_run_countdown_custom_prompt(capsys):
    run_countdown(0, "Click the FIRST CELL now!")
    assert "Click the FIRST CELL now!" in capsys.readouterr().out
