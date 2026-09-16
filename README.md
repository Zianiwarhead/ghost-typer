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

- **Speed presets:** Sluggish 25 / Casual 45 / Normal 65 / Fast 105 / Super Fast 150 / Insane 300 WPM + custom slider 10–300
- **Typewriter mode (~80 WPM):** steady mechanical rhythm, carriage-return pause on newlines, no bursts
- **Humanization:** WPM jitter, burst typing, thinking pauses, fatigue slowdown, fast common words
- **Typos that fix themselves:** neighbor-key errors + word transpositions (`teh → the`)
- **Soft-stop + Resume (Esc):** Esc keeps your place (`Stopped at 342/1200`), press Start again to resume — no re-typing from zero
- **Auto-pause:** window focus-loss + physical typing interference detection
- **Inputs:** clipboard, `.txt`/`.md` file, direct `--text`, GUI textbox
- **Chat-safe newlines:** `--chat-mode` uses Shift+Enter (Claude/ChatGPT/Discord)
- **Rich text (`--rich`):** `**bold**`, `*italic*`, `__underline__`, `# headings` typed with real Word/Docs formatting
- **Table fill (`--csv`):** fills forms and tables cell by cell with Tab/Enter navigation
- **Background mode (`--bg`, Windows):** paste/type into an unfocused classic app while you work elsewhere

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
# Windows (use a NORMAL terminal, not Administrator —
# Admin shells start in C:\WINDOWS\System32, which is write-protected)
cd ~   # or: cd Documents — just get out of System32 first
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
| insane | 300 | ludicrous speed, no errors or pauses |

Fine-tune with `--wpm N` (10–300) and `--no-errors`.

## Resume model

- Typing is char- and word-tracked (`342/1200 chars, word 58/200`). Pause/focus-loss/user-typing keeps the place.
- `Esc` = **soft-stop**: session kept in memory, GUI/CLI shows `Stopped at X/Y`.
- Press Start again to resume from X — snapped back to the word start, so a half-typed word retypes cleanly instead of resuming mid-word. Restart only if you load new text.
- True "scan the target app to find the caret" is intentionally **not** attempted
  (fragile OCR/UI-automation) — index-based resume is exact and predictable.

## Rich text + tables

Rich mode types real formatting into Word or Google Docs (`--rich-app word|docs`):

| Markup | Result |
|---|---|
| `**bold**` | Ctrl+B bold |
| `*italic*` / `_italic_` | Ctrl+I italic |
| `__underline__` | Ctrl+U underline |
| `# H` / `## H` / `### H` | Heading 1/2/3, auto-reset to Normal after the line |

```powershell
python main.py --rich --file doc.txt            # Word styles by default
python main.py --rich --rich-app docs --file doc.txt
```

Table mode fills forms and tables from CSV — click the **first cell**, it Tabs
between cells and presses Enter (or `--row-key tab|down`) at each row end.
Typos default off so your data stays exact (`--table-typos` to allow them):

```powershell
python main.py --csv data.csv
python main.py --csv data.csv --row-key tab --csv-resume 3,1
python main.py --table-inline "Ops | node,state | us-1,[B]ON[/B]"
```

No file? `--table-inline` builds a one-off table inline: `"Title | h1,h2 |
r1c1,r1c2 | …"` (`\|`/`\,` escapes). Background table pastes take
`--theme matrix|dracula|steel` for styled output.

## Background mode (experimental, Windows, CLI-only)

Delivers text into a window **without focusing it**, so you keep working
elsewhere. Reuses every source above:

```powershell
python main.py --bg "Notepad" --file note.txt      # instant paste
python main.py --bg "Word" --rich --file doc.txt   # formatted paste (bold, tables)
python main.py --bg "Word" --csv data.csv      # CSV -> HTML table paste
python main.py --bg "Notepad" --bg-human --file note.txt  # paced keystrokes
python main.py --bg-pid 12345 --file note.txt      # precise PID targeting
```

How it works: the target is resolved to its edit control, the payload goes
on the clipboard (your text clipboard is saved and restored), and a `WM_PASTE`
message is posted to its queue. `--bg-human` instead posts paced `WM_CHAR`
keystrokes (plain text, resumable, never touches the clipboard).

Honest limits (platform-enforced):
- Classic apps only: Notepad, WordPad, Word. **Browsers, Discord, VS Code,
  and Electron apps do not honor background paste — use normal mode there.**
- Click to position the caret first; minimized windows may swallow the paste.
- Ambiguous window titles are refused (you'll get the candidate list) —
  use a fuller title or `--bg-pid`.
- Only BMP characters travel over `WM_CHAR`; astral characters become `?`.

## Remote control (phone / LAN, Windows)

```powershell
python main.py --serve --port 8080
# phone browser -> http://<your-pc-ip>:8080/  (dashboard)
curl -X POST http://127.0.0.1:8080/api/v1/type -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"target":"Notepad","text":"hello","mode":"human"}'
```

Modes: `human` (background typing, `--bg-typos` via `typos: true`),
`rich` (markup → formatted paste), `table` (inline `"T | h1,h2 | r1,r2"` or
`rows` array → themed paste via `theme`). `GET /api/v1/status` reports
whether a job is running (a second job gets 409 busy, like the CLI).

Security, stated plainly (no encryption theater here):
- A bearer **token is required** on every call (auto-generated and printed,
  or pass `--serve-token`). No token, no typing.
- Binds **localhost only** unless `--serve-lan` opts into LAN exposure.
- Traffic is plain HTTP: fine on a trusted home LAN with the token, but
  assume anyone capturing packets can read it. No public internet, ever.

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
core/richtext.py           **bold**/*italic*/# heading markup parser
core/tables.py             CSV table-fill driver (Tab/Enter nav)
core/background.py         focus-free delivery: HWND lock, HTML clipboard, WM_PASTE/WM_CHAR
core/table_themes.py         themed HTML tables (matrix/dracula/steel) for paste
core/netserver.py            stdlib-only remote API + phone dashboard (token auth)
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
