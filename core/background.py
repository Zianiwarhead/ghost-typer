"""
background.py — experimental focus-free delivery (Windows only).

Types/pastes into a background window WITHOUT focusing it, so you can keep
working elsewhere. Two delivery modes:

  paste (default)  HTML/text payload -> clipboard -> WM_PASTE to the target.
                   Instant, keeps bold/italic/tables. Clipboard is borrowed
                   for a split second (text content saved + restored).
  human            paced WM_CHAR keystrokes (+ Tab/Enter nav keys) straight
                   into the window's message queue. Plain text only, slower,
                   but never touches your clipboard.

Honest limits (platform-enforced, not fixable here):
  - Works with classic edit controls: Notepad, WordPad, Word's document pane.
  - Does NOT work with browsers, Discord, VS Code, or any Electron/Chromium
    app — they don't honor WM_PASTE on the top-level window. Use normal
    (focused) mode for those.
  - The caret must already be where you want text (click it once first).
    Minimized windows may silently swallow the paste.
  - Only BMP characters travel via WM_CHAR; astral chars become '?'.

All win32 imports are lazy so this module imports everywhere; functions
raise RuntimeError("background mode needs Windows + pywin32") otherwise.
"""

import ctypes
import html as _html
import time

CF_TEXT = 1
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def available() -> bool:
    try:
        import win32gui  # noqa: F401
        return True
    except ImportError:
        return False


def _require_win32():
    try:
        import win32con
        import win32gui
    except ImportError as e:
        raise RuntimeError("background mode needs Windows + pywin32") from e
    return win32gui, win32con


