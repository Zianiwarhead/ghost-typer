"""v2.8.0: lists, formatted clipboard, mouse math, UIA dicts, brain backends."""
import io
import json
import sys
import time
import urllib.error

import pytest

from core import mouse as _mouse
from core import uia as _uia
from core.background import build_html_clipboard_payload, markup_to_html
from core.brain import _api_ask, ask, build_context, capture_screen, local_ready
from core.clipfmt import extract_html_fragment
from core.engine import TypingEngine
from core.profiles import get_profile
from core.richtext import has_markup, parse_rich_text, strip_rich
from tests.conftest import patch_engine


def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)


# ---------------- list markup ---------------- #

def test_list_tokens_open_switch_close():
    toks = parse_rich_text("- a\n- b\n1. x\n2. y\n")
    kinds = [(t[0], t[1] if len(t) == 2 else (t[1], t[2])) for t in toks]
    assert ('list', 'ul') in kinds
    assert ('list', 'ol') in kinds
    assert kinds.count(('list', None)) == 2
    assert strip_rich("- a\n- b\n1. x\n") == "a\nb\nx\n"


def test_list_edges():
    assert strip_rich("- \n") == "\n"  # marker-only line
    assert strip_rich("1,2 and a - b") == "1,2 and a - b"  # not lists
    assert strip_rich("# H\n- i\nplain\n") == "H\ni\nplain\n"  # heading closes list
    assert has_markup("- a")
    assert not has_markup("a - b")


def test_html_lists_with_inline_fmt():
    out = markup_to_html("- **a** and b\n- c\n1. x\n")
    assert out == "<ul><li><b>a</b> and b</li><li>c</li></ul><ol><li>x</li></ol>"


