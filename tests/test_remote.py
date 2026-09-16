"""Remote server, table themes, inline tables, bg-typos plumbing.

Server tests run a real threaded HTTPServer on 127.0.0.1 with an ephemeral
port — no mocks needed, no external traffic.
"""
import json
import urllib.error
import urllib.request

import pytest

from core import netserver
from core.table_themes import THEMES, format_cell, render_themed_table
from core.tables import parse_inline_table


@pytest.fixture()
def live_server():
    calls = []

    def dispatch(payload):
        calls.append(payload)
        if payload.get("text") == "BUSY":
            return 409, "busy"
        return 200, "ok"

    server, _thread = netserver.start_in_thread(
        "127.0.0.1", 0, "test-token-123", dispatch, lambda: False)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, calls
    server.shutdown()
    server.server_close()


def _post(base, body, token="test-token-123"):
    req = urllib.request.Request(
        base + "/api/v1/type", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(base, path, token="test-token-123"):
    req = urllib.request.Request(base + path,
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_dashboard_serves_without_auth(live_server):
    base, _ = live_server
    req = urllib.request.Request(base + "/")
    with urllib.request.urlopen(req) as r:
        assert r.status == 200
        assert b"GhostTyper Remote" in r.read()


def test_post_requires_token(live_server):
    base, calls = live_server
    code, _ = _post(base, {"text": "hi", "target": "x"}, token="wrong")
    assert code == 401
    code, _ = _post(base, {"text": "hi", "target": "x"}, token="")
    assert code == 401
    assert calls == []


def test_post_dispatch_and_status(live_server):
    base, calls = live_server
    code, body = _post(base, {"text": "hi", "target": "Note", "mode": "human"})
    assert code == 200 and body["status"] == "dispatched"
    assert calls[0]["text"] == "hi"
    code, raw = _get(base, "/api/v1/status")
    assert code == 200 and json.loads(raw)["typing"] is False


def test_post_busy_and_bad_payloads(live_server):
    base, _ = live_server
    code, _ = _post(base, {"text": "BUSY", "target": "x"})
    assert code == 409
    code, _ = _post(base, {"text": "", "target": "x"})
    assert code == 400
    code, _ = _post(base, {"text": "x"})
    assert code == 400
    code, _ = _post(base, {"nope": 1})
    assert code == 400


def test_post_malformed_json(live_server):
    base, _ = live_server
    req = urllib.request.Request(
        base + "/api/v1/type", data=b"{oops",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer test-token-123"})
    try:
        urllib.request.urlopen(req)
        raise AssertionError("should have failed")
    except urllib.error.HTTPError as e:
        assert e.code == 400


def test_unknown_endpoints(live_server):
    base, _ = live_server
    code, _ = _get(base, "/nope")
    assert code == 404


# ---------------- table themes ---------------- #

def test_all_themes_render_and_escape():
    for name in ("matrix", "dracula", "steel"):
        out = render_themed_table("T <x>", ["a", "b"], [["1", "2"]], name)
        assert "&lt;x&gt;" in out
        assert THEMES[name]["accent"] in out
    assert render_themed_table("", ["a"], [["1"]], "nope").startswith("<div")


def test_format_cell_tags():
    assert format_cell("**b**") == "<b>b</b>"
    assert format_cell("__u__") == "<u>u</u>"
    assert format_cell("*i*") == "<i>i</i>"
    assert format_cell("[COLOR=#f00]x[/COLOR]") == '<span style="color:#f00;">x</span>'
    assert format_cell("a_b") == "a_b"  # no mid-word false positive
    assert format_cell("") == "&nbsp;"
    assert "&amp;" in format_cell("a&b")


# ---------------- inline tables ---------------- #

def test_parse_inline_table():
    title, headers, rows = parse_inline_table("Ops | a,b | 1,2 | 3,4")
    assert (title, headers, rows) == ("Ops", ["a", "b"], [["1", "2"], ["3", "4"]])


def test_parse_inline_table_escapes():
    title, headers, rows = parse_inline_table(r"A \| B | x\,y,z | 1\,2,3")
    assert title == "A | B"
    assert headers == ["x,y", "z"]
    assert rows == [["1,2", "3"]]


def test_parse_inline_table_rejects():
    with pytest.raises(ValueError):
        parse_inline_table("just a title")
    with pytest.raises(ValueError):
        parse_inline_table("T | | 1,2")
    with pytest.raises(ValueError):
        parse_inline_table("T | a,b | , ")


# ---------------- bg-typos plumbing ---------------- #

def test_bg_msg_keyboard_mapping(monkeypatch):
    from pynput.keyboard import Key

    import main as main_mod
    sent = []
    monkeypatch.setattr("core.background.send_char",
                        lambda hwnd, ch: sent.append((hwnd, ch)))
    kb = main_mod._BgMsgKeyboard(1234)
    kb.type("ab")
    kb.press(Key.backspace)
    kb.press(Key.enter)
    kb.press(Key.shift)  # modifiers are no-ops
    kb.release(Key.backspace)
    with kb.pressed(Key.ctrl):
        pass
    assert sent == [(1234, "a"), (1234, "b"), (1234, "\b"), (1234, "\r")]


def test_alive_check_paths(fake_win32_alive, monkeypatch):
    from core import background as bg
    monkeypatch.setattr(bg, "_send_timeout_ok", lambda h: True)
    assert bg.verify_window_alive(100) is True
    assert bg.verify_window_alive(999) is False

    def _boom(h):
        raise OSError("no ctypes here")

    monkeypatch.setattr(bg, "_send_timeout_ok", _boom)
    assert bg.verify_window_alive(100) is True  # fail-open by design


@pytest.fixture()
def fake_win32_alive(monkeypatch):
    import sys
    import types
    gui = types.ModuleType("win32gui")
    con = types.ModuleType("win32con")
    gui.IsWindow = lambda h: h == 100
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(sys.modules, "win32con", con)
    # verify_window_alive calls ctypes SendMessageTimeoutW on Windows only;
    # on other platforms ctypes.windll is absent -> fail-open True.
    return gui