def _user32():
    user32 = ctypes.windll.user32
    user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
    user32.OpenClipboard.restype = ctypes.wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.wintypes.BOOL
    user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]
    user32.GetClipboardData.restype = ctypes.wintypes.HANDLE
    user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.wintypes.HANDLE]
    user32.SetClipboardData.restype = ctypes.wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [ctypes.wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = ctypes.wintypes.UINT
    return user32


def _kernel32():
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = ctypes.wintypes.BOOL
    kernel32.GlobalSize.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    return kernel32


def _with_clipboard(fn, retries: int = 8):
    """Runs fn() with the clipboard open (retries: someone else may hold it)."""
    user32 = _user32()
    last_err = None
    for _ in range(retries):
        try:
            if user32.OpenClipboard(None):
                try:
                    return fn(user32)
                finally:
                    user32.CloseClipboard()
        except Exception as e:
            last_err = e
        time.sleep(0.05)
    raise RuntimeError(f"could not open clipboard: {last_err}")


# ------------------------------------------------------------------ #
#  Window targeting                                                    #
# ------------------------------------------------------------------ #

EDIT_CLASSES = ('Edit', 'RichEdit20W', 'RICHEDIT50W', 'RICHEDIT60W', '_WwG')

# Apps whose windows don't honor background messages: Chromium browsers
# and Electron/chat apps paint their own controls and drop WM_CHAR/WM_PASTE
# posted from outside. These need focused typing, not --bg.
WEB_APP_KEYWORDS = ('chrome', 'chromium', 'edge', 'firefox', 'brave', 'opera',
                    'arc', 'discord', 'slack', 'teams', 'whatsapp', 'telegram',
                    'signal', 'vscode', 'visual studio code', 'electron', 'spotify')


def is_web_target(*texts) -> bool:
    """True if any text names a browser/chat/Electron app."""
    for text in texts:
        if not text:
            continue
        lowered = str(text).lower()
        if any(kw in lowered for kw in WEB_APP_KEYWORDS):
            return True
    return False


def web_target_guidance(title: str) -> str:
    return (f"'{title}' looks like a browser/chat app — background delivery "
            "can't reach it (Chromium/Electron drop window messages). Drop --bg "
            "and use focused typing instead: run without --bg and click the "
            "field during the countdown.")


def find_windows(keyword: str) -> list:
    """All visible top-level windows whose title contains keyword."""
    win32gui, _ = _require_win32()
    found = []

    def cb(hwnd, _extra):
        try:
            if (keyword.lower() in win32gui.GetWindowText(hwnd).lower()
                    and win32gui.IsWindowVisible(hwnd)):
                found.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return found


def find_window(keyword: str):
    """First visible window matching keyword (None if none)."""
    wins = find_windows(keyword)
    return wins[0] if wins else None


def find_window_by_pid(pid: int):
    """Visible top-level window owned by pid (None if none)."""
    win32gui, _ = _require_win32()
    try:
        import win32process
    except ImportError as e:
        raise RuntimeError("background mode needs Windows + pywin32") from e
    found = []

    def cb(hwnd, _extra):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid == pid and win32gui.IsWindowVisible(hwnd):
                found.append(hwnd)
                return False
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def find_edit_child(hwnd):
    """Deepest-first visible edit-like child, else the window itself."""
    win32gui, _ = _require_win32()
    hits = []

    def cb(child, _extra):
        try:
            if win32gui.GetClassName(child) in EDIT_CLASSES and win32gui.IsWindowVisible(child):
                hits.append(child)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumChildWindows(hwnd, cb, None)
    except Exception:
        pass
    return hits[-1] if hits else hwnd


CONSOLE_CLASSES = ('ConsoleWindowClass', 'WindowsTerminal', 'CASCADIA_HOSTING_WINDOW_CLASS')


def _is_console(hwnd) -> bool:
    """True for terminal windows (their titles echo the command line, so a
    --bg keyword almost always matches your own shell by accident)."""
    win32gui, _ = _require_win32()
    try:
        return win32gui.GetClassName(hwnd) in CONSOLE_CLASSES
    except Exception:
        return False


def resolve_target(keyword: str | None = None, pid: int | None = None):
    """(top_hwnd, edit_hwnd, title) for delivery.

    Keyword matching prefers an exact title, then non-console windows
    (consoles match nearly everything since titles echo the command line);
    ambiguous partial matches raise listing the candidates (never silently
    pick one). pid selects exactly.
    """
    win32gui, _ = _require_win32()
    if pid is not None:
        top = find_window_by_pid(pid)
        if not top:
            raise ValueError(f"No visible window owned by pid {pid}")
    else:
        cands = find_windows(keyword or "")
        exact = [h for h in cands
                 if win32gui.GetWindowText(h).lower() == (keyword or "").lower()]
        cands = exact[:1] if exact else cands
        if not cands:
            raise ValueError(f"No visible window matches {keyword!r}")
        if len(cands) > 1:
            real = [h for h in cands if not _is_console(h)]
            cands = real or cands
        if len(cands) > 1:
            shown = ", ".join(repr(win32gui.GetWindowText(h)) for h in cands[:5])
            raise ValueError(f"{len(cands)} windows match {keyword!r} ({shown}) — "
                             "be more specific or use --bg-pid")
        top = cands[0]
    edit = find_edit_child(top)
    try:
        title = win32gui.GetWindowText(top)
    except Exception:
        title = keyword or str(pid)
    return top, edit, title


# ------------------------------------------------------------------ #
#  Clipboard payloads (byte-exact offsets!)                            #
# ------------------------------------------------------------------ #

def build_html_clipboard_payload(fragment_html: str) -> bytes:
    """Wraps fragment HTML in the Windows 'HTML Format' envelope.

    Offsets are BYTE offsets into the final utf-8 payload (char counts
    break on any non-ASCII text) and the header is fixed at 105 bytes via
    zero-padded fields, so offsets stay valid after substitution.
    """
    body = ("<html><body>\n<!--StartFragment-->"
            + fragment_html + "<!--EndFragment-->\n</body></html>")
    body_bytes = body.encode('utf-8')
    marker = b"<!--StartFragment-->"
    start_frag = body_bytes.index(marker) + len(marker)
    end_frag = body_bytes.index(b"<!--EndFragment-->")
    header = (f"Version:0.9\r\nStartHTML:{105:010d}\r\nEndHTML:{105 + len(body_bytes):010d}\r\n"
              f"StartFragment:{105 + start_frag:010d}\r\nEndFragment:{105 + end_frag:010d}\r\n")
    assert len(header.encode('utf-8')) == 105
    return header.encode('utf-8') + body_bytes


def _bytes_to_handle(data: bytes):
    kernel32 = _kernel32()
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data) or 1)
    if not handle:
        raise RuntimeError("GlobalAlloc failed")
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    return handle


def _handle_to_bytes(handle) -> bytes:
    kernel32 = _kernel32()
    ptr = kernel32.GlobalLock(handle)
    try:
        return ctypes.string_at(ptr, kernel32.GlobalSize(handle))
    finally:
        kernel32.GlobalUnlock(handle)


def save_clipboard() -> dict:
    """Best-effort save of text clipboard content (files/objects not kept)."""
    saved = {}

    def _read(u32):
        for fmt in (CF_UNICODETEXT, CF_TEXT):
            try:
                handle = u32.GetClipboardData(fmt)
                if handle:
                    saved[fmt] = _handle_to_bytes(handle)
            except Exception:
                pass

    try:
        _with_clipboard(_read)
    except Exception:
        pass
    return saved


def restore_clipboard(saved: dict) -> None:
    if not saved:
        return

    def _write(u32):
        u32.EmptyClipboard()
        for fmt, data in saved.items():
            try:
                u32.SetClipboardData(fmt, _bytes_to_handle(data))
            except Exception:
                pass

    try:
        _with_clipboard(_write)
    except Exception:
        pass


def set_clipboard_html(fragment_html: str) -> None:
    user32 = _user32()
    payload = build_html_clipboard_payload(fragment_html)
    cf_html = user32.RegisterClipboardFormatW("HTML Format")

    def _write(u32):
        u32.EmptyClipboard()
        u32.SetClipboardData(cf_html, _bytes_to_handle(payload))

    _with_clipboard(_write)


