"""
main.py — GhostTyper entry point.
"""

import argparse
import os
import sys
import time

from core import background as bg
from core.controller import SessionController
from core.engine import TypingEngine, count_words
from core.focus_guard import BACKEND_AVAILABLE, FocusGuard
from core.inputs import (
    estimate_time,
    get_from_clipboard,
    get_from_file,
    get_from_string,
    preview_text,
)
from core.profiles import (
    build_custom_profile_interactive,
    clamp_wpm,
    get_profile,
    list_profiles,
    load_custom_profile,
)

BANNER = r"""
   _____ _               _     _______
  / ____| |             | |   |__   __|
 | |  __| |__   ___  ___| |_     | |_   _ _ __   ___ _ __
 | | |_ | '_ \ / _ \/ __| __|    | | | | | '_ \ / _ \ '__|
 | |__| | | | | (_) \__ \ |_     | | |_| | |_) |  __/ |
  \_____|_| |_|\___/|___/\__|    |_|\__, | .__/ \___|_|
                                     __/ | |
                                    |___/|_|
  Realistic Keystroke Simulation Engine  -  v2.7.1  (soft-stop + resume)
"""

HELP_TEXT = """
HOTKEYS:
  Ctrl + Alt + S    ->  Start typing / Resume from soft-stop
  Ctrl + Alt + P    ->  Pause / Resume
  Esc               ->  Soft-stop (keeps place — Start resumes)
  Ctrl + C          ->  Quit

USAGE EXAMPLES:
  python main.py                          # Clipboard mode, normal profile
  python main.py --gui                    # Tk mini-GUI (recommended)
  python main.py --profile typewriter     # Mechanical rhythm ~80 WPM
  python main.py --profile superfast      # ~150 WPM ceiling
  python main.py --file essay.txt         # Type from a .txt file
  python main.py --list-profiles          # Show all presets
  python main.py --custom myprofile.json  # Load saved custom profile
  python main.py --build-profile          # Create a custom profile
  python main.py --wpm 90 --no-errors     # Quick overrides (10-300)
  python main.py --countdown 8            # Longer countdown (default: 5)
  python main.py --no-focus-lock          # Disable window focus guard
  python main.py --no-interference        # Disable auto-pause on your own typing
  python main.py --rich --file doc.txt    # **Bold**, *italic*, # headings (Word/Docs)
  python main.py --csv data.csv           # Fill a table cell by cell (Tab nav)
  python main.py --csv data.csv --row-key tab --csv-resume 3,1
  python main.py --bg "Notepad" --file note.txt   # Background paste, no focus needed
  python main.py --bg "Word" --rich --file doc.txt  # Background formatted paste
  python main.py --bg "Notepad" --bg-human --file note.txt  # Paced background keys
  python main.py --serve --port 8080           # Remote API + phone dashboard
  python main.py --watch C:\\drops --bg "Word"  # Paste dropped .txt/.md files
  python main.py --doctor                      # Environment self-check
  python main.py --file essay.txt --dry-run    # Preview the delivery plan
"""

# ------------------------------------------------------------------ #
#  PROGRESS                                                            #
# ------------------------------------------------------------------ #

def make_progress_bar(current: int, total: int, width: int = 30, words: tuple | None = None) -> str:
    pct = current / total if total > 0 else 0
    filled = int(width * pct)
    bar = "#" * filled + "-" * (width - filled)
    s = f"[{bar}] {int(pct*100):>3}%  ({current}/{total} chars"
    if words is not None:
        s += f", word {words[0]}/{words[1]}"
    return s + ")"

def print_progress(current: int, total: int, words: tuple | None = None) -> None:
    print(f"\r  {make_progress_bar(current, total, words=words)}", end='', flush=True)

# ------------------------------------------------------------------ #
#  COUNTDOWN                                                           #
# ------------------------------------------------------------------ #

def run_countdown(seconds: int, prompt: str = "Click your target box NOW!") -> None:
    """Visible countdown — click your target box during this time."""
    print("\n  +-------------------------------------+")
    print(f"  |  {prompt:<35} |")
    print("  |  Typing starts in...                |")
    for i in range(seconds, 0, -1):
        bar = "#" * i + "-" * (seconds - i)
        print(f"  |  [{bar}]  {i}s remaining   |", end='\r')
        time.sleep(1)
    print("  |  GO!                                |")
    print("  +-------------------------------------+\n")

# ------------------------------------------------------------------ #
#  SESSION RUNNER                                                      #
# ------------------------------------------------------------------ #

