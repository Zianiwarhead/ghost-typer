"""Polish flow, study loop, notes file, dry-run disclosure."""
import argparse
import sys
from pathlib import Path
from unittest import mock

import pytest

from core import brain as brain_mod
from core.profiles import get_profile
from main import append_study_note, compose_dry_run, run_study_loop


def _args(**over):
    base = {'serve': False, 'port': 8080, 'serve_token': None, 'serve_lan': False,
            'watch': None, 'interval': 30, 'bg': None, 'bg_pid': None, 'rich': False,
            'rich_app': 'word', 'bg_human': False, 'row_key': 'enter',
            'table_typos': False, 'theme': None, 'csv_resume': None,
            'countdown': 5, 'profile': 'normal', 'polish': False, 'simplify': False,
            'notes': None, 'study': False, 'ask': None, 'shot': False,
            'brain': 'api', 'brain_model': None,
            'brain_url': 'https://api.openai.com/v1', 'brain_key': 'k'}
    base.update(over)
    return argparse.Namespace(**base)


def test_polish_plain_vs_simplify(monkeypatch):
    seen = {}

    def fake_complete(api_url, api_key, model, system, blocks, timeout, max_tokens):
        seen['system'] = system
        seen['text'] = blocks[0]['text']
        seen['tokens'] = max_tokens
        return "FIXED"

    monkeypatch.setattr(brain_mod, "_api_complete", fake_complete)
    assert brain_mod.polish_text("teh cat", api_key="k") == "FIXED"
    assert "ONLY the corrected text" in seen['system']
    assert "simplify" not in seen['system'].lower()
    assert seen['text'] == "teh cat"
    brain_mod.polish_text("teh cat", simplify=True, api_key="k")
    assert "simplify" in seen['system'].lower()


def test_polish_max_tokens_scales():
    seen = {}

    def fake_complete(api_url, api_key, model, system, blocks, timeout, max_tokens):
        seen['tokens'] = max_tokens
        return "x"

    with mock.patch.object(brain_mod, "_api_complete", fake_complete):
        brain_mod.polish_text("x" * 100, api_key="k")
        assert seen['tokens'] == 400  # floor
        brain_mod.polish_text("x" * 5000, api_key="k")
        assert seen['tokens'] == 2000  # cap
        brain_mod.polish_text("x" * 100, api_key="k", max_tokens=77)
        assert seen['tokens'] == 77  # explicit wins


def test_polish_backend_validation_and_local_error():
    with pytest.raises(ValueError, match='unknown brain backend'):
        brain_mod.polish_text("x", backend='nope', api_key="k")
    with pytest.raises(RuntimeError, match='--brain-key'):
        brain_mod.polish_text("x", backend='api', api_key='')
    with mock.patch.object(brain_mod, "local_ready", return_value=(False, "nope")), \
            pytest.raises(RuntimeError, match='nope'):
        brain_mod.polish_text("x", backend='local')


def test_local_setup_checked_before_heavy_imports(monkeypatch):
    # Regression: CI has no numpy; setup must be checked BEFORE importing it,
    # or this raises ModuleNotFoundError instead of the helpful RuntimeError.
    monkeypatch.setitem(sys.modules, 'numpy', None)
    with mock.patch.object(brain_mod, "local_ready", return_value=(False, "nope")), \
            pytest.raises(RuntimeError, match='nope'):
        brain_mod.polish_text("x", backend='local')


def test_append_study_note(tmp_path):
    p = str(tmp_path / "rev.md")
    append_study_note(p, "What is X?", "X is Y.")
    append_study_note(p, "Second?", "Two.")
    content = Path(p).read_text(encoding='utf-8')
    assert content.count("**Q:**") == 2
    assert "What is X?" in content and "X is Y." in content
    assert "## " in content  # timestamped header


def test_run_study_loop_quit_ask_notes(monkeypatch, tmp_path, capsys):
    answers = iter(["what is this?", "quit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    monkeypatch.setattr(brain_mod, "ask", lambda *a, **k: "An answer.")
    monkeypatch.setattr(brain_mod, "build_context",
                        lambda screenshot=False: ("Tree text", None, []))
    notes = str(tmp_path / "rev.md")
    run_study_loop(_args(notes=notes))
    out = capsys.readouterr().out
    assert "An answer." in out
    assert "(saved to " in out
    saved = Path(notes).read_text(encoding='utf-8')
    assert "what is this?" in saved and "An answer." in saved


def test_run_study_loop_brain_failure_continues(monkeypatch, capsys):
    answers = iter(["q1", "quit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(brain_mod, "ask", boom)
    monkeypatch.setattr(brain_mod, "build_context",
                        lambda screenshot=False: ("Tree", None, []))
    run_study_loop(_args())  # must not raise; loop continues to quit
    assert "Brain failed" in capsys.readouterr().out


def test_run_study_loop_shot_toggle(monkeypatch, capsys):
    answers = iter(["/shot", "quit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    run_study_loop(_args())
    assert "Screenshots on." in capsys.readouterr().out


def test_dry_run_discloses_polish():
    out = compose_dry_run(_args(polish=True, simplify=True),
                          get_profile('normal'), "hello", None, "")
    assert "Polish" in out and "simplify" in out
    assert "NOT called in dry-run" in out
    out2 = compose_dry_run(_args(), get_profile('normal'), "hello", None, "")
    assert "Polish" not in out2
