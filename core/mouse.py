"""
mouse.py — human-like cursor control (pynput-based, cross-platform).

Movement is planned as jittered multi-segment paths (pure math, seeded in
tests) and executed with variable pacing. Click targets come from UIA
element rects (see core.uia) so multiple-choice answers and buttons can be
chosen by name.
"""

import random
import time


def plan_move(x0: int, y0: int, x1: int, y1: int,
              segments: int = 3, jitter: int = 12, seed=None) -> list:
    """Jittered waypoints from (x0,y0) to (x1,y1), endpoints exact.

    A straight line screams robot; intermediate points wander perpendicular
    to the path. Deterministic under seed (tests), organic otherwise.
    """
    rng = random.Random(seed)
    dx, dy = x1 - x0, y1 - y0
    length = max(abs(dx), abs(dy), 1)
    nx, ny = -dy / length, dx / length  # perpendicular unit-ish
    points = [(x0, y0)]
    for s in range(1, segments):
        t = s / segments
        off = rng.uniform(-jitter, jitter)
        points.append((int(x0 + dx * t + nx * off), int(y0 + dy * t + ny * off)))
    points.append((x1, y1))
    return points


def _controller(ctl=None):
    if ctl is not None:
        return ctl
    from pynput.mouse import Controller
    return Controller()


def current_pos(_ctl=None) -> tuple:
    ctl = _controller(_ctl)
    return (int(ctl.position[0]), int(ctl.position[1]))


def move_human(x: int, y: int, duration: float = 0.4, _ctl=None) -> None:
    """Glides to (x, y) along a jittered path with eased pacing."""
    ctl = _controller(_ctl)
    x0, y0 = current_pos(ctl)
    points = plan_move(x0, y0, x, y)
    per = max(duration / max(len(points) - 1, 1), 0.01)
    for i, (px, py) in enumerate(points[1:], 1):
        ctl.position = (px, py)
        # Ease out: fast start, gentle landing.
        time.sleep(per * random.uniform(0.5, 1.0) * (1.6 - i / len(points)))


def click_human(x: int, y: int, button: str = 'left', _ctl=None) -> None:
    """Moves (if far) and clicks. button: left | right | double."""
    from pynput.mouse import Button
    ctl = _controller(_ctl)
    x0, y0 = current_pos(ctl)
    if abs(x - x0) + abs(y - y0) > 4:
        move_human(x, y, _ctl=ctl)
    else:
        ctl.position = (x, y)
    btn = {'left': Button.left, 'right': Button.right}.get(button, Button.left)
    time.sleep(random.uniform(0.05, 0.15))  # settle before the press
    if button == 'double':
        ctl.click(Button.left, 2)
    else:
        ctl.click(btn, 1)


def click_element(node: dict, button: str = 'left', _ctl=None) -> tuple:
    """Clicks the center of a UIA node dict. Returns the (x, y) clicked."""
    from core.uia import rect_center
    rect = node.get('rect')
    if not rect:
        raise ValueError(f"element {node.get('name')!r} has no screen rect")
    x, y = rect_center(rect)
    click_human(x, y, button=button, _ctl=_ctl)
    return (x, y)
