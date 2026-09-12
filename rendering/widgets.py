"""Reusable console UI primitives shared by every menu and panel.

Before this module each `draw_*_menu` function open-coded its own centering
math, frame call, selection color, scroll clamping and footer hint string.
That is why the menus drifted apart visually and why fixing anything meant
fourteen near-identical edits.

The geometry helpers here are deliberately usable *outside* the renderer:
`centered_menu()` and the `ListRegion` it hands back are what let the input
handlers in main.py turn a mouse position into a row index without
duplicating (and eventually mis-copying) the layout arithmetic.
"""

from __future__ import annotations

from typing import NamedTuple

from config import MAP_WIDTH, SCREEN_HEIGHT
from rendering import ui_theme as theme

# Box-drawing glyphs for the emphasized border drawn over a focused panel.
# All six are in CP437 and therefore in the bundled tilesheet's charmap.
_DOUBLE_HORIZONTAL = "═"
_DOUBLE_VERTICAL = "║"
_DOUBLE_TOP_LEFT = "╔"
_DOUBLE_TOP_RIGHT = "╗"
_DOUBLE_BOTTOM_LEFT = "╚"
_DOUBLE_BOTTOM_RIGHT = "╝"


class ListRegion(NamedTuple):
    """The rectangle a scrolling list's rows occupy.

    `height` is the number of rows visible at once, not the total number of
    entries - callers pair it with a scroll offset to map screen rows to
    list indices in both directions.
    """

    x: int
    y: int
    width: int
    height: int

    def index_at(self, mouse_x, mouse_y, scroll_offset, total):
        """List index under a mouse position, or None if it isn't over a row.

        Returns None rather than a clamped index so a click in the padding
        below a short list does nothing instead of re-selecting the last
        entry.
        """
        if mouse_x is None or mouse_y is None:
            return None
        if not (self.x <= mouse_x < self.x + self.width):
            return None
        if not (self.y <= mouse_y < self.y + self.height):
            return None
        index = int(scroll_offset) + (int(mouse_y) - self.y)
        return index if 0 <= index < int(total) else None


class MenuGeometry(NamedTuple):
    """Position and size of a centered menu frame, plus its content box."""

    x: int
    y: int
    width: int
    height: int

    @property
    def inner_x(self):
        return self.x + theme.PAD_X

    @property
    def inner_y(self):
        return self.y + theme.PAD_TOP

    @property
    def inner_width(self):
        return self.width - (theme.PAD_X * 2)

    @property
    def hint_row(self):
        """Row reserved for the key-hint footer, just inside the bottom border."""
        return self.y + self.height - 2

    def list_region(self, *, top_offset=0, bottom_margin=2, width=None):
        """Carve out the row area for a scrolling list inside this menu.

        `top_offset` is measured from the first content row, so a menu with
        a two-line header passes top_offset=2. `bottom_margin` reserves rows
        for the hint footer.
        """
        top = self.inner_y + int(top_offset)
        height = max(0, (self.y + self.height - int(bottom_margin)) - top)
        return ListRegion(
            x=self.inner_x,
            y=top,
            width=int(width) if width is not None else self.inner_width,
            height=height,
        )


def centered_menu(width, height):
    """Center a menu over the world view.

    Menus are centered on the map area rather than the whole screen so they
    don't drift under the status column on the right.
    """
    width = max(4, min(int(width), MAP_WIDTH))
    height = max(3, min(int(height), SCREEN_HEIGHT))
    return MenuGeometry(
        x=(MAP_WIDTH - width) // 2,
        y=(SCREEN_HEIGHT - height) // 2,
        width=width,
        height=height,
    )


def panel(console, x, y, width, height, *, title=None, focused=False, bg=None, fg=None):
    """Draw a framed, cleared panel.

    Focus is an accent-color border; all surfaces share the same thin frame.
    Print captions explicitly because tcod's deprecated title argument adds
    color controls that interfere with the shared palette.
    """
    frame_fg = fg if fg is not None else (theme.FRAME_FOCUSED if focused else theme.FRAME)
    background = bg if bg is not None else theme.PANEL_BG
    console.draw_frame(
        x=x, y=y, width=width, height=height,
        clear=True, fg=frame_fg, bg=background,
    )
    if title and width > 4:
        caption = " " + str(title).strip()[:width - 4] + " "
        console.print(x=x + (width - len(caption)) // 2, y=y,
                      string=caption, fg=theme.HEADING, bg=background)


