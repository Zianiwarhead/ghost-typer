# 👻 Ghost Typer v2 — Realistic Keystroke Simulation

Type like a human, not a robot. Paste text anywhere and Ghost Typer re-types it
with human rhythm: bursts, pauses, typos + corrections, fatigue, and a
mechanical typewriter mode.

Windows-first. CLI + Tk mini-GUI. MIT open source — use it, share it, be happy.

> **Fair-use note:** built for demos, accessibility, typing effects, and content
> you own. Don't use it to deceive proctors, exams, or hiring tests.

## Features

- **Speed presets:** Sluggish 25 / Casual 45 / Normal 65 / Fast 105 / Super Fast 150 WPM + custom slider 10–200
- **Typewriter mode (~80 WPM):** steady mechanical rhythm, carriage-return pause on newlines, no bursts
- **Humanization:** WPM jitter, burst typing, thinking pauses, fatigue slowdown, fast common words
- **Typos that fix themselves:** neighbor-key errors + word transpositions (`teh → the`)
- **Soft-stop + Resume (Esc):** Esc keeps your place (`Stopped at 342/1200`), press Start again to resume — no re-typing from zero
- **Auto-pause:** window focus-loss + physical typing interference detection
- **Inputs:** clipboard, `.txt`/`.md` file, direct `--text`, GUI textbox
- **Chat-safe newlines:** `--chat-mode` uses Shift+Enter (Claude/ChatGPT/Discord)

## Quick start

```powershell
pip install -e .          # or: pip install -r requirements.txt
python main.py --list-profiles
python main.py --profile normal
python main.py --gui      # Tk mini-GUI (recommended)
```

1. Copy text (or pick a file in GUI).
2. Click your target box during the 5s countdown.
3. Hotkeys: `Ctrl+Alt+S` start/resume · `Ctrl+Alt+P` pause · `Esc` soft-stop · `Ctrl+C` quit.

## CLI examples

```powershell
python main.py --profile typewriter --chat-mode
python main.py --file essay.txt --profile fast
python main.py --text "Hello world" --wpm 90 --no-errors
python main.py --countdown 8 --no-focus-lock
python main.py --build-profile --custom myprofile.json
```

## Speed table

| Preset | WPM | Feel |
|---|---|---|
| sluggish | 25 | hunt-and-peck, heavy thinking |
| casual | 45 | relaxed |
| normal / average | 65 | typical office worker |
| fast | 105 | practiced |
| superfast | 150 | near-bot ceiling, still humanized |
| expert | 120 | accurate programmer |
| typewriter | 80 | mechanical, steady, newline clunk |
| flawless | 70 | zero typos |

Fine-tune with `--wpm N` (10–200) and `--no-errors`.

## Resume model

- Typing is index-tracked. Pause/focus-loss/user-typing keeps the index.
- `Esc` = **soft-stop**: session kept in memory, GUI/CLI shows `Stopped at X/Y`.
- Press Start again to resume from X. Restart only if you load new text.
- True "scan the target app to find the caret" is intentionally **not** attempted
  (fragile OCR/UI-automation) — index-based resume is exact and predictable.

## Project layout

```
main.py            CLI + --gui launcher
gui.py             Tk mini-GUI
core/engine.py     keystroke simulation, mechanical timing
core/controller.py hotkeys, threads, soft-stop/resume, interference guard
core/focus_guard.py Windows focus-lock (pywin32)
core/profiles.py   presets
core/inputs.py     clipboard/file/string sources
assets/            generated icon.ico/.png
tests/             pytest suite (mocked keyboard — no real keypresses)
```

## Dev

```powershell
pip install -e .[dev]
pytest -q
ruff check .
python tools\make_icon.py
```

Build exe: `pip install pyinstaller; pyinstaller --noconfirm --onefile --windowed --name GhostTyper --icon assets\icon.ico main.py`

## Roadmap

- Persistent sessions (resume after restart), per-app profiles
- Optional key-click audio for typewriter mode
- Cross-platform focus guard (macOS/Linux)
