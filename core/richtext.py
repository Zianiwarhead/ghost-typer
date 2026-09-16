"""
richtext.py — lightweight markup for formatted typing (Word / Google Docs).

Supported syntax (enabled with --rich):

    **bold**            Ctrl+B around the words
    *italic* / _italic_  Ctrl+I around the words
    __underline__       Ctrl+U around the words
    # Heading           Heading 1 style (Ctrl+Alt+1)
    ## Heading          Heading 2 style (Ctrl+Alt+2)
    ### Heading         Heading 3 style (Ctrl+Alt+3)
    - item              bulleted list (app autocorrect / <ul> on paste)
    1. item             numbered list (app autocorrect / <ol> on paste)

Style resets to Normal automatically after each heading line
(Word: Ctrl+Shift+N, Docs: Ctrl+Alt+0 — see --rich-app).
Lists exit cleanly after their last item.

Unclosed markers are typed literally. Everything else types as-is.
"""

import re

# (delimiter, style name) — order matters, longest first on ties.
DELIMS = [('**', 'bold'), ('__', 'underline'), ('*', 'italic'), ('_', 'italic')]

FMT_KEYS = {'bold': 'b', 'italic': 'i', 'underline': 'u'}

HEADING_RE = re.compile(r'^(#{1,3})\s+(.*)$')
LIST_RE = re.compile(r'^(-|\d+\.)\s+(.*)$')


def _parse_inline(s: str) -> list:
    """Parses one line (no newlines) into text/fmt tokens."""
    tokens: list = []
    i = 0
    while i < len(s):
        best = None
        for d, name in DELIMS:
            p = s.find(d, i)
            if p != -1 and (best is None or p < best[0]
                            or (p == best[0] and len(d) > len(best[1]))):
                best = (p, d, name)
        if best is None:
            tokens.append(('text', s[i:]))
            break
        p, d, name = best
        q = s.find(d, p + len(d))
        if q == -1 or q == p + len(d):
            # No closer (or empty content) — emit delimiter literally.
            tokens.append(('text', s[i:p + len(d)]))
            i = p + len(d)
            continue
        if p > i:
            tokens.append(('text', s[i:p]))
        tokens.append(('fmt', name, True))
        tokens.append(('text', s[p + len(d):q]))
        tokens.append(('fmt', name, False))
        i = q + len(d)
    return tokens


def parse_rich_text(text: str) -> list:
    """Parses markup into tokens.

    Token shapes:
      ('text', str)          printable characters (newlines included)
      ('fmt', name, on)      toggle bold/italic/underline (name, bool)
      ('heading', level)     apply Heading level (1-3), or None = Normal
      ('list', kind)         open bulleted ('ul') / numbered ('ol') list,
                             or None = close list (exit cleanly)
    """
    tokens: list = []
    in_list = None
    for line in text.splitlines(keepends=True):
        body = line.removesuffix('\n')
        has_nl = line.endswith('\n')
        m = HEADING_RE.match(body)
        if m:
            if in_list is not None:
                tokens.append(('list', None))
                in_list = None
            tokens.append(('heading', len(m.group(1))))
            tokens.extend(_parse_inline(m.group(2)))
            if has_nl:
                tokens.append(('text', '\n'))
            tokens.append(('heading', None))
            continue
        lm = LIST_RE.match(body) if body.strip() else None
        if lm:
            kind = 'ol' if lm.group(1) != '-' else 'ul'
            if in_list != kind:
                if in_list is not None:
                    tokens.append(('list', None))
                tokens.append(('list', kind))
                in_list = kind
            tokens.extend(_parse_inline(lm.group(2)))
            if has_nl:
                tokens.append(('text', '\n'))
            continue
        if body.strip():
            if in_list is not None:
                tokens.append(('list', None))
                in_list = None
            tokens.extend(_parse_inline(body))
            if has_nl:
                tokens.append(('text', '\n'))
        elif has_nl:
            tokens.append(('text', '\n'))
    if in_list is not None:
        tokens.append(('list', None))
    # Merge adjacent text tokens for cleaner downstream handling.
    merged: list = []
    for tok in tokens:
        if tok[0] == 'text' and merged and merged[-1][0] == 'text':
            merged[-1] = ('text', merged[-1][1] + tok[1])
        else:
            merged.append(tok)
    return merged


def strip_rich(text: str) -> str:
    """Plain printable text (markup removed) — for estimates and spans."""
    return ''.join(t[1] for t in parse_rich_text(text) if t[0] == 'text')


def has_markup(text: str) -> bool:
    """True if the text contains any actionable markup."""
    return any(t[0] == 'fmt'
               or (t[0] == 'heading' and t[1] is not None)
               or (t[0] == 'list' and t[1] is not None)
               for t in parse_rich_text(text))