def run_typing_session(
    text: str,
    profile: dict,
    controller: SessionController,
    use_focus_lock: bool = True,
    start_index: int = 0,
    use_interference: bool = True,
    rich_app: str | None = None,
) -> None:
    """Runs inside the background typing thread. Supports resume via start_index.

    rich_app ('word'/'docs') enables markup mode: session/progress indexes
    count PLAIN characters while the engine types the markup with formatting.
    """
    from core.richtext import has_markup, strip_rich

    # --- Focus guard setup ---
    focus_guard = FocusGuard(controller.pause_flag, controller.stop_flag)

    if use_focus_lock and BACKEND_AVAILABLE:
        target_title = focus_guard.lock_to_current_window()
        focus_guard.start_watching()
        print(f"  Locked to: '{target_title}'")
        print("  Switch away -> auto-pause. Return -> auto-resume.\n")
    elif use_focus_lock and not BACKEND_AVAILABLE:
        print(f"  Focus lock unavailable ({focus_guard.unavailable_reason}).\n")

    plain = strip_rich(text) if rich_app else text
    if rich_app:
        if not plain.strip():
            print("[!] Rich text has no printable content.")
            return
        if not has_markup(text):
            print("  (note: --rich found no markup — typing as plain text)")

    # Fresh start vs resume bookkeeping (plain offsets in rich mode)
    is_resume = start_index > 0
    if not is_resume:
        controller.save_session(plain, profile,
                                rich_source=text if rich_app else None,
                                rich_app=rich_app or 'word')
    else:
        # Keep same text/profile, just continue the index.
        controller.last_text = plain
        controller.last_profile = dict(profile)
        controller.last_total = len(plain)
        controller.update_index(start_index, len(plain))

    # --- Engine (emit_hook feeds the interference guard) ---
    engine = TypingEngine(profile, controller.stop_flag, emit_hook=controller.mark_own_emit)
    if use_interference:
        controller.start_interference_watch()

    est = estimate_time(plain[start_index:], profile['wpm'])
    resume_tag = f" (resuming from {start_index}/{len(plain)})" if is_resume else ""
    rich_tag = f" | rich:{rich_app}" if rich_app else ""
    print(f"  [>] Typing started — {len(plain)} chars{resume_tag} — est. {est}")
    print(f"  Profile : {profile.get('name', 'Custom')} | "
          f"{profile['wpm']} WPM | "
          f"Errors: {'on' if profile.get('errors_enabled', True) else 'off'}"
          f"{' | mechanical' if profile.get('mechanical') else ''}{rich_tag}\n")

    def progress(current: int, total: int) -> None:
        controller.wait_if_paused()
        w = engine.get_word_progress()
        controller.update_index(current, total, w[0], w[1])
        print_progress(current, total, words=w)

    if rich_app:
        success = engine.type_rich(text, app=rich_app, progress_callback=progress,
                                   start_index=start_index)
    else:
        success = engine.type_text(text, progress_callback=progress, start_index=start_index)

    focus_guard.stop_watching()
    print()

    if success:
        controller.clear_session()
        print("\n  [Done]\n")
    else:
        info = controller.get_resume_info()
        print(f"\n  [Soft-stopped at {info['index']}/{info['total']} chars "
              f"(word {info['word_index']}/{info['word_total']}, resumes at word start)]")
        print(f"  Press Ctrl+Alt+S to resume. Next: '{info['remaining_preview']}'\n")


def run_table_session(
    rows: list,
    profile: dict,
    controller: SessionController,
    col_nav: str = 'tab',
    row_nav: str = 'enter',
    start_cell: tuple = (0, 0),
    use_interference: bool = True,
    use_focus_lock: bool = True,
) -> None:
    """Fills a CSV table cell by cell (see core.tables)."""
    from core.tables import count_cells, fill_table

    focus_guard = FocusGuard(controller.pause_flag, controller.stop_flag)
    if use_focus_lock and BACKEND_AVAILABLE:
        target_title = focus_guard.lock_to_current_window()
        focus_guard.start_watching()
        print(f"  Locked to: '{target_title}'")
        print("  Switch away -> auto-pause. Return -> auto-resume.\n")
    elif use_focus_lock and not BACKEND_AVAILABLE:
        print(f"  Focus lock unavailable ({focus_guard.unavailable_reason}).\n")

    total = count_cells(rows)
    print(f"  [>] Table fill started — {len(rows)} rows, {total} cells "
          f"(Tab nav: {col_nav}, row end: {row_nav})\n")

    engine = TypingEngine(profile, controller.stop_flag, emit_hook=controller.mark_own_emit)
    if use_interference:
        controller.start_interference_watch()

    def progress(done: int, tot: int, r: int, c: int) -> None:
        print(f"\r  [cell {done}/{tot} — row {r + 1}/{len(rows)}]", end='', flush=True)

    finished, (rr, cc) = fill_table(
        engine, rows, col_nav=col_nav, row_nav=row_nav,
        stop_flag=controller.stop_flag,
        pause_checker=controller.wait_if_paused,
        progress_callback=progress, start_cell=start_cell,
    )
    focus_guard.stop_watching()
    print()
    if finished:
        print("\n  [Done] Table filled.\n")
    else:
        print(f"\n  [Soft-stopped at row {rr + 1}, col {cc + 1}]")
        print(f"  Resume with: --csv-resume {rr + 1},{cc + 1}\n")


class _BgMsgKeyboard:
    """pynput-shaped keyboard posting WM_CHAR — lets the real TypingEngine
    (typos, corrections, fatigue, bursts) drive background typing."""

    def __init__(self, hwnd):
        from core import background as _bg
        self._bg = _bg
        self.hwnd = hwnd

    def type(self, s):
        for ch in s:
            self._bg.send_char(self.hwnd, ch)

    def press(self, key):
        from pynput.keyboard import Key
        try:
            mapping = {Key.backspace: '\b', Key.enter: '\r',
                       Key.tab: '\t', Key.space: ' '}
            if key in mapping:
                self._bg.send_char(self.hwnd, mapping[key])
        except Exception:
            pass
        # Modifiers and the rest: messages carry no shift state — ignore.

    def release(self, key):
        pass

    def pressed(self, *keys):
        from contextlib import nullcontext
        return nullcontext()


class _BgTableTyper:
    """Minimal engine-shaped sender so tables.fill_table works over messages."""

    def __init__(self, hwnd, stop_flag, delay: float):
        from core import background as _bg
        self._bg = _bg
        self.hwnd = hwnd
        self.stop_flag = stop_flag
        self.delay = delay

    def type_text(self, text: str, progress_callback=None, start_index: int = 0) -> bool:
        for ch in text[start_index:]:
            if self.stop_flag[0]:
                return False
            self._bg.send_char(self.hwnd, ch)
            time.sleep(self.delay)
        return True

    def _tap(self, key, key_id: str) -> None:
        from pynput.keyboard import Key
        vk = {Key.tab: 0x09, Key.enter: 0x0D, Key.down: 0x28}.get(key, 0x0D)
        self._bg.send_key(self.hwnd, vk)


