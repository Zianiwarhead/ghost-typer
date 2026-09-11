"""Rich-text markup and CSV table-fill."""
import time

import pytest

from core.engine import TypingEngine
from core.profiles import get_profile
from core.richtext import has_markup, parse_rich_text, strip_rich
from core.tables import count_cells, fill_table, load_csv, parse_cell
from tests.conftest import patch_engine


def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)


def _engine(monkeypatch, marks):
    patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    return TypingEngine(get_profile("flawless"), [False], emit_hook=marks.append)


# ---------------- richtext parser ---------------- #

def test_bold_italic_underline_tokens():
    toks = parse_rich_text("Hello **bold** and *it* plus __under__.")
    kinds = [(t[0], t[1] if len(t) == 2 else (t[1], t[2])) for t in toks]
    assert ('fmt', ('bold', True)) in kinds
    assert ('fmt', ('bold', False)) in kinds
    assert ('fmt', ('italic', True)) in kinds
    assert ('fmt', ('underline', True)) in kinds
    assert strip_rich("Hello **bold** and *it* plus __under__.") == "Hello bold and it plus under."


def test_heading_tokens_and_reset():
    toks = parse_rich_text("# Title\nbody\n")
    assert toks[0] == ('heading', 1)
    assert ('heading', None) in toks
    assert strip_rich("# Title\nbody\n") == "Title\nbody\n"
    assert parse_rich_text("## H2\n")[0] == ('heading', 2)
    assert parse_rich_text("### H3\n")[0] == ('heading', 3)


def test_unclosed_markers_stay_literal():
    assert strip_rich("a **oops and *meh") == "a **oops and *meh"
    assert not has_markup("plain text, # not a heading")
    assert has_markup("has **bold**")
    assert has_markup("# Head")


def test_double_star_beats_single():
    toks = parse_rich_text("**x**")
    assert toks == [('fmt', 'bold', True), ('text', 'x'), ('fmt', 'bold', False)]


# ---------------- engine type_rich ---------------- #

def test_type_rich_bold_taps_ctrl(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    marks = []
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=marks.append)
    assert eng.type_rich("Go **fast** now") is True
    assert ''.join(dummy.typed) == "Go fast now"
    assert ("press", "b") in dummy.pressed_keys  # on
    assert dummy.pressed_keys.count(("press", "b")) == 2  # on + off
    assert 'b' in marks


def test_type_rich_heading_applies_and_resets(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    assert eng.type_rich("# Title\nbody", app='word') is True
    assert ''.join(dummy.typed) == "Titlebody"  # newline goes out as Enter press
    assert ("press", "Key.enter") in dummy.pressed_keys
    assert ("press", "1") in dummy.pressed_keys  # heading 1
    assert ("press", "n") in dummy.pressed_keys  # word reset Ctrl+Shift+N
    assert eng.get_word_progress() == (2, 2)


def test_type_rich_docs_reset_uses_ctrl_alt_0(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    assert eng.type_rich("# T\nx", app='docs') is True
    assert ("press", "0") in dummy.pressed_keys
    assert ("press", "n") not in dummy.pressed_keys


def test_type_rich_resume_replays_style(monkeypatch):
    # "**hello world**", stop inside "world" (plain idx 8 -> snap 6),
    # resume must re-apply bold then close it: exactly 2 'b' taps.
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    assert eng.type_rich("**hello world**", start_index=8) is True
    assert dummy.pressed_keys.count(("press", "b")) == 2
    assert ''.join(dummy.typed) == "hello world"[6:]


def test_type_rich_resume_past_closed_style_is_plain(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    assert eng.type_rich("**hi** there", start_index=4) is True
    assert ("press", "b") not in dummy.pressed_keys
    assert ''.join(dummy.typed) == "there"  # snapped 4 -> 3 (word start)


def test_type_rich_honors_stop(monkeypatch):
    patch_engine(monkeypatch)
    import time as _time
    real_sleep = _time.sleep
    monkeypatch.setattr(_time, "sleep", lambda s: real_sleep(0))
    stop = [False]
    eng = TypingEngine(get_profile("flawless"), stop)

    def progress(cur, tot):
        if cur >= 3:
            stop[0] = True

    assert eng.type_rich("aaa **b** ccc", progress_callback=progress) is False
    assert eng.current_index == 3


# ---------------- tables ---------------- #

def test_load_csv_and_count(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("name,age\nAda,36\n,Grace\n", encoding="utf-8")
    rows = load_csv(str(p))
    assert rows == [["name", "age"], ["Ada", "36"], ["", "Grace"]]
    assert count_cells(rows) == 6


def test_load_csv_missing_and_empty(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_csv(str(tmp_path / "nope.csv"))
    p = tmp_path / "e.csv"
    p.write_text("\n\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_csv(str(p))


def test_parse_cell():
    assert parse_cell("3,1") == (2, 0)
    assert parse_cell("1,1") == (0, 0)
    with pytest.raises(ValueError):
        parse_cell("bogus")


def test_fill_table_types_cells_and_navigates(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    rows = [["a", "b"], ["c", "d"]]
    finished, pos = fill_table(eng, rows, stop_flag=[False])
    assert finished is True and pos == (1, 1)
    assert ''.join(dummy.typed) == "abcd"
    tabs = [k for k in dummy.pressed_keys if k == ("press", "Key.tab")]
    enters = [k for k in dummy.pressed_keys if k == ("press", "Key.enter")]
    assert len(tabs) == 2  # a->b, c->d
    assert len(enters) == 1  # end of row 1


def test_fill_table_empty_cells_still_navigate(monkeypatch):
    dummy = patch_engine(monkeypatch)
    _no_sleep(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    finished, _ = fill_table(eng, [["", "x"]], stop_flag=[False])
    assert finished is True
    assert ''.join(dummy.typed) == "x"


def test_fill_table_stop_reports_position_and_resumes(monkeypatch):
    patch_engine(monkeypatch)
    import time as _time
    real_sleep = _time.sleep
    monkeypatch.setattr(_time, "sleep", lambda s: real_sleep(0))
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    rows = [["a", "b"], ["c", "d"]]
    stop = [False]
    seen = []

    def progress(done, tot, r, c):
        seen.append((done, r, c))
        if done >= 2:
            stop[0] = True

    finished, pos = fill_table(eng, rows, stop_flag=stop, progress_callback=progress)
    assert finished is False
    assert pos == (1, 0)  # third cell never started
    # Resume from that cell completes the rest.
    eng2 = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    finished2, _ = fill_table(eng2, rows, stop_flag=[False], start_cell=pos)
    assert finished2 is True


def test_fill_table_rejects_bad_nav(monkeypatch):
    patch_engine(monkeypatch)
    eng = TypingEngine(get_profile("flawless"), [False], emit_hook=lambda k: None)
    with pytest.raises(ValueError):
        fill_table(eng, [["a"]], col_nav='teleport')
