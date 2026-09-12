"""Alpha-composited world sprites without changing the 16px console UI.

The tcod console stores one glyph per cell. Stamping a transparent actor used
to replace the floor beneath it. This adapter composites sprite pixels with
the existing cell, then caches the resulting native console tile. Source art
can be 32px or larger; fonts, map coordinates and input remain unchanged.
"""

from collections import OrderedDict
from runtime_compat import np
from config import MAP_WIDTH, MAP_HEIGHT

_tileset = None
_composites = {}
_pixels = {}
_parts = {}
_scaled = OrderedDict()
_lightfield = None
_light_visible = None
BASE = 0x106000
CAPACITY = 32000


def install(tileset):
    global _tileset, _lightfield, _light_visible
    _tileset = tileset
    _composites.clear()
    _pixels.clear()
    _parts.clear()
    _scaled.clear()
    _lightfield = _light_visible = None


def enabled(world):
    return _tileset is not None and getattr(world, "world_art_style", "village32") == "village32"


def begin_frame():
    global _lightfield, _light_visible
    _lightfield = _light_visible = None
    # Recycle only between frames, never while a console still references
    # a tile allocated earlier in the same frame.
    if len(_composites) > CAPACITY - 5000:
        _composites.clear()
        _pixels.clear()
        _parts.clear()
    elif len(_parts) > 30000:
        _parts.clear()


def scaled(source, width, height, *, token):
    """Bounded cache for immutable artwork at the four supported zooms."""
    key = (token, width, height)
    if key not in _scaled:
        _scaled[key] = resize(source, width, height)
        if len(_scaled) > 192:
            _scaled.popitem(last=False)
    else:
        _scaled.move_to_end(key)
    return _scaled[key]


def set_lightfield(tint, visible):
    """Receive the existing renderer's local-light result, never simulate it."""
    global _lightfield, _light_visible
    _lightfield, _light_visible = tint, visible


def world_tint(world, screen_x=None, screen_y=None):
    """Share the existing local light, ambient and season palette."""
    if _lightfield is not None and screen_x is not None and screen_y is not None:
        x, y = int(screen_x), int(screen_y)
        if 0 <= y < _lightfield.shape[0] and 0 <= x < _lightfield.shape[1] and _light_visible[y, x]:
            return tuple(int(c) for c in _lightfield[y, x])
    from rendering import lighting
    from rendering.console_renderer import (
        LIGHT_LEVEL_TINTS,
        SEASON_TINTS,
        current_season_name,
    )

    level = getattr(world, "current_light_level_name", "DAY")
    shade = 255 * (0.55 + 0.45 * lighting.ambient_for_light_level(level))
    light = LIGHT_LEVEL_TINTS.get(level, (1, 1, 1))
    season = SEASON_TINTS.get(current_season_name(world), (1, 1, 1))
    return tuple(min(255, round(shade * a * b)) for a, b in zip(light, season))


def resize(pixels, width, height):
    """Nearest-neighbor sampling, including non-square source sprites."""
    rows = np.minimum(pixels.shape[0] - 1, np.arange(height) * pixels.shape[0] // height)
    cols = np.minimum(pixels.shape[1] - 1, np.arange(width) * pixels.shape[1] // width)
    return pixels[rows[:, None], cols[None, :]].copy()


def tile_pixels(cp):
    if cp not in _pixels:
        _pixels[cp] = _tileset.get_tile(int(cp)).copy()
    return _pixels[cp]


def stamp(console, pixels, x, y, *, token, tint=(255, 255, 255), clip=None):
    """Stamp RGBA at screen-pixel coordinates, clipped to the map and mask.

    `token` identifies immutable source pixels. `clip(cx, cy)` optionally
    gates each destination console cell (e.g. for field-of-view boundaries).
    """
    if _tileset is None or not hasattr(console, "ch"):
        return False
    x, y = int(x), int(y)
    height, width = pixels.shape[:2]
    x0, y0 = max(0, x // 16), max(0, y // 16)
    x1 = min(MAP_WIDTH, console.width, (x + width + 15) // 16)
    y1 = min(MAP_HEIGHT, console.height, (y + height + 15) // 16)
    for cy in range(y0, y1):
        for cx in range(x0, x1):
            if clip is not None and not clip(cx, cy):
                continue
            sx, sy = cx * 16 - x, cy * 16 - y
            left, top = max(0, sx), max(0, sy)
            right, bottom = min(width, sx + 16), min(height, sy + 16)
            part_key = (token, sx, sy)
            cached_part = _parts.get(part_key)
            if cached_part is None:
                part = pixels[top:bottom, left:right]
                opaque = part.shape[:2] == (16, 16) and bool((part[:, :, 3] == 255).all())
                cached_part = (part.astype(np.uint32), bool(part[:, :, 3].any()), opaque)
                _parts[part_key] = cached_part
            layer, occupied, opaque = cached_part
            if not occupied:
                continue
            if opaque:
                key = (part_key, tint)
            else:
                cp = int(console.ch[cy, cx])
                fg, bg = tuple(console.fg[cy, cx]), tuple(console.bg[cy, cx])
                key = (part_key, cp, fg, bg, tint)
            composite_cp = _composites.get(key)
            if composite_cp is None:
                if len(_composites) >= CAPACITY:
                    continue  # Keep already allocated cells valid this frame.
                tint_array = np.array(tint, dtype=np.uint32)
                if opaque:
                    rgb = layer[:, :, :3] * tint_array // 255
                else:
                    base = tile_pixels(cp).astype(np.uint32)
                    alpha = base[:, :, 3:4]
                    rgb = (
                        base[:, :, :3] * np.array(fg, dtype=np.uint32) // 255 * alpha
                        + np.array(bg, dtype=np.uint32) * (255 - alpha)
                    ) // 255
                    la = layer[:, :, 3:4]
                    target = rgb[top - sy : bottom - sy, left - sx : right - sx]
                    target[:] = (
                        layer[:, :, :3] * tint_array // 255 * la + target * (255 - la)
                    ) // 255
                result = np.full((16, 16, 4), 255, dtype=np.uint8)
                result[:, :, :3] = rgb
                composite_cp = BASE + len(_composites)
                _tileset[composite_cp] = result
                _pixels[composite_cp] = result
                _composites[key] = composite_cp
            console.ch[cy, cx] = composite_cp
            console.fg[cy, cx] = (255, 255, 255)
    return True


def source_sheet(path, columns, rows, cell_width, cell_height):
    """Read an atlas without altering it; normalize cells only in memory."""
    from PIL import Image

    source = np.array(Image.open(path).convert("RGBA"))
    if not (source[:, :, 3] < 32).any():
        raise ValueError(f"Sprite atlas needs true transparency, not a baked background: {path}")
    sprites = []
    for row in range(rows):
        for column in range(columns):
            part = source[
                row * source.shape[0] // rows : (row + 1) * source.shape[0] // rows,
                column * source.shape[1] // columns : (column + 1) * source.shape[1] // columns,
            ]
            ys, xs = np.where(part[:, :, 3] > 32)
            canvas = np.zeros((cell_height, cell_width, 4), dtype=np.uint8)
            if len(xs):
                crop = part[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
                scale = min((cell_width - 4) / crop.shape[1], (cell_height - 4) / crop.shape[0])
                sw, sh = max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))
                canvas[
                    cell_height - sh - 2 : cell_height - 2,
                    (cell_width - sw) // 2 : (cell_width - sw) // 2 + sw,
                ] = resize(crop, sw, sh)
            sprites.append(canvas)
    return tuple(sprites)