def run_background_session(plan: dict, controller: SessionController) -> None:
    """Delivers plan to a background window (no focus steal). See --bg.

    plan keys: kind ('text'|'html'|'table'), text/html/rows, keyword, human,
    profile, start_index/start_cell, plain (session text for human mode).
    """
    from core import background as bg

    keyword = plan.get('keyword')
    result = plan.get('result')

    def _mark(ok: bool, reason: str = "") -> None:
        if result is not None:
            result['ok'] = ok
            result['reason'] = reason

    try:
        _top, edit, title = bg.resolve_target(keyword=keyword, pid=plan.get('pid'))
    except (RuntimeError, ValueError) as e:
        print(f"\n[!] {e}\n")
        _mark(False, str(e))
        return
    print(f"  Locked (background) to: '{title}' — it stays unfocused, keep working.\n")

    if bg.is_web_target(title, keyword or ""):
        print(f"\n[!] {bg.web_target_guidance(title)}\n")
        controller.clear_session()
        _mark(False, "web target refused")
        return

    human = plan.get('human', False)
    profile = plan['profile']
    stop_flag = controller.stop_flag

    for remaining in range(max(0, min(int(plan.get('countdown', 0)), 60)), 0, -1):
        if stop_flag[0]:
            _mark(False, "stopped")
            return
        print(f"\r  Delivering in {remaining}s — position the caret!", end='', flush=True)
        time.sleep(1)
    if plan.get('countdown'):
        print()
    if stop_flag[0]:
        _mark(False, "stopped")
        return
    if not bg.verify_window_alive(edit):
        print("\n[!] Target window closed or hung — aborted.\n")
        _mark(False, "target dead")
        return

    if not human:
        # Instant paste via borrowed clipboard (saved + restored).
        saved = bg.save_clipboard()
        try:
            if plan['kind'] == 'html':
                bg.set_clipboard_html(plan['html'])
            elif plan['kind'] == 'table':
                bg.set_clipboard_html(
                    bg.rows_to_html_table(plan['rows'], theme=plan.get('theme'),
                                          title=plan.get('title', '')))
            else:
                bg.set_clipboard_text(plan['text'])
            if stop_flag[0]:
                return
            bg.paste_to_hwnd(edit)
            time.sleep(0.6)  # let the target process the paste
        finally:
            bg.restore_clipboard(saved)
        controller.clear_session()
        print("\n  [Done] Pasted into background window (clipboard restored).\n")
        _mark(True)
        return

    # Human mode: the REAL TypingEngine drives message-posting, so typos,
    # corrections, fatigue, and bursts all work (see --bg-typos in profile).
    plain = plan['plain']
    total = len(plain)
    start = max(0, min(plan.get('start_index', 0), total))
    controller.save_session(plain, profile)
    controller.update_index(start, total)
    base = 60.0 / (max(profile['wpm'], 1) * 5)
    print(f"  [>] Background typing — {total} chars from {start}.\n")

    if plan['kind'] == 'table':
        from core.tables import fill_table
        sender = _BgTableTyper(edit, stop_flag, base)

        def tprogress(done: int, tot: int, r: int, c: int) -> None:
            controller.wait_if_paused()
            print(f"\r  [cell {done}/{tot} — row {r + 1}/{len(plan['rows'])}]", end='', flush=True)
            if done % 5 == 0 and not bg.verify_window_alive(edit):
                stop_flag[0] = True

        finished, (rr, cc) = fill_table(
            sender, plan['rows'], col_nav=plan.get('col_nav', 'tab'),
            row_nav=plan.get('row_nav', 'enter'), stop_flag=stop_flag,
            pause_checker=controller.wait_if_paused,
            progress_callback=tprogress, start_cell=plan.get('start_cell', (0, 0)),
        )
        print()
        if finished:
            controller.clear_session()
            print("\n  [Done] Table typed into background window.\n")
            _mark(True)
        else:
            print(f"\n  [Soft-stopped at row {rr + 1}, col {cc + 1}]")
            print(f"  Resume with: --csv-resume {rr + 1},{cc + 1}\n")
            _mark(False, "stopped")
        return

    engine = TypingEngine(profile, stop_flag, emit_hook=None)
    engine.keyboard = _BgMsgKeyboard(edit)

    def progress(current: int, total: int) -> None:
        controller.wait_if_paused()
        w = engine.get_word_progress()
        controller.update_index(current, total, w[0], w[1])
        print_progress(current, total, words=w)
        if current and current % 20 == 0 and not bg.verify_window_alive(edit):
            stop_flag[0] = True

    success = engine.type_text(plain, progress_callback=progress, start_index=start)
    print()
    if success:
        controller.clear_session()
        print("\n  [Done] Typed into background window.\n")
        _mark(True)
    else:
        info = controller.get_resume_info()
        print(f"\n  [Soft-stopped at {info['index']}/{info['total']}]")
        print("  Press Ctrl+Alt+S to resume.\n")
        _mark(False, "stopped")

# ------------------------------------------------------------------ #
#  ARGS                                                                #
# ------------------------------------------------------------------ #

