"""
table_themes.py — themed HTML tables for background paste delivery.

Renders CSV/inline rows as styled HTML (Word/Classic RichEdit hosts).
Cell values support a small inline syntax on top of plain text:

    **bold**            <b>
    __underline__       <u>
    *italic* / _italic_ <i>   (single markers; processed after the doubles)
    [COLOR=#ff0000]x[/COLOR]  <span style="color:...">

Everything else is HTML-escaped. Pick with --theme / dashboard theme field.
"""

import html as _html
import re

THEMES = {
    "matrix": {"bg": "#0d1117", "header_bg": "#161b22",
               "text": "#58a6ff", "accent": "#238636"},
    "dracula": {"bg": "#282a36", "header_bg": "#44475a",
                "text": "#f8f8f2", "accent": "#ff79c6"},
    "steel": {"bg": "#ffffff", "header_bg": "#f6f8fa",
              "text": "#24292f", "accent": "#0969da"},
}


def format_cell(cell: str) -> str:
    """Escapes a cell, then applies the inline tags (empty -> &nbsp;)."""
    s = _html.escape(cell, quote=False)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'__(.+?)__', r'<u>\1</u>', s)
    s = re.sub(r'\*(.+?)\*', r'<i>\1</i>', s)
    # Single _italic_: avoid matching inside words (a_b) or entities (&nbsp;).
    s = re.sub(r'(?<![\w&;])_(.+?)_(?![\w;])', r'<i>\1</i>', s)
    s = re.sub(r'\[COLOR=(.+?)\](.*?)\[/COLOR\]', r'<span style="color:\1;">\2</span>', s)
    return s or '&nbsp;'


def render_themed_table(title: str, headers: list, rows: list,
                        theme_name: str = "steel") -> str:
    """Full HTML data sheet. Unknown theme names fall back to steel."""
    theme = THEMES.get(theme_name, THEMES["steel"])
    parts = ['<div style="font-family:\'Segoe UI\',sans-serif;margin:10px 0;">']
    if title:
        parts.append(f'<h3 style="color:{theme["accent"]};margin-bottom:8px;">'
                     f'{_html.escape(title, quote=False)}</h3>')
    parts.append(
        f'<table style="border-collapse:collapse;width:100%;font-size:13px;'
        f'background-color:{theme["bg"]};">'
        f'<thead><tr style="background-color:{theme["header_bg"]};'
        f'color:{theme["accent"]};">')
    for h in headers:
        parts.append(f'<th style="padding:8px 12px;border:1px solid {theme["accent"]};'
                     f'text-align:left;"><b>{_html.escape(h, quote=False)}</b></th>')
    parts.append('</tr></thead><tbody>')
    for i, row in enumerate(rows):
        row_bg = theme["header_bg"] if i % 2 == 0 else theme["bg"]
        parts.append(f'<tr style="background-color:{row_bg};color:{theme["text"]};">')
        for cell in row:
            parts.append(f'<td style="padding:6px 12px;border:1px solid {theme["accent"]};">'
                         f'{format_cell(cell)}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table></div>')
    return ''.join(parts)
