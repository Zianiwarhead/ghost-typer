"""Doctor exit codes + dry-run composer (no side effects)."""
import argparse
import sys

from core.doctor import run as run_doctor
from core.profiles import get_profile
from main import compose_dry_run


def _args(**over):
    base = {'serve': False, 'port': 8080, 'serve_token': None, 'serve_lan': False,
            'watch': None, 'interval': 30, 'bg': None, 'bg_pid': None, 'rich': False,
            'rich_app': 'word', 'bg_human': False, 'row_key': 'enter',
            'table_typos': False, 'theme': None, 'csv_resume': None,
            'countdown': 5, 'profile': 'normal'}
    base.update(over)
    return argparse.Namespace(**base)


def test_doctor_returns_int():
    assert run_doctor() in (0, 1)


def test_doctor_detects_missing_dep(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pyperclip', None)
    assert run_doctor() == 1


def test_dry_run_plain_focused():
    out = compose_dry_run(_args(), get_profile('normal'), "hello world", None, "")
    assert "Dry run" in out
    assert "11 chars" in out
    assert "focused typing" in out
    assert "Est. time" in out


def test_dry_run_table_and_rich():
    rows = [["a", "b"], ["1", "2"]]
    out = compose_dry_run(_args(), get_profile('normal'), None, rows, "")
    assert "2 rows" in out and "4 cells" in out
    out2 = compose_dry_run(_args(rich=True), get_profile('normal'), "Hi **there**", None, "")
    assert "markup found" in out2


def test_dry_run_bg_unresolved_warns():
    out = compose_dry_run(_args(bg="No Such Window XYZ"), get_profile('normal'),
                          "hello", None, "")
    assert "UNRESOLVED" in out
    assert "Warnings" in out


def test_dry_run_serve_and_watch_modes():
    out = compose_dry_run(_args(serve=True, serve_lan=True), get_profile('normal'),
                          None, None, "")
    assert "remote API" in out
    assert "Warnings" in out  # LAN + auto token warning
    out2 = compose_dry_run(_args(watch="C:/drops"), get_profile('normal'), None, None, "")
    assert "watch C:/drops" in out2
    assert ".txt" in out2 and "done/" in out2
