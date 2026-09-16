"""
uia.py — screen reading via UI Automation (Windows only).

Converts live controls into plain dict trees FIRST, so every decision
(find, render, click-target math) runs on data and is fully unit-testable.
The COM layer stays thin and every access is guarded: flaky controls
return partial trees, never exceptions.
"""

try:
    import uiautomation as _uia
    _UIA_IMPORT_ERROR = None
except Exception as e:  # optional dependency: any failure means unavailable
    _uia = None
    _UIA_IMPORT_ERROR = e

if _uia is not None:
    # The library logs to @AutomationLog.txt in the working dir by default;
    # redirect to the null device so users' folders stay clean.
    try:
        import os as _os
        _uia.Logger.SetLogFile('NUL' if _os.name == 'nt' else _os.devnull)
    except Exception:
        pass


def available() -> bool:
    return _uia is not None


def _require_uia():
    if _uia is None:
        raise RuntimeError(
            "screen reading needs Windows + the uiautomation package "
            f"(pip install uiautomation): {_UIA_IMPORT_ERROR}")
    return _uia


def rect_center(rect) -> tuple:
    """Center of an (x, y, w, h) rect dict."""
    return (rect['x'] + rect['w'] // 2, rect['y'] + rect['h'] // 2)


def _element_to_dict(el, depth: int, budget: list) -> dict:
    """One control -> plain dict. Never raises (partial data on failure)."""
    node = {'name': '', 'control': '?', 'rect': None, 'value': None, 'children': []}
    if budget[0] <= 0 or depth < 0:
        return node
    budget[0] -= 1
    try:
        node['name'] = (el.Name or '')[:200]
    except Exception:
        pass
    try:
        node['control'] = el.ControlTypeName or '?'
    except Exception:
        pass
    try:
        r = el.BoundingRectangle
        node['rect'] = {'x': int(r.left), 'y': int(r.top),
                        'w': int(r.width()), 'h': int(r.height())}
    except Exception:
        pass
    if node['control'] in ('EditControl', 'TextControl', 'ComboBoxControl',
                           'DocumentControl'):
        try:
            node['value'] = (el.GetValuePattern().Value or '')[:2000]
        except Exception:
            pass
    if depth > 0:
        try:
            kids = el.GetChildren() or []
        except Exception:
            kids = []
        for kid in kids[:40]:
            node['children'].append(_element_to_dict(kid, depth - 1, budget))
    return node


def _root_for(hwnd):
    uia = _require_uia()
    if hwnd is None:
        hwnd = uia.GetForegroundWindow()
    return uia.ControlFromHandle(hwnd)


def dump_tree(hwnd=None, depth: int = 3, max_nodes: int = 200) -> list:
    """Top-level control forest as plain dicts (empty list on any failure)."""
    try:
        root = _root_for(hwnd)
        title = {'name': '', 'control': 'Window', 'rect': None,
                 'value': None, 'children': []}
        try:
            title['name'] = (root.Name or '')[:200]
        except Exception:
            pass
        try:
            kids = root.GetChildren() or []
        except Exception:
            kids = []
        budget = [max_nodes]
        for kid in kids[:40]:
            title['children'].append(_element_to_dict(kid, depth - 1, budget))
        return [title]
    except Exception:
        return []


def find_in_tree(nodes: list, text: str):
    """First node whose name contains text (case-insensitive), depth-first."""
    needle = (text or '').lower()
    if not needle:
        return None
    stack = list(nodes)
    while stack:
        node = stack.pop(0)
        if needle in (node.get('name') or '').lower():
            return node
        stack = list(node.get('children') or []) + stack
    return None


def find_on_screen(text: str, hwnd=None, depth: int = 4):
    """Dump + find in one call. Returns node dict or None."""
    return find_in_tree(dump_tree(hwnd, depth=depth), text)


def tree_to_text(nodes: list, indent: int = 0) -> str:
    """Renders a tree as indented lines for model context."""
    lines = []
    for node in nodes:
        name = node.get('name') or ''
        label = f"{node.get('control', '?')}: {name}".rstrip(': ').rstrip()
        if node.get('value'):
            label += f" = {node['value'][:120]}"
        lines.append('  ' * indent + label)
        kids = node.get('children') or []
        if kids:
            lines.append(tree_to_text(kids, indent + 1))
    return '\n'.join(lines)
