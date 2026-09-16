"""
watcher.py — safe drop-folder automation (--watch DIR).

Drop a .txt file (pasted as text) or .md file (pasted as formatted HTML)
into the watched folder and the next poll delivers it to the background
target, then routes the file to done/ (or failed/ with the reason).

Safety rules (deliberate, non-negotiable):
  - One job at a time: a running session means skip this cycle, no overlap.
  - Never delete: files move to done/ or failed/, nothing is destroyed.
  - Web targets stay refused (the runner enforces it post-resolve too).
  - Only .txt/.md directly inside DIR (no recursion, no executables).
"""

import os
import shutil

WATCH_EXTS = {'.txt': 'text', '.md': 'rich'}


def ensure_dirs(watch_dir: str) -> tuple:
    """Creates done/ and failed/ routing dirs. Returns their paths."""
    done = os.path.join(watch_dir, 'done')
    failed = os.path.join(watch_dir, 'failed')
    os.makedirs(done, exist_ok=True)
    os.makedirs(failed, exist_ok=True)
    return done, failed


def scan(watch_dir: str):
    """Oldest matching file by mtime, or None. Skips routing dirs."""
    try:
        entries = os.listdir(watch_dir)
    except OSError:
        return None
    best = None
    for name in entries:
        path = os.path.join(watch_dir, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in WATCH_EXTS:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if best is None or mtime < best[1]:
            best = (path, mtime)
    return best[0] if best else None


def load_job(path: str) -> tuple:
    """Reads a job file -> (kind, content). Raises ValueError on problems."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in WATCH_EXTS:
        raise ValueError(f"unsupported extension for watch dir: {path}")
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise ValueError(f"cannot read {path}: {e}")
    if not content.strip():
        raise ValueError(f"empty job file: {path}")
    return WATCH_EXTS[ext], content


def settle(path: str, ok: bool) -> str:
    """Moves a finished job to done/ (ok) or failed/. Returns new path."""
    watch_dir = os.path.dirname(os.path.abspath(path))
    dest_dir = os.path.join(watch_dir, 'done' if ok else 'failed')
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(path))
    if os.path.abspath(path) != os.path.abspath(dest):
        shutil.move(path, dest)
    return dest
