"""
inputs.py - All text input sources for GhostTyper.
Handles clipboard, file, and direct string input.
"""

import os

import pyperclip


def get_from_clipboard() -> str:
    text = pyperclip.paste()
    if not text or not text.strip():
        raise ValueError("Clipboard is empty. Copy some text first.")
    return text

def get_from_file(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    _, ext = os.path.splitext(path)
    if ext.lower() not in [".txt", ".md", ""]:
        raise ValueError(f"Unsupported file type \x27{ext}\x27. Use .txt or .md files.")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        raise ValueError(f"File is empty: {path}")
    return text

def get_from_string(text: str) -> str:
    if not text or not text.strip():
        raise ValueError("Provided text is empty.")
    return text

def estimate_time(text: str, wpm: int) -> str:
    words = len(text) / 5
    seconds = (words / wpm) * 60
    if seconds < 60:
        return f"~{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"~{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"~{hours}h {mins}m"

def preview_text(text: str, max_chars: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."
