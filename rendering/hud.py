"""Shared visible controls and their hit targets; actions stay in main.py."""
from config import MAP_WIDTH
from rendering import ui_theme as theme


def toolbar_buttons(world):
    pause = "Resume" if getattr(world, "is_paused", False) else "Pause"
    labels = [("Space", pause, "SPACE"), ("1", "1x", "N1"), ("2", "2x", "N2"),
              ("3", "4x", "N3"), ("U", "Bag", "U"), ("I", "Self", "I"),
              ("L", "Look", "L"), ("C", "Craft", "C"), ("B", "Build", "B"), ("?", "", "SLASH")]
    x = 1
    for key, label, action in labels:
        text = f"{key} {label}".strip()
        width = len(text) + 1
        if x + width > MAP_WIDTH:
            break
        yield x, width, text, action
        x += width + 1


def toolbar_action_at(world, x, y):
    if y != 1:
        return None
    for left, width, _, action in toolbar_buttons(world):
        if left <= x < left + width:
            return action
    return None


def draw_toolbar(console, world):
    for y in range(3):
        console.print(x=0, y=y, string=" " * MAP_WIDTH, fg=theme.TEXT, bg=theme.PANEL_BG_DEEP)
    for x, width, text, action in toolbar_buttons(world):
        hovered = getattr(world, "mouse_y", -1) == 1 and x <= getattr(world, "mouse_x", -1) < x+width
        active = action == "SPACE" and getattr(world, "is_paused", False)
        console.print(x=x, y=1, string=text.ljust(width),
                      fg=theme.SELECTION if active else theme.TEXT_DIM,
                      bg=theme.SELECTION_BG if active else theme.HOVER_BG if hovered else theme.PANEL_BG_DEEP)
    console.print(x=1, y=2, string="E Act  F Combat  T Talk  Q Journal  . Step  Wheel Zoom  Right click Inspect",
                  fg=theme.TEXT_MUTED, bg=theme.PANEL_BG_DEEP)
