"""Drop-folder watcher: scan/load/settle semantics (delivery-free)."""
import os

import pytest

from core import watcher as w


def _touch(path, content="x", mtime=None):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_scan_empty_and_ignores_nonmatching(tmp_path):
    assert w.scan(str(tmp_path)) is None
    _touch(str(tmp_path / "run.exe"), "x")
    os.makedirs(str(tmp_path / "done"))
    _touch(str(tmp_path / "done" / "old.txt"), "x")
    assert w.scan(str(tmp_path)) is None  # only subdir content: ignored


def test_scan_picks_oldest(tmp_path):
    d = str(tmp_path)
    _touch(os.path.join(d, "b.txt"), "b", mtime=2000)
    _touch(os.path.join(d, "a.txt"), "a", mtime=1000)
    assert w.scan(d).endswith("a.txt")


def test_scan_case_insensitive_ext(tmp_path):
    d = str(tmp_path)
    _touch(os.path.join(d, "N.MD"), "x")
    assert w.scan(d).endswith("N.MD")


def test_load_kinds_and_failures(tmp_path):
    d = str(tmp_path)
    p1 = os.path.join(d, "a.txt")
    p2 = os.path.join(d, "b.md")
    _touch(p1, "hello")
    _touch(p2, "# hi")
    assert w.load_job(p1) == ('text', "hello")
    assert w.load_job(p2) == ('rich', "# hi")
    _touch(os.path.join(d, "e.txt"), "   ")
    with pytest.raises(ValueError):
        w.load_job(os.path.join(d, "e.txt"))
    with pytest.raises(ValueError):
        w.load_job(os.path.join(d, "x.csv"))
    with pytest.raises(ValueError):
        w.load_job(os.path.join(d, "missing.txt"))


def test_settle_routes_and_moves(tmp_path):
    d = str(tmp_path)
    w.ensure_dirs(d)
    p1 = os.path.join(d, "ok.txt")
    p2 = os.path.join(d, "bad.txt")
    _touch(p1, "x")
    _touch(p2, "x")
    dest1 = w.settle(p1, True)
    dest2 = w.settle(p2, False)
    assert dest1 == os.path.join(d, "done", "ok.txt")
    assert dest2 == os.path.join(d, "failed", "bad.txt")
    assert os.path.exists(dest1) and os.path.exists(dest2)
    assert not os.path.exists(p1)