def _overprint_double_border(console, x, y, width, height, fg, bg, title):
    """Redraw a panel's border cells with double-line glyphs.

    The title occupies part of the top edge, so that span is skipped to
    avoid painting over the text tcod already placed there.
    """
    if width < 2 or height < 2:
        return
    title_span = 0
    if title:
        # tcod centers the title on the top border with a space either side.
        title_span = min(width - 2, len(str(title)) + 2)
    title_start = x + max(1, (width - title_span) // 2)
    title_end = title_start + title_span

    for offset in range(1, width - 1):
        column = x + offset
        if not (title_start <= column < title_end):
            console.print(x=column, y=y, string=_DOUBLE_HORIZONTAL, fg=fg, bg=bg)
        console.print(x=column, y=y + height - 1, string=_DOUBLE_HORIZONTAL, fg=fg, bg=bg)
    for offset in range(1, height - 1):
        console.print(x=x, y=y + offset, string=_DOUBLE_VERTICAL, fg=fg, bg=bg)
        console.print(x=x + width - 1, y=y + offset, string=_DOUBLE_VERTICAL, fg=fg, bg=bg)

    console.print(x=x, y=y, string=_DOUBLE_TOP_LEFT, fg=fg, bg=bg)
    console.print(x=x + width - 1, y=y, string=_DOUBLE_TOP_RIGHT, fg=fg, bg=bg)
    console.print(x=x, y=y + height - 1, string=_DOUBLE_BOTTOM_LEFT, fg=fg, bg=bg)
    console.print(x=x + width - 1, y=y + height - 1, string=_DOUBLE_BOTTOM_RIGHT, fg=fg, bg=bg)


def heading(console, x, y, text, *, color=None):
    """Draw a section heading. Returns the next free row."""
    console.print(x=x, y=y, string=str(text), fg=color if color is not None else theme.HEADING)
    return y + 1


def text_line(console, x, y, text, *, color=None, width=None):
    """Draw one clipped line of body text. Returns the next free row."""
    string = str(text)
    if width is not None:
        string = string[: max(0, int(width))]
    console.print(x=x, y=y, string=string, fg=color if color is not None else theme.TEXT)
    return y + 1


def field(console, x, y, label, value, *, width=None, value_color=None):
    """Draw a "Label: value" pair with the label muted and the value bright."""
    label_text = f"{label}: "
    console.print(x=x, y=y, string=label_text, fg=theme.TEXT_MUTED)
    value_text = str(value)
    if width is not None:
        value_text = value_text[: max(0, int(width) - len(label_text))]
    console.print(
        x=x + len(label_text), y=y, string=value_text,
        fg=value_color if value_color is not None else theme.TEXT,
    )
    return y + 1


def rule(console, x, y, width, *, color=None):
    """Draw a horizontal separator line. Returns the next free row."""
    console.print(
        x=x, y=y, string=theme.RULE * max(0, int(width)),
        fg=color if color is not None else theme.FRAME,
    )
    return y + 1


def meter(console, x, y, width, label, value, maximum, colors, *, show_numbers=True):
    """Draw a labelled bar as solid blocks.

    `colors` is a (fill, track) pair from ui_theme. Both halves are drawn
    with the same full-block glyph in different colors, so the bar reads as
    one continuous shape - the old '#'/'-' rendering broke it into
    punctuation that was hard to judge at a glance.

    A non-zero value always keeps at least one filled cell, so "nearly dead"
    never renders identically to "dead".
    """
    maximum = max(1, int(maximum))
    value = max(0, int(value))
    readout = f"{value}/{maximum}" if show_numbers else ""
    label_text = f"{label} " if label else ""

    track_width = int(width) - len(label_text) - len(readout)
    if show_numbers:
        track_width -= 1  # gap between bar and numbers
    track_width = max(1, track_width)

    ratio = min(1.0, value / maximum)
    filled = int(track_width * ratio)
    if value > 0:
        filled = max(1, filled)
    filled = min(track_width, filled)

    fill_color, track_color = colors
    bar_x = x + len(label_text)
    if label_text:
        console.print(x=x, y=y, string=label_text, fg=theme.TEXT_DIM)
    if filled > 0:
        console.print(x=bar_x, y=y, string=theme.BAR_CELL * filled, fg=fill_color)
    if filled < track_width:
        console.print(
            x=bar_x + filled, y=y,
            string=theme.BAR_CELL * (track_width - filled), fg=track_color,
        )
    if show_numbers:
        console.print(x=x + int(width) - len(readout), y=y, string=readout, fg=theme.TEXT)
    return y + 1


def hint_bar(console, x, y, width, hints, *, color=None):
    """Draw a footer of "KEY action" pairs, e.g. [("Enter", "confirm")].

    Keys are drawn in the heading color and actions muted, so the bar scans
    as a key legend rather than as a sentence.
    """
    cursor = x
    limit = x + int(width)
    for index, (key, action) in enumerate(hints):
        segment = f"{key} {action}"
        separator = "   " if index else ""
        if cursor + len(separator) + len(segment) > limit:
            break
        if separator:
            console.print(x=cursor, y=y, string=separator, fg=theme.TEXT_MUTED)
            cursor += len(separator)
        console.print(x=cursor, y=y, string=str(key), fg=color if color is not None else theme.HEADING)
        cursor += len(str(key))
        console.print(x=cursor, y=y, string=f" {action}", fg=theme.TEXT_MUTED)
        cursor += len(action) + 1
    return y + 1


def clamp_scroll(selected_index, scroll_offset, visible_rows):
    """Scroll just far enough to keep the selected row on screen.

    This exact block was copy-pasted into six menus; each copy was a chance
    to get an off-by-one wrong in only one of them.
    """
    visible_rows = max(1, int(visible_rows))
    selected_index = max(0, int(selected_index))
    scroll_offset = max(0, int(scroll_offset))
    if selected_index < scroll_offset:
        return selected_index
    if selected_index >= scroll_offset + visible_rows:
        return selected_index - visible_rows + 1
    return scroll_offset


def scrollbar(console, x, y, height, *, offset, total, visible):
    """Draw a vertical scrollbar, or nothing if everything already fits."""
    height = max(0, int(height))
    total = int(total)
    visible = max(1, int(visible))
    if height <= 0 or total <= visible:
        return

    max_offset = max(1, total - visible)
    ratio = min(1.0, max(0, int(offset)) / max_offset)
    thumb_y = y + int(round(ratio * (height - 1)))
    for row in range(height):
        row_y = y + row
        is_thumb = row_y == thumb_y
        console.print(
            x=x, y=row_y,
            string=theme.SCROLL_THUMB if is_thumb else theme.SCROLL_TRACK,
            fg=theme.TEXT_DIM if is_thumb else theme.TEXT_DISABLED,
        )


class Row(NamedTuple):
    """One entry in a `list_view`.

    `icon_key` names an item whose sprite is drawn to the left of the text
    (see console_renderer._draw_item_icon); `enabled=False` greys the row
    out for things like recipes the player can't afford.
    """

    text: str
    color: object = None
    enabled: bool = True
    icon_key: object = None


def list_view(
    console,
    region,
    rows,
    *,
    selected_index=0,
    scroll_offset=0,
    hovered_index=None,
    icon_drawer=None,
    show_cursor=True,
    show_scrollbar=True,
    preserve_row_colors=False,
):
    """Draw a scrolling, selectable list inside `region`.

    Pass `selected_index=None` for a list the player scrolls but doesn't
    pick from (the inventory readout, say). That suppresses the follow-the-
    selection scrolling, which would otherwise snap such a list back to the
    top on every frame.

    Returns the (possibly adjusted) scroll offset so the caller can persist
    it back into its menu context.
    """
    total = len(rows)
    if selected_index is not None:
        scroll_offset = clamp_scroll(selected_index, scroll_offset, region.height)
    scroll_offset = max(0, min(int(scroll_offset), max(0, total - region.height)))

    text_offset = 2 if show_cursor else 0
    for screen_row in range(region.height):
        index = scroll_offset + screen_row
        if index >= total:
            break
        row = rows[index]
        if not isinstance(row, Row):
            row = Row(text=str(row))

        is_selected = index == selected_index
        color = theme.row_color(
            selected=is_selected,
            hovered=hovered_index == index,
            enabled=row.enabled,
            base=row.color,
        )
        if preserve_row_colors and row.color is not None:
            color = row.color
        row_y = region.y + screen_row

        background = (theme.SELECTION_BG if is_selected else
                      theme.HOVER_BG if hovered_index == index else None)
        if background is not None:
            console.print(x=region.x, y=row_y, string=" " * region.width,
                          fg=color, bg=background)

        if show_cursor and is_selected:
            console.print(x=region.x, y=row_y, string=theme.SELECT_CURSOR, fg=color)

        text_x = region.x + text_offset
        icon_width = 0
        if row.icon_key is not None and icon_drawer is not None:
            if icon_drawer(console, text_x, row_y, row.icon_key):
                icon_width = 2

        console.print(
            x=text_x + icon_width,
            y=row_y,
            string=str(row.text)[: max(0, region.width - text_offset - icon_width)],
            fg=color,
        )

    if show_scrollbar:
        scrollbar(
            console,
            region.x + region.width,
            region.y,
            region.height,
            offset=scroll_offset,
            total=total,
            visible=region.height,
        )

    return scroll_offset


def empty_state(console, region, message):
    """Draw the placeholder text shown when a list has no entries."""
    console.print(
        x=region.x, y=region.y,
        string=str(message)[: max(0, region.width)],
        fg=theme.TEXT_MUTED,
    )
