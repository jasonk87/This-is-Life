"""A minimal block-letter font for the main menu title.

The title screen is the first thing a player sees, and a single line of
plain text in the same size as everything else doesn't announce anything.
This renders short strings as 5-row block letters built from the same full
block glyph the meters use, so it needs no extra tileset support.

Only the letters actually used by the game's title are defined; anything
else renders as blank space rather than raising, so changing the title text
degrades to a gap instead of crashing the menu.
"""

from __future__ import annotations

from rendering import ui_theme as theme

GLYPH_HEIGHT = 5
GLYPH_WIDTH = 5
LETTER_SPACING = 1
WORD_SPACING = 3

# 'X' marks a filled cell. Kept as literal art so the shapes are editable
# by eye rather than by decoding a bitmask.
_GLYPHS = {
    "T": (
        "XXXXX",
        "  X  ",
        "  X  ",
        "  X  ",
        "  X  ",
    ),
    "H": (
        "X   X",
        "X   X",
        "XXXXX",
        "X   X",
        "X   X",
    ),
    "I": (
        "XXXXX",
        "  X  ",
        "  X  ",
        "  X  ",
        "XXXXX",
    ),
    "S": (
        "XXXXX",
        "X    ",
        "XXXXX",
        "    X",
        "XXXXX",
    ),
    "L": (
        "X    ",
        "X    ",
        "X    ",
        "X    ",
        "XXXXX",
    ),
    "F": (
        "XXXXX",
        "X    ",
        "XXXX ",
        "X    ",
        "X    ",
    ),
    "E": (
        "XXXXX",
        "X    ",
        "XXXX ",
        "X    ",
        "XXXXX",
    ),
}


def render_lines(text, *, fill=theme.BAR_CELL):
    """Render `text` as GLYPH_HEIGHT strings of block characters."""
    rows = [""] * GLYPH_HEIGHT
    for index, char in enumerate(str(text).upper()):
        if char == " ":
            for row in range(GLYPH_HEIGHT):
                rows[row] += " " * WORD_SPACING
            continue

        glyph = _GLYPHS.get(char)
        separator = " " * LETTER_SPACING if index else ""
        for row in range(GLYPH_HEIGHT):
            cells = glyph[row] if glyph else " " * GLYPH_WIDTH
            rows[row] += separator + cells.replace("X", fill)
    return rows


def measure(text):
    """Width in console cells of `text` rendered as block letters."""
    lines = render_lines(text)
    return max((len(line) for line in lines), default=0)


def draw(console, center_x, y, text, *, fg=theme.HEADING, shadow_fg=None):
    """Draw block-letter `text` horizontally centered on `center_x`.

    Passing `shadow_fg` stamps a one-cell offset copy underneath first,
    which gives the letters some weight against a dark background.
    """
    lines = render_lines(text)
    width = max((len(line) for line in lines), default=0)
    x = max(0, int(center_x) - (width // 2))

    if shadow_fg is not None:
        for row, line in enumerate(lines):
            console.print(x=x + 1, y=y + row + 1, string=line, fg=shadow_fg)
    for row, line in enumerate(lines):
        console.print(x=x, y=y + row, string=line, fg=fg)
    return y + GLYPH_HEIGHT