def set_clipboard_text(text: str) -> None:
    def _write(u32):
        u32.EmptyClipboard()
        u32.SetClipboardData(CF_UNICODETEXT, _bytes_to_handle((text + '\x00').encode('utf-16-le')))

    _with_clipboard(_write)


# ------------------------------------------------------------------ #
#  Delivery                                                            #
# ------------------------------------------------------------------ #

def paste_to_hwnd(hwnd) -> None:
    """Posts WM_PASTE (async — never blocks on the target thread)."""
    win32gui, win32con = _require_win32()
    win32gui.PostMessage(hwnd, win32con.WM_PASTE, 0, 0)


def send_char(hwnd, ch: str) -> None:
    """Posts one WM_CHAR ('\\n' -> CR, astral chars -> '?')."""
    win32gui, win32con = _require_win32()
    if ch == '\n':
        ch = '\r'
    code = ord(ch)
    if code > 0xFFFF:
        code = ord('?')
    win32gui.PostMessage(hwnd, win32con.WM_CHAR, code, 0)


def send_key(hwnd, vk: int) -> None:
    """Posts key down+up (Tab/Enter/arrows for table navigation)."""
    win32gui, win32con = _require_win32()
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)


def _send_timeout_ok(hwnd) -> bool:
    """True if the window's thread answers a null message within 100ms."""
    user32 = ctypes.windll.user32
    user32.SendMessageTimeoutW.argtypes = [
        ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.c_size_t,
        ctypes.c_ssize_t, ctypes.wintypes.UINT, ctypes.wintypes.UINT,
        ctypes.POINTER(ctypes.c_ulong)]
    user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    result = ctypes.c_ulong()
    answered = user32.SendMessageTimeoutW(
        hwnd, 0, 0, 0, 0x0002, 100, ctypes.byref(result))
    return bool(answered)


def verify_window_alive(hwnd) -> bool:
    """True if the window exists and its thread answers within 100ms.

    Fail-open on unexpected errors (a posted message to a dead window is
    simply dropped by the OS); IsWindow covers the actually-dead case.
    """
    win32gui, _win32con = _require_win32()
    try:
        if not win32gui.IsWindow(hwnd):
            return False
    except Exception:
        return False
    try:
        return _send_timeout_ok(hwnd)
    except Exception:
        return True


# ------------------------------------------------------------------ #
#  Markup -> HTML (reuses our richtext tokens)                         #
# ------------------------------------------------------------------ #

def markup_to_html(markup: str) -> str:
    """Converts **bold**/*italic*/__underline__/# headings to HTML."""
    from core.richtext import parse_rich_text
    blocks: list = []
    cur: list = []
    cur_heading = None
    open_tags: list = []

    def close_inline():
        for t in reversed(open_tags):
            cur.append(f'</{t}>')
        open_tags.clear()

    def flush_block():
        nonlocal cur_heading
        if cur:
            close_inline()
            text = ''.join(cur)
            cur.clear()
            if text:
                if cur_heading is not None:
                    blocks.append(f'<h{cur_heading}>{text}</h{cur_heading}>')
                else:
                    blocks.append(f'<p>{text}</p>')
        cur_heading = None

    for tok in parse_rich_text(markup):
        kind = tok[0]
        if kind == 'text':
            parts = tok[1].split('\n')
            for j, part in enumerate(parts):
                if j:
                    flush_block()  # newline ends the block
                if part:
                    cur.append(_html.escape(part, quote=False))
        elif kind == 'fmt':
            _, name, on = tok
            tag = {'bold': 'b', 'italic': 'i', 'underline': 'u'}[name]
            if on:
                cur.append(f'<{tag}>')
                open_tags.append(tag)
            elif tag in open_tags:
                open_tags.remove(tag)
                cur.append(f'</{tag}>')
            # else: stray close (e.g. after a newline flush) — ignore
        else:  # heading apply / reset
            flush_block()
            cur_heading = tok[1]
    flush_block()
    return ''.join(blocks)


def rows_to_html_table(rows: list, theme: str | None = None, title: str = "") -> str:
    """CSV rows -> bordered HTML table (first row = header).

    theme None = legacy plain style (unchanged output); otherwise one of
    table_themes.THEMES rendered via render_themed_table.
    """
    if theme:
        from core.table_themes import render_themed_table
        headers, body = (rows[0], rows[1:]) if rows else ([], [])
        return render_themed_table(title, headers, body, theme)
    parts = [('<table border="1" cellspacing="0" cellpadding="6" '
              'style="border-collapse:collapse;font-family:sans-serif;">')]
    for ri, row in enumerate(rows):
        parts.append('<tr>')
        for cell in row:
            val = _html.escape(cell, quote=False) or '&nbsp;'
            if ri == 0:
                parts.append(f'<th style="background-color:#1a1a1a;color:#ffffff;">{val}</th>')
            else:
                parts.append(f'<td>{val}</td>')
        parts.append('</tr>')
    parts.append('</table>')
    return ''.join(parts)