def test_engine_types_list_markers_and_exits(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    assert eng.type_rich("- a\n- b\n") is True
    # Marker typed once; follow-on bullets come from the app's autocorrect
    # (Word/Docs), so subsequent items need no literal "- " retyped.
    assert ''.join(dummy.typed) == "- ab"
    enters = [k for k in dummy.pressed_keys if k == ("press", "Key.enter")]
    assert len(enters) == 3  # two newlines + one list-exit Enter


def test_engine_resume_inside_list(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    assert eng.type_rich("- hello brave world", start_index=8) is True
    assert ''.join(dummy.typed) == "brave world"  # marker NOT retyped mid-line
    assert ("press", "Key.enter") in dummy.pressed_keys  # close still exits


# ---------------- clipfmt ---------------- #

def test_extract_round_trip():
    frag = "<b>bold</b> and <u>u</u>"
    assert extract_html_fragment(build_html_clipboard_payload(frag)) == frag


def test_extract_rejects_garbage():
    assert extract_html_fragment(b"garbage") is None
    assert extract_html_fragment(b"") is None
    assert extract_html_fragment(build_html_clipboard_payload("x")[:60]) is None
    # Cut mid-multibyte-char inside the fragment -> undecodable -> None.
    full = build_html_clipboard_payload("<b>" + "é" * 20 + "</b>")
    cut_at = full.index("é".encode()[:1]) + 1
    assert extract_html_fragment(full[:cut_at]) is None


# ---------------- mouse math ---------------- #

def test_plan_move_endpoints_and_determinism():
    a = _mouse.plan_move(0, 0, 100, 50, segments=4, seed=7)
    b = _mouse.plan_move(0, 0, 100, 50, segments=4, seed=7)
    assert a == b
    assert a[0] == (0, 0) and a[-1] == (100, 50)
    assert len(a) == 5  # start + (segments - 1) midpoints + end
    for x, y in a[1:-1]:
        assert -12 <= x <= 112 and -12 <= y <= 62


def test_move_and_click_use_fake_controller(monkeypatch):
    _no_sleep(monkeypatch)

    class Fake:
        def __init__(self):
            self.positions = []
            self.clicks = []
            self._pos = (0, 0)

        @property
        def position(self):
            return self._pos

        @position.setter
        def position(self, v):
            self._pos = v
            self.positions.append(v)

        def click(self, btn, n):
            self.clicks.append((str(btn), n))

    fake = Fake()
    _mouse.move_human(90, 40, duration=0.01, _ctl=fake)
    assert fake.positions[-1] == (90, 40)
    _mouse.click_human(90, 40, _ctl=fake)
    assert fake.clicks == [("Button.left", 1)]
    with pytest.raises(ValueError):
        _mouse.click_element({'name': 'x', 'rect': None}, _ctl=fake)
    assert _mouse.click_element(
        {'name': 'Save', 'rect': {'x': 10, 'y': 10, 'w': 20, 'h': 20}},
        _ctl=fake) == (20, 20)


# ---------------- uia dict helpers ---------------- #

def test_rect_center_and_find():
    assert _uia.rect_center({'x': 10, 'y': 10, 'w': 20, 'h': 20}) == (20, 20)
    tree = [{'name': 'root', 'control': 'Window', 'rect': None, 'value': None, 'children': [
        {'name': 'Cancel', 'control': 'Button', 'rect': None, 'value': None, 'children': []},
        {'name': 'Save File', 'control': 'Button', 'rect': None, 'value': None, 'children': []}]}]
    assert _uia.find_in_tree(tree, 'save')['name'] == 'Save File'
    assert _uia.find_in_tree(tree, 'nope') is None
    assert _uia.find_in_tree(tree, '') is None
    text = _uia.tree_to_text(tree)
    assert 'Save File' in text and 'Cancel' in text


# ---------------- brain backends ---------------- #

class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        return json.dumps(self._p).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_api_ask_builds_request(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen['url'] = req.full_url
        seen['auth'] = req.get_header('Authorization')
        seen['body'] = json.loads(req.data.decode())
        return _FakeResp({"choices": [{"message": {"content": "  hi  "}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    out = _api_ask("https://x.test/v1", "sek", "m", "Q?", "CTX", b"\xff\xd8raw",
                   timeout=5, max_tokens=10)
    assert out == "hi"
    assert seen['url'].endswith('/chat/completions')
    assert seen['auth'] == 'Bearer sek'
    content = seen['body']['messages'][1]['content']
    assert any(p.get('type') == 'image_url' for p in content)
    assert seen['body']['model'] == 'm'


def test_api_ask_errors(monkeypatch):
    with pytest.raises(RuntimeError, match='--brain-key'):
        _api_ask("https://x.test/v1", "", "m", "Q?", "", None, 5, 10)

    def fake_401(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "deny", {},
                                     io.BytesIO(b'{"error":"bad key"}'))

    monkeypatch.setattr("urllib.request.urlopen", fake_401)
    with pytest.raises(RuntimeError, match='401'):
        _api_ask("https://x.test/v1", "sek", "m", "Q?", "", None, 5, 10)

    def fake_empty(req, timeout=None):
        return _FakeResp({"choices": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_empty)
    with pytest.raises(RuntimeError, match='no usable answer'):
        _api_ask("https://x.test/v1", "sek", "m", "Q?", "", None, 5, 10)


def test_ask_dispatch_and_validation():
    with pytest.raises(ValueError, match='unknown brain backend'):
        ask("Q?", backend='nope')
    with pytest.raises(RuntimeError, match='--brain-key'):
        ask("Q?", backend='api', api_key='')


def test_local_backend_reports_setup(monkeypatch):
    monkeypatch.setitem(sys.modules, 'onnxruntime', None)
    ready, reason = local_ready()
    assert ready is False and reason


def test_context_and_shot_shapes():
    text, _shot, notes = build_context()
    assert isinstance(text, str) and isinstance(notes, list)
    data, note = capture_screen()
    assert (data is None) == bool(note)  # bytes XOR an explanation, never neither
