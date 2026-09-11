"""
tables.py — CSV table-fill mode.

Fills forms, Word tables, and spreadsheets cell by cell: types each value
with the humanized engine, then navigates with real Tab / Enter / Down
(all marked so the interference guard knows they're ours).

Position yourself in the FIRST cell before starting. Soft-stop reports the
cell position; resume with --csv-resume ROW,COL (1-based).
"""

import csv
import time

NAV_KEYS = ('tab', 'enter', 'down')


def load_csv(path: str) -> list:
    """Loads a CSV file into rows of strings (utf-8-sig for Excel files)."""
    try:
        with open(path, 'r', encoding='utf-8-sig', newline='') as f:
            rows = [list(row) for row in csv.reader(f)]
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {path}")
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        raise ValueError(f"CSV file is empty: {path}")
    return rows


def count_cells(rows: list) -> int:
    return sum(len(r) for r in rows)


def _nav(engine, which: str) -> None:
    from pynput.keyboard import Key
    key = {'tab': Key.tab, 'enter': Key.enter, 'down': Key.down}[which]
    engine._tap(key, f'key:{which}')
    time.sleep(0.2)  # let the app settle on the new cell


def fill_table(engine, rows: list, col_nav: str = 'tab', row_nav: str = 'enter',
               stop_flag=None, pause_checker=None, progress_callback=None,
               start_cell=(0, 0)) -> tuple:
    """Fills rows starting at start_cell (0-based (row, col)).

    Returns (finished: bool, (row, col)) — on soft-stop, (row, col) is the
    cell that was NOT started (resume with --csv-resume ROW+1,COL+1).
    """
    stop_flag = stop_flag if stop_flag is not None else [False]
    if col_nav not in NAV_KEYS or row_nav not in NAV_KEYS:
        raise ValueError(f"Nav keys must be among {NAV_KEYS}")
    total = count_cells(rows)
    sr, sc = start_cell
    done = sum(len(rows[r]) for r in range(min(sr, len(rows))))
    if 0 <= sr < len(rows):
        done += min(sc, len(rows[sr]))

    for ri in range(len(rows)):
        if ri < sr:
            continue
        row = rows[ri]
        for ci in range(len(row)):
            if ri == sr and ci < sc:
                continue
            if stop_flag[0]:
                return False, (ri, ci)
            if pause_checker is not None:
                pause_checker()
            cell = row[ci]
            if cell:
                engine.type_text(cell)
            done += 1
            last = (ri == len(rows) - 1 and ci == len(row) - 1)
            if not last:
                _nav(engine, col_nav if ci < len(row) - 1 else row_nav)
            if progress_callback is not None:
                progress_callback(done, total, ri, ci)
    return True, (len(rows) - 1, len(rows[-1]) - 1)


def parse_cell(s: str) -> tuple:
    """Parses ROW,COL (1-based) for --csv-resume into 0-based (row, col)."""
    try:
        r, c = s.split(',')
        return max(0, int(r) - 1), max(0, int(c) - 1)
    except (ValueError, AttributeError):
        raise ValueError(f"Bad --csv-resume value {s!r}: use ROW,COL like 3,1")
