"""Pixel-aligned UI geometry independent of a font's Unicode coverage.

The shipped font and its fallback both lack full block and several corners.
Construct these geometric glyphs explicitly so meters and frames never vanish.
"""
from runtime_compat import np


def register_ui_glyphs(tileset):
    size = 16
    masks = {}
    for char in "─│┌┐└┘├┤┬┴┼█░•▲▼":
        mask = np.zeros((size, size), dtype=bool)
        if char == "█":
            mask[:] = True
        elif char == "░":
            mask[::4, ::4] = True
            mask[2::4, 2::4] = True
        elif char == "•":
            mask[6:10, 6:10] = True
        elif char in "▲▼":
            for row in range(6):
                y = 4 + row if char == "▲" else 11 - row
                mask[y, 7-row:9+row] = True
        else:
            if char in "─┐┘┤┬┴┼":
                mask[7:9, :8] = True
            if char in "─┌└├┬┴┼":
                mask[7:9, 8:] = True
            if char in "│└┘├┤┴┼":
                mask[:8, 7:9] = True
            if char in "│┌┐├┤┬┼":
                mask[8:, 7:9] = True
        masks[char] = mask
    for char, mask in masks.items():
        rgba = np.full((size, size, 4), 255, dtype=np.uint8)
        rgba[:, :, 3] = mask * 255
        tileset[ord(char)] = rgba
