"""
clipfmt.py — formatted clipboard round-trip (paste as-is).

Typing is inherently plain text: formatting dies the moment you retype.
These helpers read the clipboard's HTML Format envelope back out
(byte offsets parsed in reverse of background.build_html_clipboard_payload)
so formatted content (Word/Gmail tables, bold, underline) can be delivered
intact instead of retyped.
"""

import re

from core import background as _bg


def extract_html_fragment(payload: bytes):
    """Slices the fragment out of an 'HTML Format' envelope (byte offsets).

    Returns the decoded fragment string, or None if the envelope is bad.
    """
    if not payload or len(payload) < 105:
        return None
    try:
        head = payload[:200].decode('utf-8', errors='strict')
        start = re.search(r'StartFragment:(\d+)', head)
        end = re.search(r'EndFragment:(\d+)', head)
        if not start or not end:
            return None
        frag = payload[int(start.group(1)):int(end.group(1))]
        return frag.decode('utf-8')
    except (ValueError, UnicodeDecodeError, IndexError):
        return None


def read_clipboard_html():
    """Raw HTML fragment currently on the clipboard, or None.

    Windows-only in practice (needs the clipboard APIs); returns None
    anywhere the clipboard can't be opened.
    """
    try:
        user32 = _bg._user32()
        cf_html = user32.RegisterClipboardFormatW("HTML Format")
    except Exception:
        return None

    def _read(u32):
        try:
            handle = u32.GetClipboardData(cf_html)
        except Exception:
            return None
        if not handle:
            return None
        try:
            return _bg._handle_to_bytes(handle)
        except Exception:
            return None

    try:
        raw = _bg._with_clipboard(_read)
    except Exception:
        return None
    if not raw:
        return None
    return extract_html_fragment(raw)


def read_clipboard_text():
    """Plain unicode text currently on the clipboard, or None."""
    def _read(u32):
        try:
            handle = u32.GetClipboardData(_bg.CF_UNICODETEXT)
        except Exception:
            return None
        if not handle:
            return None
        try:
            raw = _bg._handle_to_bytes(handle)
        except Exception:
            return None
        try:
            return raw.decode('utf-16-le').rstrip('\x00')
        except Exception:
            return None

    try:
        return _bg._with_clipboard(_read)
    except Exception:
        return None


def describe_clipboard() -> dict:
    """What formats are available: {'text': bool, 'html': bool}."""
    return {'text': read_clipboard_text() is not None,
            'html': read_clipboard_html() is not None}