def parse_args():
    parser = argparse.ArgumentParser(
        prog='ghosttyper',
        description='GhostTyper — Realistic keystroke simulation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=HELP_TEXT
    )

    source = parser.add_mutually_exclusive_group()
    source.add_argument('--file', '-f', metavar='PATH')
    source.add_argument('--text', '-t', metavar='TEXT')
    source.add_argument('--csv', metavar='PATH',
                        help='Table-fill mode: type a CSV file cell by cell (Tab/Enter nav)')
    source.add_argument('--table-inline', metavar='SPEC',
                        help='Table-fill mode without a file: "Title | h1,h2 | r1c1,r1c2 [| ...]"')

    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument('--profile', '-p', metavar='NAME', default='normal')
    profile_group.add_argument('--custom', '-c', metavar='PATH')

    parser.add_argument('--wpm', type=int, help='Override WPM (10-300)')
    parser.add_argument('--no-errors', action='store_true')
    parser.add_argument('--list-profiles', action='store_true')
    parser.add_argument('--build-profile', action='store_true')
    parser.add_argument('--gui', action='store_true',
                        help='Launch Tk mini-GUI instead of CLI hotkey mode')
    parser.add_argument('--countdown', type=int, default=5,
                        help='Seconds before typing starts (default: 5)')
    parser.add_argument('--no-focus-lock', action='store_true',
                        help='Disable window focus guard')
    parser.add_argument('--no-interference', action='store_true',
                        help='Disable auto-pause when you physically type mid-run')
    parser.add_argument('--hard-stop', action='store_true',
                        help='Esc clears resume state instead of soft-stop')
    parser.add_argument('--chat-mode', action='store_true',
                        help='Use Shift+Enter for newlines (safe for Claude, ChatGPT, Discord etc)')
    parser.add_argument('--rich', action='store_true',
                        help='Rich-text mode: **bold**, *italic*, __underline__, # headings (Word/Docs)')
    parser.add_argument('--rich-app', choices=['word', 'docs'], default='word',
                        help='Target app for rich styles: heading reset shortcut (default: word)')
    parser.add_argument('--row-key', choices=['enter', 'tab', 'down'], default='enter',
                        help='CSV table-fill: key ending each row (default: enter; Word tables often want tab)')
    parser.add_argument('--csv-resume', metavar='ROW,COL',
                        help='CSV table-fill: start at cell ROW,COL, 1-based (e.g. 3,1)')
    parser.add_argument('--table-typos', action='store_true',
                        help='Table-fill: allow typos (default off — data integrity)')
    parser.add_argument('--theme', choices=['matrix', 'dracula', 'steel'], default=None,
                        help='Background table paste: styled theme (default: plain table)')
    parser.add_argument('--bg', metavar='KEYWORD',
                        help='Background mode: deliver to the window whose title contains KEYWORD '
                             'without focusing it (classic apps: Notepad, WordPad, Word — NOT browsers)')
    parser.add_argument('--bg-pid', metavar='PID', type=int,
                        help='Background mode: deliver to the window owned by PID '
                             '(precise alternative to --bg)')
    parser.add_argument('--bg-human', action='store_true',
                        help='Background mode: paced keystrokes instead of instant paste (plain only)')
    parser.add_argument('--bg-typos', action='store_true',
                        help='Background human mode: allow typos/corrections (default off)')
    parser.add_argument('--serve', action='store_true',
                        help='Remote mode: run the LAN REST API (dashboard + POST /api/v1/type)')
    parser.add_argument('--port', type=int, default=8080,
                        help='Remote mode: listen port (default: 8080)')
    parser.add_argument('--serve-token', metavar='TOKEN',
                        help='Remote mode: API bearer token (auto-generated if omitted)')
    parser.add_argument('--serve-lan', action='store_true',
                        help='Remote mode: bind all interfaces (default: localhost only)')
    parser.add_argument('--watch', metavar='DIR',
                        help='Watch mode: paste .txt/.md files dropped in DIR to the --bg target')
    parser.add_argument('--interval', type=int, default=30,
                        help='Watch mode: poll DIR every N seconds (default: 30)')
    parser.add_argument('--doctor', action='store_true',
                        help='Check environment (deps, clipboard, backends) and exit')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print exactly what would be delivered, then exit (no side effects)')

    return parser.parse_args()

# ------------------------------------------------------------------ #
#  MAIN                                                                #
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
#  DRY RUN                                                           #
# ------------------------------------------------------------------ #

