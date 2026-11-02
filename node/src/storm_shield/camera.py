"""The picture a Camera draws: a labelled scene of the water at its own spot.

It is a drawing, not footage, and it holds nothing that says where the Camera is.
"""

STAFF_TOP_M = 6.0
_WIDTH, _HEIGHT = 320, 200
_GROUND_Y = 150
_STAFF_X = 270
_STAFF_TOP_Y = 30


def _y_at(metres: float) -> float:
    return _GROUND_Y - (_GROUND_Y - _STAFF_TOP_Y) * metres / STAFF_TOP_M


def draw_picture(depth_m: float | None) -> str:
    """An SVG of the water `depth_m` deep against a depth staff; None draws dry ground."""
    if depth_m is None:
        water = ""
        caption = "DRY"
    else:
        shown = min(max(depth_m, 0.0), STAFF_TOP_M)
        top = _y_at(shown)
        water = (
            f'<rect x="0" y="{top:.1f}" width="{_WIDTH}" height="{_GROUND_Y - top:.1f}" '
            'fill="#3b82c4" opacity="0.8"/>'
            f'<line x1="0" y1="{top:.1f}" x2="{_WIDTH}" y2="{top:.1f}" stroke="#e8f3ff" '
            'stroke-width="2"/>'
        )
        caption = f"WATER {depth_m:.1f} m"
    ticks = "".join(
        f'<line x1="{_STAFF_X - 8}" y1="{_y_at(metre):.1f}" x2="{_STAFF_X + 8}" '
        f'y2="{_y_at(metre):.1f}" stroke="#222"/>'
        for metre in range(int(STAFF_TOP_M) + 1)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_WIDTH} {_HEIGHT}" '
        'role="img" aria-label="Simulated camera picture">'
        f'<rect width="{_WIDTH}" height="{_HEIGHT}" fill="#cfe3f2"/>'
        f'<rect y="{_GROUND_Y}" width="{_WIDTH}" height="{_HEIGHT - _GROUND_Y}" fill="#8a7550"/>'
        f"{water}"
        f'<rect x="{_STAFF_X - 3}" y="{_STAFF_TOP_Y}" width="6" '
        f'height="{_GROUND_Y - _STAFF_TOP_Y}" fill="#f4f4f4" stroke="#222"/>'
        f"{ticks}"
        '<text x="8" y="22" font-family="sans-serif" font-size="16" font-weight="bold" '
        'fill="#b00020">SIMULATED</text>'
        f'<text x="8" y="188" font-family="sans-serif" font-size="14" fill="#111">{caption}</text>'
        "</svg>"
    )
