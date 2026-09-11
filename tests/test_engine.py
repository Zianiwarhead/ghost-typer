from core.engine import TypingEngine
from core.profiles import get_profile
from tests.conftest import patch_engine


def _fast_no_sleep(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_full_run_reports_progress(monkeypatch):
    patch_engine(monkeypatch)
    _fast_no_sleep(monkeypatch)
    profile = get_profile("flawless")
    engine = TypingEngine(profile, [False])
    seen = []
    ok = engine.type_text("hi!", progress_callback=lambda c, t: seen.append((c, t)))
    assert ok is True
    assert engine.get_progress() == (3, 3)
    assert seen[-1] == (3, 3)
    assert engine.get_remaining_text("hi!") == ""


def test_resume_from_index(monkeypatch):
    patch_engine(monkeypatch)
    _fast_no_sleep(monkeypatch)
    profile = get_profile("flawless")
    engine = TypingEngine(profile, [False])
    ok = engine.type_text("abcdef", progress_callback=None, start_index=4)
    assert ok is True
    assert engine.current_index == 6


def test_soft_stop_keeps_index(monkeypatch):
    patch_engine(monkeypatch)
    import time as _time
    real_sleep = _time.sleep
    monkeypatch.setattr(_time, "sleep", lambda s: real_sleep(0))
    profile = get_profile("flawless")
    stop = [False]
    engine = TypingEngine(profile, stop)

    def progress(cur, tot):
        if cur >= 5:
            stop[0] = True

    ok = engine.type_text("x" * 200, progress_callback=progress)
    assert ok is False
    cur, tot = engine.get_progress()
    assert cur >= 5 and tot == 200
    assert engine.get_remaining_text("x" * 200) == "x" * (200 - cur)


def test_mechanical_delay_runs(monkeypatch):
    patch_engine(monkeypatch)
    _fast_no_sleep(monkeypatch)
    profile = get_profile("typewriter")
    engine = TypingEngine(profile, [False])
    assert engine.type_text("Hello.\nWorld", progress_callback=None) is True
