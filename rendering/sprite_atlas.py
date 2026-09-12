"""Runtime helpers for stamping DawnLike sprites across zoomed console cells."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from data.dawnlike import DAWNLIKE_BASE_CODEPOINT, DAWNLIKE_COLUMNS, all_catalog_codepoints


ZOOMED_DAWNLIKE_BASE_CODEPOINT = 0xF0000
ZOOMED_DAWNLIKE_LEVELS = (2, 3, 4)
DAWNLIKE_TILE_SIZE = 16

_zoomed_sprite_codepoints: dict[tuple[int, int, int, int], int] = {}


def zoomed_sprite_codepoint(base_codepoint: int, zoom: int, offset_x: int, offset_y: int) -> int | None:
    """Return a registered split-sprite codepoint for a zoomed DawnLike tile."""
    return _zoomed_sprite_codepoints.get((int(base_codepoint), int(zoom), int(offset_x), int(offset_y)))


def register_pixel_sprite(tileset, base_codepoint, pixels, first_split_codepoint):
    """Register a native 16px RGBA sprite and all integer zoom quadrants.

    Returns the next unused split codepoint. Callers reserve separate ranges
    so generated materials cannot overwrite the DawnLike catalog.
    """
    tileset[base_codepoint] = pixels
    next_codepoint = first_split_codepoint
    for zoom in ZOOMED_DAWNLIKE_LEVELS:
        expanded = pixels.repeat(zoom, axis=0).repeat(zoom, axis=1)
        for y in range(zoom):
            for x in range(zoom):
                tileset[next_codepoint] = expanded[y*16:(y+1)*16, x*16:(x+1)*16]
                _zoomed_sprite_codepoints[(base_codepoint, zoom, x, y)] = next_codepoint
                next_codepoint += 1
    return next_codepoint


def register_zoomed_dawnlike_tiles(
    tileset,
    image_path: str | Path,
    *,
    zoom_levels: Iterable[int] = ZOOMED_DAWNLIKE_LEVELS,
) -> int:
    """Create zoomed split tiles for every catalogued DawnLike sprite.

    tcod renders one image per console cell. For zoomed-in views we therefore
    split an upscaled 32/48/64px sprite back into 16px quadrants and register
    each quadrant as a private-use codepoint. The renderer can then stamp those
    cells together into one larger pixel-art sprite.
    """
    from PIL import Image
    from runtime_compat import np

    image_path = Path(image_path)
    image = Image.open(image_path).convert("RGBA")
    image_width, image_height = image.size
    row_count = image_height // DAWNLIKE_TILE_SIZE
    column_count = min(DAWNLIKE_COLUMNS, image_width // DAWNLIKE_TILE_SIZE)
    if column_count <= 0 or row_count <= 0:
        return 0

    resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    valid_levels = tuple(sorted({int(level) for level in zoom_levels if int(level) in ZOOMED_DAWNLIKE_LEVELS}))
    codepoints = sorted(set(all_catalog_codepoints().values()))
    next_codepoint = ZOOMED_DAWNLIKE_BASE_CODEPOINT
    _zoomed_sprite_codepoints.clear()

    for base_codepoint in codepoints:
        sprite_index = int(base_codepoint) - DAWNLIKE_BASE_CODEPOINT
        if sprite_index < 0:
            continue
        row = sprite_index // DAWNLIKE_COLUMNS
        col = sprite_index % DAWNLIKE_COLUMNS
        if row >= row_count or col >= column_count:
            continue

        left = col * DAWNLIKE_TILE_SIZE
        top = row * DAWNLIKE_TILE_SIZE
        tile = image.crop((left, top, left + DAWNLIKE_TILE_SIZE, top + DAWNLIKE_TILE_SIZE))
        for zoom in valid_levels:
            scaled_size = DAWNLIKE_TILE_SIZE * zoom
            scaled = tile.resize((scaled_size, scaled_size), resample=resampling)
            for offset_y in range(zoom):
                for offset_x in range(zoom):
                    part = scaled.crop((
                        offset_x * DAWNLIKE_TILE_SIZE,
                        offset_y * DAWNLIKE_TILE_SIZE,
                        (offset_x + 1) * DAWNLIKE_TILE_SIZE,
                        (offset_y + 1) * DAWNLIKE_TILE_SIZE,
                    ))
                    tileset.set_tile(next_codepoint, np.array(part))
                    _zoomed_sprite_codepoints[(base_codepoint, zoom, offset_x, offset_y)] = next_codepoint
                    next_codepoint += 1

    return len(_zoomed_sprite_codepoints)
