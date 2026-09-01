"""Single source of truth for UI colors, glyphs, and spacing.

Every menu used to carry its own literal RGB tuples, which is why "gold"
appeared as (255, 215, 0), (255, 215, 120) and (255, 255, 0) on three
different screens, and why "the selected row" was a slightly different cyan
depending on which menu you opened. Draw code should name a color from here
instead of writing a tuple inline, so a palette change is one edit rather
than fourteen.

Glyphs are restricted to the CP437/CHARMAP_TCOD range that the bundled
`dejavu16x16_gs_tc.png` tilesheet actually contains. Unicode block-eighths
(U+2588 partials like the left-seven-eighths bar) are *not* in that charmap
and render as blanks, so bars here are whole cells only.
"""

# --- Surfaces -------------------------------------------------------------
# Panels sit on top of the world view, so they need an opaque fill; the
# "deep" variant is for the always-present status column, which should read
# as part of the window chrome rather than as a popup. Tuned toward a warm,
# muted pixel-art tone so the UI reads as one canvas with the DawnLike world
# instead of a floating dark-theme overlay.
PANEL_BG = (140, 122, 95)         # warm parchment tan
PANEL_BG_DEEP = (118, 101, 78)    # deeper parchment (status chrome)
PANEL_BG_RAISED = (160, 140, 111) # lighter parchment (focused popup)
LOG_BG = (104, 89, 69)            # parchment message log

# --- Frames ---------------------------------------------------------------
FRAME = (96, 80, 61)          # dark bronze, defines panel edge on parchment
FRAME_FOCUSED = (236, 196, 108)  # warm parchment highlight

# --- Text -----------------------------------------------------------------
TEXT = (240, 232, 218)        # warm off-white (bright, high contrast on parchment)
TEXT_DIM = (96, 78, 58)       # dim brown (clearly darker than panel for legibility)
TEXT_MUTED = (112, 96, 76)    # muted brown (darker than panel for legibility)
TEXT_DISABLED = (84, 72, 58)  # disabled brown (darkest, dimmed)

# --- Semantic accents -----------------------------------------------------
HEADING = (176, 128, 48)      # section headings, menu titles, field labels (dark gold)
SELECTION = (150, 104, 40)    # the row/action the cursor is on (dark amber)
HOVER = (120, 96, 66)         # the row the mouse is over but not selected
SUCCESS = (142, 206, 130)
WARNING = (240, 176, 84)
DANGER = (230, 96, 96)
INFO = (150, 186, 226)
SOCIAL = (200, 164, 222)

# --- Item quality tiers ---------------------------------------------------
QUALITY_ORDER = ("Poor", "Normal", "Fine", "Masterwork")
QUALITY_COLORS = {
    "Poor": (150, 150, 150),
    "Normal": TEXT,
    "Fine": (110, 220, 130),
    "Masterwork": (255, 195, 60),
}

# --- Meters ---------------------------------------------------------------
# Each meter is a (fill, track) pair. The track is drawn as a solid cell in a
# dark tint of the fill rather than as a dash, so a bar reads as one
# continuous shape at a glance instead of as punctuation.
METER_HP = ((236, 92, 92), (74, 28, 28))
METER_HUNGER_OK = ((150, 210, 96), (44, 60, 30))
METER_HUNGER_WARN = ((240, 206, 92), (66, 58, 26))
METER_HUNGER_CRIT = ((236, 108, 84), (68, 32, 24))
METER_THIRST_OK = ((104, 208, 226), (28, 56, 62))
METER_THIRST_WARN = ((92, 158, 232), (26, 44, 66))
METER_THIRST_CRIT = ((104, 116, 232), (28, 30, 68))
METER_ENTITY_HP = ((236, 92, 92), (62, 24, 24))

# --- Log categories -------------------------------------------------------
# Colors keyed by the category recorded on the message itself. The renderer
# no longer guesses from message text - see engine.add_message_to_chat_log.
LOG_COLORS = {
    "combat": DANGER,
    "quest": HEADING,
    "social": INFO,
    "gain": SUCCESS,
    "warning": WARNING,
    "system": TEXT_MUTED,
    "default": (225, 225, 225),
}

# --- Glyphs (CP437-safe) --------------------------------------------------
BAR_CELL = "█"        # full block - used for both fill and track
SCROLL_THUMB = "█"
SCROLL_TRACK = "░"    # light shade
SELECT_CURSOR = ">"
BULLET = "•"
ARROW_UP = "▲"
ARROW_DOWN = "▼"
RULE = "─"            # horizontal line, for in-panel separators

# --- Spacing --------------------------------------------------------------
# Menus indent content one cell past the frame border, so text starts at
# frame_x + PAD_X and the first content row is frame_y + PAD_TOP.
PAD_X = 2
PAD_TOP = 2


def quality_color(quality):
    """Color for an item quality tier, defaulting to the Normal tier."""
    return QUALITY_COLORS.get(quality, QUALITY_COLORS["Normal"])


def log_color(category):
    """Color for a chat-log message category, defaulting to plain text."""
    return LOG_COLORS.get(category, LOG_COLORS["default"])


def row_color(*, selected=False, hovered=False, enabled=True, base=None):
    """Resolve the color of a list row from its interaction state.

    Selection wins over hover so that moving the mouse across a list never
    makes it ambiguous which row Enter would actually act on.
    """
    if selected:
        return SELECTION
    if hovered:
        return HOVER
    if not enabled:
        return TEXT_DISABLED
    return base if base is not None else TEXT
