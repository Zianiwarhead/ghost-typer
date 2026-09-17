"""Web UI Api: lifecycle, soft-stop/resume, inputs, doctor.

Engine keystrokes are mocked (conftest.patch_engine); sleeps are stubbed
except where a test deliberately needs the run to stay alive.
"""
import sys
import time
import types

import pytest

from tests.conftest import patch_engine
from webapp import Api


def _noop_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)


def _wait_done(api, timeout=15.0):
    # Join the worker when visible (deterministic); poll only until it appears.
    deadline = time.time() + timeout
    while api.get_status()["typing"] and time.time() < deadline:
        worker = api.controller._typing_thread
        if worker is not None:
            worker.join(max(0.0, deadline - time.time()))
        else:
            time.sleep(0.02)
    return api.get_status()


def test_initial_status_shape():
    s = Api().get_status()
    assert s == {"typing": False, "paused": False, "index": 0, "total": 0,
                 "has_resume": False, "message": s["message"]}


def test_full_run_to_done(monkeypatch):
    patch_engine(monkeypatch)
    _noop_sleep(monkeypatch)
    api = Api()
    assert api.start({"text": "hi there", "profile": "normal", "wpm": 300,
                      "focus_lock": False, "countdown": 2}) is True
    s = _wait_done(api)
    assert s["typing"] is False
    assert s["message"] == "Done."
    assert s["has_resume"] is False


def test_start_while_running_rejected(monkeypatch):
    patch_engine(monkeypatch)
    api = Api()
    assert api.start({"text": "hello world, this keeps going", "profile": "sluggish",
                      "countdown": 5}) is True
    assert api.start({"text": "other"}) is False
    api.stop()
    _wait_done(api)


def test_stop_during_countdown_cancels(monkeypatch):
    patch_engine(monkeypatch)
    api = Api()
    assert api.start({"text": "hello", "profile": "normal", "countdown": 5}) is True
    time.sleep(0.2)  # let the thread enter its countdown
    api.stop()
    s = _wait_done(api)
    assert s["typing"] is False
    assert "Cancelled" in s["message"]
    assert s["has_resume"] is False


def test_soft_stop_then_resume(monkeypatch):
    patch_engine(monkeypatch)
    api = Api()
    profile = {"wpm": 65, "error_rate": 0.0, "transposition_rate": 0.0,
               "thinking_chance": 0.0, "burst_chance": 0.0,
               "fatigue_enabled": False, "errors_enabled": False,
               "mechanical": False, "chat_mode": False, "name": "t"}

    calls = []

    def murder_sleep(s):
        calls.append(s)
        if len(calls) > 12:
            api.controller.stop_flag[0] = True

    monkeypatch.setattr(time, "sleep", murder_sleep)
    api._run_inner("hello world, this is a typing test string", profile,
                   False, 0, False)
    # _run_inner ran on this thread; simulate the worker thread having exited.
    api.controller._typing_thread = None
    assert api.controller.has_resume() is True
    assert "Resume" in api.get_status()["message"]

    _noop_sleep(monkeypatch)
    api._run_inner("hello world, this is a typing test string", profile,
                   False, 0, True)
    assert api.get_status()["message"] == "Done."
    assert api.controller.has_resume() is False


def test_pause_toggle():
    api = Api()
    assert api.pause() is True
    assert api.pause() is False


def test_bad_profile_raises_before_running():
    api = Api()
    with pytest.raises(ValueError):
        api.start({"text": "hi", "profile": "nope"})
    assert api.get_status()["typing"] is False


def test_wpm_clamped(monkeypatch):
    patch_engine(monkeypatch)
    _noop_sleep(monkeypatch)
    api = Api()
    assert api.start({"text": "hi", "profile": "normal", "wpm": 99999,
                      "focus_lock": False, "countdown": 2}) is True
    _wait_done(api)
    assert api.get_status()["message"] == "Done."


def test_paste_clipboard_stubbed(monkeypatch):
    stub = types.ModuleType("pyperclip")
    stub.paste = lambda: "clip text"
    monkeypatch.setitem(sys.modules, "pyperclip", stub)
    assert Api().paste_clipboard() == "clip text"


def test_paste_clipboard_failure_returns_empty(monkeypatch):
    stub = types.ModuleType("pyperclip")

    def boom():
        raise RuntimeError("no clipboard")

    stub.paste = boom
    monkeypatch.setitem(sys.modules, "pyperclip", stub)
    assert Api().paste_clipboard() == ""


def test_run_doctor_returns_report():
    report = Api().run_doctor()
    assert isinstance(report, str) and len(report.strip()) > 0