def compose_dry_run(args, profile, static_text, table_rows, table_title) -> str:
    """Describes exactly what the flags would deliver. Side-effect free
    except reading the clipboard (when it's the source) and listing
    windows (to resolve --bg targets)."""
    from core.inputs import estimate_time
    from core.tables import count_cells
    lines = ["", "  Dry run — nothing will be typed, pasted, or copied.", ""]
    warnings: list = []

    if getattr(args, 'serve', False):
        lines.append(f"  Mode       : remote API on port {args.port} "
                     f"({'LAN-exposed' if args.serve_lan else 'localhost only'})")
        lines.append(f"  Token      : {'provided' if args.serve_token else 'auto-generated'}")
        lines.append("  Endpoints  : GET / (dashboard), GET /api/v1/status, POST /api/v1/type")
        if args.serve_lan and not args.serve_token:
            warnings.append("LAN mode with an auto token — copy it from this terminal, never commit it.")
        return _dry_finish(lines, warnings)

    if getattr(args, 'watch', None):
        lines.append(f"  Mode       : watch {args.watch} every {args.interval}s")
        lines.append("  Routing    : .txt -> text paste, .md -> formatted paste")
        lines.append("  Files      : done/ on success, failed/ otherwise (never deleted)")
        if not (args.bg or args.bg_pid):
            warnings.append("--watch needs --bg/--bg-pid (drop-folder delivery is background-only).")
        return _dry_finish(lines, warnings)

    bg_mode = bool(args.bg or args.bg_pid)
    human = bool(args.bg_human)
    rich_app = args.rich_app if args.rich else None

    if table_rows is not None:
        cells = count_cells(table_rows)
        chars = sum(len(c) for r in table_rows for c in r)
        lines.append(f"  Source     : table ({len(table_rows)} rows, {cells} cells, {chars} chars)")
        if bg_mode:
            if human:
                lines.append(f"  Delivery   : background paced keys, Tab nav, row end {args.row_key}")
            else:
                from core.background import rows_to_html_table
                payload = rows_to_html_table(table_rows, theme=args.theme, title=table_title)
                lines.append(f"  Delivery   : background HTML paste ({len(payload.encode('utf-8'))} bytes"
                             + (f", theme {args.theme}" if args.theme else ", plain table") + ")")
        else:
            lines.append(f"  Delivery   : focused typing, Tab nav, row end {args.row_key}")
        lines.append(f"  Typos      : {'on' if args.table_typos else 'off (table default)'}")
    else:
        text = static_text
        if text is None:
            try:
                text = get_from_clipboard()
            except ValueError:
                text = ""
                warnings.append("clipboard is empty — nothing to deliver.")
        if rich_app:
            from core.richtext import has_markup, strip_rich
            plain = strip_rich(text)
            lines.append(f"  Source     : {len(plain)} plain chars"
                         + (" (markup found)" if has_markup(text)
                            else " (NOTE: no markup — would type plain)"))
            text = plain
        else:
            lines.append(f"  Source     : {len(text)} chars, {count_words(text)} words")
        if bg_mode:
            if human and rich_app:
                lines.append("  Delivery   : background paced keys (plain — formatting needs paste mode)")
            elif human:
                lines.append("  Delivery   : background paced keys")
            else:
                lines.append("  Delivery   : background instant paste (clipboard borrowed + restored)")
        else:
            lines.append(f"  Delivery   : focused typing ({profile.get('name')}, {profile['wpm']} WPM)")
            lines.append(f"  Est. time  : {estimate_time(text, profile['wpm'])}")

    if bg_mode:
        target = f"pid {args.bg_pid}" if args.bg_pid else f"window matching '{args.bg}'"
        try:
            _top, _edit, title = bg.resolve_target(keyword=args.bg, pid=args.bg_pid)
            lines.append(f"  Target     : '{title}' (resolves NOW)")
            if bg.is_web_target(title, args.bg or ""):
                warnings.append("target looks like a browser/chat app — delivery would be refused.")
        except (RuntimeError, ValueError) as e:
            lines.append(f"  Target     : {target} (UNRESOLVED: {e})")
            warnings.append("position the caret and make sure the window exists before running for real.")
        if not human:
            warnings.append("paste borrows the clipboard for a split second (saved + restored).")
    elif rich_app:
        lines.append(f"  Styles     : {rich_app} shortcuts (**bold**, *italic*, # headings)")
    return _dry_finish(lines, warnings)


def _dry_finish(lines: list, warnings: list) -> str:
    if warnings:
        lines.append("")
        lines.append("  Warnings:")
        lines.extend(f"    ! {w}" for w in warnings)
    lines.append("")
    return "\n".join(lines)


