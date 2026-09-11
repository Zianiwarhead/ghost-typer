# 👻 Ghost Typer v2 — Realistic Keystroke Simulation

![Tests](https://github.com/Zianiwarhead/ghost-typer/actions/workflows/test.yml/badge.svg)

Type like a human, not a robot. Paste text anywhere and Ghost Typer re-types it
with human rhythm: bursts, pauses, typos + corrections, fatigue, and a
mechanical typewriter mode.

Windows, macOS, and Linux (incl. SteamOS desktop mode). CLI + Tk mini-GUI.
MIT open source — use it, share it, be happy.

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

## Platform support

| OS | Typing | Focus-lock (auto-pause on switch) |
|---|---|---|
| Windows | ✅ | ✅ full window-level |
| macOS | ✅ | ✅ app-level (no permission prompt) — [details](#macos-focus-lock) |
| Linux (X11 / XWayland, incl. SteamOS desktop mode) | ✅ | ✅ via `xdotool` |
| Linux (pure Wayland, e.g. GNOME Wayland) | ✅ | ❌ degrades gracefully — typing still works |

Focus-lock is a safety/convenience feature, not a requirement — typing works
everywhere; on platforms where the lock can't be established, Ghost Typer
tells you why and keeps going without it.

### macOS focus-lock

Tracks the frontmost **application**, not the specific window, so it needs no
Accessibility permission and works instantly. The trade-off: switching
between two windows of the *same* app won't register as a focus change.

### Linux focus-lock

Needs `xdotool` installed as a system package (`sudo apt install xdotool` or
your distro's equivalent). Works on X11 and XWayland-backed sessions — this
covers SteamOS desktop mode via Gamescope's XWayland layer. Pure-Wayland
compositors block the window queries this relies on; that's a platform
security restriction, not something a workaround can fix.

## Quick start

First, clone the repo and **change into its folder** — every command below
must run from there (not from `System32` or your home folder):

```powershell
# Windows
git clone https://github.com/Zianiwarhead/ghost-typer.git
cd ghost-typer
pip install -e .          # or: pip install -r requirements.txt
python main.py --list-profiles
python main.py --profile normal
python main.py --gui      # Tk mini-GUI (recommended)
```

```bash
# macOS / Linux
git clone https://github.com/Zianiwarhead/ghost-typer.git
cd ghost-typer
pip3 install -e .         # or: pip3 install -r requirements.txt
python3 main.py --list-profiles
python3 main.py --profile normal
python3 main.py --gui     # Tk mini-GUI (recommended)
```

> **Wrong-folder errors?** If you see `does not appear to be a Python project`
> or `can't open file '...main.py'`, your terminal is in the wrong directory
> (e.g. `C:\WINDOWS\System32`). `cd` into the `ghost-typer` folder first —
> `pip install -e .` means "install the project *in this folder*".

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
main.py                    CLI + --gui launcher
gui.py                     Tk mini-GUI
core/engine.py             keystroke simulation, mechanical timing
core/controller.py         hotkeys, threads, soft-stop/resume, interference guard
core/focus_guard.py        platform dispatcher — picks the backend below by OS
core/focus_guard_windows.py  Windows focus-lock (pywin32)
core/focus_guard_macos.py    macOS focus-lock (pyobjc, app-level)
core/focus_guard_linux.py    Linux focus-lock (xdotool)
core/focus_guard_base.py     shared interface + graceful no-op fallback
core/profiles.py           presets
core/inputs.py             clipboard/file/string sources
assets/                    generated icon.ico/.png
tests/                     pytest suite (mocked keyboard — no real keypresses)
```

## Dev

```powershell
pip install -e .[dev]
pytest -q
ruff check .
python tools\make_icon.py
```

On headless Linux (including CI), `pynput` needs a live X display just to
import — run tests under a virtual one: `sudo apt install xvfb && xvfb-run -a pytest -q`.

Build exe: `pip install pyinstaller; pyinstaller --noconfirm --onefile --windowed --name GhostTyper --icon assets\icon.ico main.py`

## Roadmap

- Persistent sessions (resume after restart), per-app profiles
- Optional key-click audio for typewriter mode
- `--strict-focus` on macOS: opt-in window-level tracking via the
  Accessibility API, for people who need per-window (not per-app) precision
