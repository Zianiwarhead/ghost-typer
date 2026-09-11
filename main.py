"""
main.py — GhostTyper entry point.
"""

import argparse
import sys
import time

from core.controller import SessionController
from core.engine import TypingEngine
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
  Realistic Keystroke Simulation Engine  -  v2.3.0  (soft-stop + resume)
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

def run_countdown(seconds: int) -> None:
    """Visible countdown — click your target box during this time."""
    print("\n  +-------------------------------------+")
    print("  |  Click your target box NOW!         |")
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
) -> None:
    """Fills a CSV table cell by cell (see core.tables)."""
    from core.tables import count_cells, fill_table

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
    print()
    if finished:
        print("\n  [Done] Table filled.\n")
    else:
        print(f"\n  [Soft-stopped at row {rr + 1}, col {cc + 1}]")
        print(f"  Resume with: --csv-resume {rr + 1},{cc + 1}\n")

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
                        help='CSV table-fill: allow typos (default off — data integrity)')

    return parser.parse_args()

# ------------------------------------------------------------------ #
#  MAIN                                                                #
# ------------------------------------------------------------------ #

def main():
    print(BANNER)
    args = parse_args()

    if args.list_profiles:
        list_profiles()
        return

    if args.build_profile:
        build_custom_profile_interactive()
        return

    if args.gui:
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
        except (FileNotFoundError, ValueError) as e:
            print(f"[!] {e}")
            sys.exit(1)

    # Load CSV table if provided (fail fast on bad path/content)
    csv_rows: list | None = None
    start_cell: tuple = (0, 0)
    if args.csv:
        from core.tables import load_csv, parse_cell
        try:
            csv_rows = load_csv(args.csv)
            if args.csv_resume:
                start_cell = parse_cell(args.csv_resume)
        except (FileNotFoundError, ValueError) as e:
            print(f"[!] {e}")
            sys.exit(1)
        if not args.table_typos:
            profile['errors_enabled'] = False
            profile['error_rate'] = 0.0
            profile['transposition_rate'] = 0.0

    use_focus_lock = not args.no_focus_lock
    use_interference = not args.no_interference
    rich_app = args.rich_app if args.rich else None

    # Print info
    if csv_rows is not None:
        from core.tables import count_cells
        total_chars = sum(len(c) for r in csv_rows for c in r)
        print(f"  Source     : table: {args.csv} ({len(csv_rows)} rows, {count_cells(csv_rows)} cells)")
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
    print()
    print("  Hotkeys:")
    print("    Ctrl+Alt+S  ->  Start typing / Resume")
    print("    Ctrl+Alt+P  ->  Pause / Resume")
    print("    Esc         ->  Soft-stop (keeps place)")
    print("    Ctrl+C      ->  Quit")
    print()

    controller = SessionController()

    def on_start() -> None:
        if controller.is_typing():
            print("[!] Already typing. Press Esc to stop first.")
            return

        # Table-fill branch: position in the FIRST cell (or --csv-resume),
        # then Start. No controller resume — re-entry uses --csv-resume.
        if csv_rows is not None:
            run_countdown(args.countdown)
            if controller.stop_flag[0]:
                return
            controller.start_session(
                run_table_session,
                csv_rows,
                profile,
                controller,
                'tab',
                args.row_key,
                start_cell,
                use_interference,
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

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n  Goodbye.\n")
        controller.stop_listening()
        sys.exit(0)


if __name__ == "__main__":
    main()