def main():
    print(BANNER)
    args = parse_args()

    if args.doctor:
        from core.doctor import run as run_doctor
        sys.exit(run_doctor())

    if args.list_profiles:
        list_profiles()
        return

    if args.build_profile:
        build_custom_profile_interactive()
        return

    if args.gui:
        if args.bg:
            print("(note: --bg is CLI-only for now — the GUI types into the focused window as usual)")
        try:
            from gui import launch_gui
        except ImportError as e:
            print(f"[!] GUI needs tkinter: {e}")
            sys.exit(1)
        launch_gui()
        return

    # Load profile
    try:
        profile = load_custom_profile(args.custom) if args.custom else get_profile(args.profile)
    except (ValueError, FileNotFoundError) as e:
        print(f"[!] Profile error: {e}")
        sys.exit(1)

    if args.wpm:
        profile['wpm'] = clamp_wpm(args.wpm)
    if args.no_errors:
        profile['errors_enabled'] = False
        profile['error_rate'] = 0.0
        profile['transposition_rate'] = 0.0
    profile['chat_mode'] = args.chat_mode

    # Load static text if provided
    static_text: str | None = None
    if args.text:
        static_text = get_from_string(args.text)
    elif args.file:
        try:
            static_text = get_from_file(args.file)
        except (OSError, ValueError) as e:
            print(f"[!] Cannot read file: {e}")
            sys.exit(1)

    # Load table source if provided (CSV file or inline spec; fail fast)
    table_rows: list | None = None
    table_title: str = ""
    table_label: str = ""
    start_cell: tuple = (0, 0)
    if args.csv or args.table_inline:
        from core.tables import load_csv, parse_cell, parse_inline_table
        try:
            if args.csv:
                table_rows = load_csv(args.csv)
                table_label = args.csv
            else:
                table_title, headers, body = parse_inline_table(args.table_inline)
                table_rows = [headers] + body
                table_label = "inline spec"
            if args.csv_resume:
                start_cell = parse_cell(args.csv_resume)
        except (OSError, ValueError) as e:
            print(f"[!] Cannot load table: {e}")
            sys.exit(1)
        if not args.table_typos:
            profile['errors_enabled'] = False
            profile['error_rate'] = 0.0
            profile['transposition_rate'] = 0.0

    use_focus_lock = not args.no_focus_lock
    use_interference = not args.no_interference
    rich_app = args.rich_app if args.rich else None
    bg_keyword = args.bg
    bg_pid = args.bg_pid
    bg_target = f"pid {bg_pid}" if bg_pid else f"window matching '{bg_keyword}'"
    if (bg_keyword or bg_pid) and not bg.available():
        print("[!] Background mode needs Windows + pywin32 — it is unavailable here.")
        print("    (Remove --bg/--bg-pid to use normal focused typing.)")
        sys.exit(1)

    if args.dry_run:
        print(compose_dry_run(args, profile, static_text, table_rows, table_title))
        return

    # Print info
    if table_rows is not None:
        from core.tables import count_cells
        total_chars = sum(len(c) for r in table_rows for c in r)
        print(f"  Source     : table: {table_label} ({len(table_rows)} rows, {count_cells(table_rows)} cells)")
        print(f"  Characters : {total_chars}")
        print(f"  Est. time  : {estimate_time('x' * total_chars, profile['wpm'])}")
        print(f"  Row end key: {args.row_key} | Start cell: {start_cell[0] + 1},{start_cell[1] + 1}")
        if not args.table_typos:
            print("  Typos      : off (table mode — pass --table-typos to allow)")
    elif static_text:
        print(f"  Source     : {'file: ' + args.file if args.file else 'direct text'}")
        print(f"  Preview    : {preview_text(static_text)}")
        print(f"  Characters : {len(static_text)}")
        print(f"  Est. time  : {estimate_time(static_text, profile['wpm'])}")
    else:
        print("  Source     : Clipboard")

    print(f"  Profile    : {profile.get('name')} ({profile['wpm']} WPM)")
    if rich_app:
        print(f"  Rich mode  : on ({rich_app} styles: **bold**, *italic*, # headings)")
    print(f"  Countdown  : {args.countdown}s")
    print(f"  Focus lock : {'on (auto-pause on window switch)' if use_focus_lock and BACKEND_AVAILABLE else 'off'}")
    print(f"  Stop mode  : {'hard-stop (Esc clears resume)' if args.hard_stop else 'soft-stop (Esc keeps place for resume)'}")
    print(f"  Newlines   : {'Shift+Enter (chat mode)' if args.chat_mode else 'Enter (normal mode — Word, Notepad, Docs)'}")
    if bg_keyword or bg_pid:
        print(f"  Background : to {bg_target} "
              f"({'paced keys' if args.bg_human else 'instant paste'}) — focus + interference guards off")
    print()
    print("  Hotkeys:")
    print("    Ctrl+Alt+S  ->  Start typing / Resume")
    print("    Ctrl+Alt+P  ->  Pause / Resume")
    print("    Esc         ->  Soft-stop (keeps place)")
    print("    Ctrl+C      ->  Quit")
    print()

    controller = SessionController()
    api_server = None

    def _net_dispatch(payload: dict) -> tuple:
        """POST /api/v1/type callback -> (code, message). Builds plan dicts."""
        if controller.is_typing():
            return 409, "busy: a typing session is already running"
        target = str(payload.get('target', '')).strip()
        text = payload.get('text', '')
        mode = str(payload.get('mode', 'human')).strip().lower()
        if not text or not target:
            return 400, "need 'text' and 'target'"
        if mode not in ('human', 'rich', 'table'):
            return 400, "mode must be human, rich, or table"
        if not target.isdigit() and bg.is_web_target(target):
            return 400, bg.web_target_guidance(target)
        try:
            nprofile = get_profile(str(payload.get('profile', 'normal')))
        except (ValueError, AttributeError):
            return 400, f"unknown profile {payload.get('profile')!r}"
        nprofile['chat_mode'] = False
        theme = payload.get('theme') or None
        if theme is not None:
            from core.table_themes import THEMES
            if theme not in THEMES:
                return 400, f"unknown theme {theme!r}"
        typos = bool(payload.get('typos', payload.get('obfuscate', False)))
        if mode == 'human' and not typos:
            nprofile['errors_enabled'] = False
            nprofile['error_rate'] = 0.0
            nprofile['transposition_rate'] = 0.0
        pid, keyword = None, target
        if target.isdigit():
            pid, keyword = int(target), None
        try:
            countdown = max(0, min(int(payload.get('countdown', 0)), 60))
        except (TypeError, ValueError):
            return 400, "countdown must be seconds 0-60"
        if mode == 'table':
            rows_payload = payload.get('rows')
            try:
                if isinstance(rows_payload, list) and rows_payload:
                    title, headers, body = "", rows_payload[0], rows_payload[1:]
                    if not body:
                        return 400, "table needs headers + at least one row"
                    rows = [headers] + body
                else:
                    from core.tables import parse_inline_table
                    title, headers, body = parse_inline_table(text)
                    rows = [headers] + body
            except ValueError as e:
                return 400, str(e)
            plan = {'kind': 'table', 'rows': rows, 'keyword': keyword, 'pid': pid,
                    'human': False, 'profile': nprofile, 'theme': theme,
                    'title': title, 'countdown': countdown}
        elif mode == 'rich':
            from core.background import markup_to_html
            plan = {'kind': 'html', 'html': markup_to_html(text),
                    'keyword': keyword, 'pid': pid, 'human': False,
                    'profile': nprofile, 'countdown': countdown}
        else:
            plan = {'kind': 'text', 'text': text, 'plain': text,
                    'keyword': keyword, 'pid': pid, 'human': True,
                    'profile': nprofile, 'start_index': 0, 'countdown': countdown}
        controller.start_session(run_background_session, plan, controller)
        return 200, f"{mode} job dispatched ({len(text)} chars)"

    if args.serve:
        import secrets

        from core import netserver
        if not bg.available():
            print("[!] --serve needs Windows + pywin32 for delivery targets.")
            sys.exit(1)
        token = args.serve_token or secrets.token_urlsafe(24)
        host = '0.0.0.0' if args.serve_lan else '127.0.0.1'
        api_server, _srv_thread = netserver.start_in_thread(
            host, args.port, token, _net_dispatch, controller.is_typing)
        print(f"  Remote API : http://{host}:{args.port}/  (dashboard + POST /api/v1/type)")
        print(f"  API token  : {token}")
        print("  Keep this window open — curl/phone from ANOTHER terminal while it runs.")
        if args.serve_lan:
            print("  [!] LAN-exposed: anyone on your network holding the token can type "
                  "into your apps. Trusted networks only.")

    def _bg_start() -> None:
        """Background delivery flow: resolve window, countdown, dispatch."""
        from core.richtext import has_markup, strip_rich

        bprofile = dict(profile)
        human = bool(args.bg_human)
        if human and bprofile.get('errors_enabled', True) and not args.bg_typos:
            bprofile['errors_enabled'] = False
            bprofile['error_rate'] = 0.0
            bprofile['transposition_rate'] = 0.0
            print("  (note: background human mode types clean — typos off, see --bg-typos)")
        elif human and args.bg_typos:
            print("  (background human mode: typos on — full human signature)")

        # Resume: plain-text human sessions only (rich/csv re-run fresh).
        if (controller.has_resume() and controller.last_text
                and controller.last_rich_source is None and table_rows is None):
            info = controller.get_resume_info()
            print(f"\n  Resuming background job from {info['index']}/{info['total']}")
            plan = {'kind': 'text', 'text': controller.last_text,
                    'plain': controller.last_text, 'keyword': bg_keyword, 'pid': bg_pid,
                    'human': True, 'profile': bprofile, 'start_index': info['index']}
            run_countdown(max(2, min(args.countdown, 3)))
            if controller.stop_flag[0]:
                return
            controller.start_session(run_background_session, plan, controller)
            return

        if table_rows is not None:
            if human:
                plan = {'kind': 'table', 'rows': table_rows, 'keyword': bg_keyword, 'pid': bg_pid,
                        'human': True, 'profile': bprofile, 'plain': '',
                        'col_nav': 'tab', 'row_nav': args.row_key, 'start_cell': start_cell}
            else:
                sr, sc = start_cell
                rows = [table_rows[sr][sc:]] + table_rows[sr + 1:] if sr < len(table_rows) else []
                plan = {'kind': 'table', 'rows': rows, 'keyword': bg_keyword, 'pid': bg_pid,
                        'human': False, 'profile': bprofile,
                        'theme': args.theme, 'title': table_title}
        else:
            source_text = static_text
            if source_text is None:
                try:
                    source_text = get_from_clipboard()
                    print(f"\n  Clipboard: {preview_text(source_text)}")
                except ValueError as e:
                    print(f"\n[!] {e}")
                    return
            if rich_app:
                if human:
                    print("  (note: formatting needs paste mode — background human types plain text)")
                    plain = strip_rich(source_text)
                    plan = {'kind': 'text', 'text': plain, 'plain': plain,
                            'keyword': bg_keyword, 'pid': bg_pid, 'human': True,
                            'profile': bprofile, 'start_index': 0}
                else:
                    if not has_markup(source_text):
                        print("  (note: --rich found no markup — pasting as formatted text anyway)")
                    plan = {'kind': 'html', 'html': bg.markup_to_html(source_text),
                            'keyword': bg_keyword, 'pid': bg_pid, 'human': False, 'profile': bprofile}
            else:
                if human:
                    plan = {'kind': 'text', 'text': source_text, 'plain': source_text,
                            'keyword': bg_keyword, 'pid': bg_pid, 'human': True,
                            'profile': bprofile, 'start_index': 0}
                else:
                    plan = {'kind': 'text', 'text': source_text,
                            'keyword': bg_keyword, 'pid': bg_pid, 'human': False, 'profile': bprofile}

        try:
            _top, _edit, _title = bg.resolve_target(keyword=bg_keyword, pid=bg_pid)  # fail fast
            if bg.is_web_target(_title, bg_keyword or ""):
                print(f"\n[!] {bg.web_target_guidance(_title)}\n")
                return
            print(f"  Target found: '{_title}' — position the caret, then it stays unfocused.")
        except (RuntimeError, ValueError) as e:
            print(f"\n[!] {e}\n")
            return
        run_countdown(args.countdown)
        if controller.stop_flag[0]:
            return
        controller.start_session(run_background_session, plan, controller)

    def on_start() -> None:
        if controller.is_typing():
            print("[!] Already typing. Press Esc to stop first.")
            return

        # Background branch: deliver without focusing (classic apps only).
        if bg_keyword or bg_pid:
            _bg_start()
            return

        # Table-fill branch: position in the FIRST cell (or --csv-resume),
        # then Start. No controller resume — re-entry uses --csv-resume.
        if table_rows is not None:
            run_countdown(args.countdown, "Click the FIRST CELL now!")
            if controller.stop_flag[0]:
                return
            controller.start_session(
                run_table_session,
                table_rows,
                profile,
                controller,
                'tab',
                args.row_key,
                start_cell,
                use_interference,
                use_focus_lock,
            )
            return

        # Resume path: same text, continue from last_index (no countdown repeat? keep short one)
        if controller.has_resume() and static_text is not None:
            info = controller.get_resume_info()
            print(f"\n  Resuming from char {info['index']}/{info['total']} (word {info['word_index']}/{info['word_total']}) — '{info['remaining_preview']}'")
            run_countdown(max(2, min(args.countdown, 3)))
            if controller.stop_flag[0]:
                return
            controller.resume_session(
                run_typing_session,
                controller.last_rich_source or controller.last_text,
                controller.last_profile,
                controller,
                use_focus_lock,
                use_interference=use_interference,
                rich_app=controller.last_rich_app if controller.last_rich_source else None,
            )
            return
        if controller.has_resume() and static_text is None:
            # Clipboard mode with a pending resume: prefer resuming the same
            # buffer over re-reading the clipboard (which may have changed).
            info = controller.get_resume_info()
            print(f"\n  Resuming clipboard session from {info['index']}/{info['total']}")
            run_countdown(max(2, min(args.countdown, 3)))
            if controller.stop_flag[0]:
                return
            controller.resume_session(
                run_typing_session,
                controller.last_rich_source or controller.last_text,
                controller.last_profile,
                controller,
                use_focus_lock,
                use_interference=use_interference,
                rich_app=controller.last_rich_app if controller.last_rich_source else None,
            )
            return

        # Get text
        source_text = static_text
        if source_text is None:
            try:
                source_text = get_from_clipboard()
                print(f"\n  Clipboard: {preview_text(source_text)}")
                print(f"  Length: {len(source_text)} chars | Est: {estimate_time(source_text, profile['wpm'])}")
            except ValueError as e:
                print(f"\n[!] {e}")
                return

        # Countdown — user must click target box during this time
        run_countdown(args.countdown)

        # Check if stopped during countdown
        if controller.stop_flag[0]:
            return

        controller.start_session(
            run_typing_session,
            source_text,
            profile,
            controller,
            use_focus_lock,
            use_interference=use_interference,
            rich_app=rich_app,
        )

    def on_stop(info=None) -> None:
        # Esc with no live session (e.g. during countdown) only cancels —
        # don't print a stale resume summary for a previous session.
        if not controller.is_typing():
            if args.hard_stop:
                controller.clear_session()
            print("\n  [Cancelled — nothing was typing.]\n")
            return
        if args.hard_stop:
            controller.clear_session()
            print("\n  [Stopped — resume cleared (--hard-stop)].\n")
            return
        if isinstance(info, dict) and info.get("total"):
            print(f"\n  [Soft-stopped at char {info['index']}/{info['total']} (word {info['word_index']}/{info['word_total']})] — Ctrl+Alt+S resumes.\n")
        else:
            print("\n  [Soft-stopped] — Ctrl+Alt+S resumes.\n")

    controller.on_start = on_start
    controller.on_stop = on_stop
    controller.start_listening()

    print("  Listening for hotkeys...\n")

    watch = None
    if args.watch:
        from core import watcher as _watcher
        if not (bg_keyword or bg_pid):
            print("[!] --watch needs --bg/--bg-pid (drop-folder delivery is background-only).")
            sys.exit(1)
        if not os.path.isdir(args.watch):
            print(f"[!] Watch dir not found: {args.watch}")
            sys.exit(1)
        _watcher.ensure_dirs(args.watch)
        try:
            _top, _edit, _title = bg.resolve_target(keyword=bg_keyword, pid=bg_pid)
            if bg.is_web_target(_title, bg_keyword or ""):
                print(f"\n[!] {bg.web_target_guidance(_title)}\n")
                sys.exit(1)
            print(f"  Watching  : {args.watch} every {args.interval}s -> '{_title}'")
            print("  Position the caret once — dropped .txt/.md files paste themselves.\n")
        except (RuntimeError, ValueError) as e:
            print(f"\n[!] {e}\n")
            sys.exit(1)
        watch = {'next': 0.0}

    def _watch_poll() -> None:
        from core import watcher as _watcher
        if controller.is_typing():
            print("  [watch] job running — skipping this cycle.")
            return
        job = _watcher.scan(args.watch)
        if job is None:
            return
        name = os.path.basename(job)
        print(f"\n  [watch] picked up '{name}'")
        try:
            kind, content = _watcher.load_job(job)
        except ValueError as e:
            print(f"  [watch] bad file: {e}")
            print(f"  [watch] -> failed/{name}")
            _watcher.settle(job, False)
            return
        if kind == 'rich':
            from core.background import markup_to_html
            plan = {'kind': 'html', 'html': markup_to_html(content),
                    'keyword': bg_keyword, 'pid': bg_pid,
                    'human': False, 'profile': dict(profile), 'countdown': 0}
        else:
            plan = {'kind': 'text', 'text': content,
                    'keyword': bg_keyword, 'pid': bg_pid,
                    'human': False, 'profile': dict(profile), 'countdown': 0}
        result: dict = {}
        plan['result'] = result
        controller.start_session(run_background_session, plan, controller)
        time.sleep(0.3)
        deadline = time.time() + 120
        while controller.is_typing() and time.time() < deadline:
            time.sleep(0.2)
        if controller.is_typing():
            print("  [watch] still running after 120s — leaving file for next cycle.")
            return
        ok = bool(result.get('ok', False))
        dest = _watcher.settle(job, ok)
        print(f"  [watch] {'done' if ok else 'failed'} -> {dest}"
              + (f" ({result.get('reason', '')})" if not ok and result.get('reason') else ""))

    try:
        while True:
            time.sleep(0.5)
            if watch is not None and time.time() >= watch['next']:
                watch['next'] = time.time() + max(5, args.interval)
                _watch_poll()
    except KeyboardInterrupt:
        print("\n  Goodbye.\n")
        try:
            if api_server is not None:
                api_server.shutdown()
        except Exception:
            pass
        controller.stop_listening()
        sys.exit(0)


if __name__ == "__main__":
    main()