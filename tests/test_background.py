"""Background delivery: payload builders + stubbed-window targeting.

win32gui/win32con are stubbed via sys.modules so these run on any OS
(including headless Linux CI). Real clipboard/window calls are only
exercised in the live Notepad check, never here.
"""
import re
import sys
import types

import pytest

from core import background as bg


@pytest.fixture()
def fake_win32(monkeypatch):
    gui = types.ModuleType("win32gui")
    con = types.ModuleType("win32con")
    proc = types.ModuleType("win32process")
    con.WM_PASTE = 0x0302
    con.WM_CHAR = 0x0102
    con.WM_KEYDOWN = 0x0100
    con.WM_KEYUP = 0x0101

    state = {
        # hwnd: (title, visible, class, children, pid)
        100: ("Untitled - Notepad", True, "Notepad", [101], 1111),
        101: ("", True, "Edit", [], 1111),
        200: ("Some Game", True, "GameWnd", [], 2222),
        300: ("My Notepad notes", True, "Notepad", [], 3333),
        400: ("cmd with bg1 command", True, "ConsoleWindowClass", [], 4444),
        500: ("bg1 data", True, "Notepad", [], 5555),
    }
    gui.posted = []
    proc.GetWindowThreadProcessId = lambda h: (0, state[h][4])

    def EnumWindows(cb, extra):
        for hwnd in (100, 200, 300, 400, 500):
            if cb(hwnd, extra) is False:
                break

    def EnumChildWindows(hwnd, cb, extra):
        for child in state[hwnd][3]:
            cb(child, extra)

    gui.EnumWindows = EnumWindows
    gui.EnumChildWindows = EnumChildWindows
    gui.GetWindowText = lambda h: state[h][0]
    gui.IsWindowVisible = lambda h: state[h][1]
    gui.GetClassName = lambda h: state[h][2]
    gui.PostMessage = lambda h, m, w, l: gui.posted.append((h, m, w, l))
    monkeypatch.setitem(sys.modules, "win32gui", gui)
    monkeypatch.setitem(sys.modules, "win32con", con)
    monkeypatch.setitem(sys.modules, "win32process", proc)
    return gui


# ---------------- HTML payload (byte-exact) ---------------- #

def test_html_payload_offsets_are_byte_based():
    payload = bg.build_html_clipboard_payload("<b>héllo 世界</b>")
    head = payload[:105].decode("utf-8")
    m = dict(re.findall(r"(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)", head))
    s, e, f0, f1 = (int(m[k]) for k in ("StartHTML", "EndHTML", "StartFragment", "EndFragment"))
    assert payload[s:].startswith(b"<html>")
    assert e == len(payload)
    frag = payload[f0:f1]
    assert b"<!--" not in frag
    assert frag.decode("utf-8") == "<b>héllo 世界</b>"


def test_html_payload_ascii():
    payload = bg.build_html_clipboard_payload("<p>hi</p>")
    assert payload[105:].startswith(b"<html>")
    assert len(payload) == int(re.search(rb"EndHTML:(\d+)", payload[:105]).group(1))


# ---------------- converters ---------------- #

def test_markup_to_html_basic():
    out = bg.markup_to_html("# Title\nHello **bold** and *it*.")
    assert out == "<h1>Title</h1><p>Hello <b>bold</b> and <i>it</i>.</p>"


def test_markup_to_html_escapes():
    out = bg.markup_to_html("a < b & **c**")
    assert out == "<p>a &lt; b &amp; <b>c</b></p>"


def test_markup_to_html_underline_and_h2():
    out = bg.markup_to_html("## Sub\n__under__ ok")
    assert out == "<h2>Sub</h2><p><u>under</u> ok</p>"


def test_markup_to_html_plain_paragraphs():
    assert bg.markup_to_html("one\n\ntwo") == "<p>one</p><p>two</p>"


def test_rows_to_html_table():
    out = bg.rows_to_html_table([["a", "b"], ["1", "x&y"]])
    assert "<th" in out and ">a</th>" in out
    assert "<td>1</td>" in out and "x&amp;y" in out
    assert out.count("<tr>") == 2


# ---------------- window targeting (stubbed) ---------------- #

def test_find_window_matches_case_insensitively(fake_win32):
    assert bg.find_window("notepad") == 100
    assert bg.find_window("GAME") == 200
    assert bg.find_window("nope") is None


def test_find_edit_child_prefers_edit_control(fake_win32):
    assert bg.find_edit_child(100) == 101
    assert bg.find_edit_child(200) == 200  # no edit child -> top level


def test_resolve_target(fake_win32):
    top, edit, title = bg.resolve_target(keyword="Untitled - Notepad")
    assert (top, edit, title) == (100, 101, "Untitled - Notepad")
    with pytest.raises(ValueError):
        bg.resolve_target(keyword="missing")


def test_resolve_exact_beats_partial(fake_win32):
    top, _, _ = bg.resolve_target(keyword="my notepad notes")
    assert top == 300


def test_resolve_ambiguous_refuses(fake_win32):
    with pytest.raises(ValueError, match="be more specific"):
        bg.resolve_target(keyword="notepad")


def test_resolve_prefers_real_window_over_console(fake_win32):
    # 400 is a console echoing the command line; 500 is the real target.
    top, edit, title = bg.resolve_target(keyword="bg1")
    assert top == 500
    assert title == "bg1 data"
    assert edit == 500  # no edit child -> falls back to top


def test_resolve_uses_lone_console(fake_win32):
    top, _, _title = bg.resolve_target(keyword="cmd with")
    assert top == 400


def test_resolve_by_pid(fake_win32):
    top, edit, title = bg.resolve_target(pid=1111)
    assert (top, edit, title) == (100, 101, "Untitled - Notepad")
    with pytest.raises(ValueError):
        bg.resolve_target(pid=9999)


def test_paste_posts_wm_paste(fake_win32):
    bg.paste_to_hwnd(101)
    assert fake_win32.posted == [(101, 0x0302, 0, 0)]


def test_send_char_and_key(fake_win32):
    bg.send_char(101, "A")
    bg.send_char(101, "\n")  # newline -> CR
    bg.send_key(101, 0x09)
    assert fake_win32.posted == [
        (101, 0x0102, ord("A"), 0),
        (101, 0x0102, ord("\r"), 0),
        (101, 0x0100, 0x09, 0),
        (101, 0x0101, 0x09, 0),
    ]


def test_send_char_astral_becomes_question(fake_win32):
    bg.send_char(101, "😀")
    assert fake_win32.posted == [(101, 0x0102, ord("?"), 0)]


def test_is_web_target():
    assert bg.is_web_target('Google Chrome') is True
    assert bg.is_web_target('Discord') is True
    assert bg.is_web_target('doc - Word', 'Word') is False
    assert bg.is_web_target('', None) is False
    assert bg.is_web_target('Untitled - Notepad') is False


def test_web_guidance_mentions_focused():
    msg = bg.web_target_guidance('Discord')
    assert 'Discord' in msg and '--bg' in msg

