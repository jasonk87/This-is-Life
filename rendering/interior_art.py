"""Readable rooms from real placed furniture; no decorative simulation objects.

Furniture keeps its original logical tile, collision, interaction and ownership.
Only actual loose map items may appear on a surface. Work zones are standing
spaces, not a license to invent a fixture or obstruct its worker.
"""

from functools import lru_cache
from pathlib import Path

from config import MAP_HEIGHT, MAP_WIDTH
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.dawnlike import ITEM_SPRITES
from rendering import atlas_regions, pixel_scene as pixels, terrain_art
from rendering.village_art import rect, tone
from runtime_compat import np

# atlas index, frame width/height at 32px per logical tile
SPECS = {
    "wooden_bed": (0, 32, 48),
    "bed_simple": (1, 32, 44),
    "wooden_table": (2, 40, 32),
    "wooden_chair": (3, 28, 38),
    "chest_wooden": (4, 34, 30),
    "wall_shelf": (5, 38, 34),
    "bookshelf": (6, 34, 48),
    "cupboard": (7, 36, 36),
    "workbench": (8, 40, 34),
    "forge": (9, 42, 44),
    "oven": (10, 40, 48),
    "anvil": (11, 32, 32),
    "stone_anvil": (11, 32, 32),
    "fireplace": (12, 40, 48),
    "loom": (13, 38, 44),
    "wooden_stool": (14, 26, 28),
    "noticeboard": (15, 38, 42),
}
FLOORS = {"wood_floor", "stone_floor", "brick_floor", "dirt_floor", "mossy_cobblestone"}
_name_keys = {
    definition["name"]: key
    for key, definition in DECORATION_ITEM_DEFINITIONS.items()
    if key in SPECS and "name" in definition
}
_sources = ()


def install():
    global _sources
    path = Path(__file__).resolve().parents[1] / "assets/world32/interiors-atlas-v1.png"
    _sources = atlas_regions.read_silhouettes(path) if path.exists() else ()
    object_pixels.cache_clear()
    foreground_pixels.cache_clear()


def enabled(world):
    return bool(_sources) and pixels.enabled(world) and getattr(world, "interior_art_enabled", True)


def furniture_key(tile):
    return _name_keys.get(getattr(tile, "name", None))


def floor_beneath(world, x, y, building):
    from rendering.console_renderer import _get_tile_key

    for dx, dy in ((0, 1), (1, 0), (-1, 0), (0, -1)):
        if building is not None and not building.contains_global_coords(x + dx, y + dy):
            continue
        key = _get_tile_key(world.get_tile_at(x + dx, y + dy))
        if key in FLOORS:
            return key
    return "wood_floor" if building is not None else "plains"


@lru_cache(maxsize=24)
def floor_surface(key, variant):
    if key == "plains":
        return pixels.resize(terrain_art._surface("plains", variant), 32, 32)
    base = {
        "wood_floor": (105, 79, 52),
        "stone_floor": (82, 87, 84),
        "brick_floor": (114, 80, 62),
        "dirt_floor": (79, 65, 47),
        "mossy_cobblestone": (74, 84, 63),
    }[key]
    image = np.empty((32, 32, 4), dtype=np.uint8)
    image[:] = (*base, 255)
    if key == "wood_floor":
        for row in range(0, 32, 8):
            rect(image, 0, row, 32, 1, tone(base, -17))
            rect(image, 0, row + 1, 32, 1, tone(base, 9))
            x = ((row // 8) * 11 + variant * 7) % 32
            rect(image, x, row, 1, 8, tone(base, -13))
            rect(image, (x + 5) % 24, row + 4, 7, 1, tone(base, -5))
    elif key != "dirt_floor":
        for row in (0, 16):
            rect(image, 0, row, 32, 2, tone(base, -19))
            offset = 0 if row == 0 else 16
            rect(image, offset, row, 2, 16, tone(base, -19))
            rect(image, offset + 2, row + 2, 13, 1, tone(base, 10))
    else:
        for x, y in ((4, 7), (22, 15), (11, 27)):
            rect(image, (x + variant * 3) % 30, y, 2, 1, tone(base, 7))
    return image


def draw_floor(console, world, camera_x, camera_y, x, y, tile, tile_key):
    if not enabled(world):
        return False
    kind = furniture_key(tile)
    if not kind and tile_key not in FLOORS:
        return False
    from rendering.console_renderer import _get_zoom_factor, is_visible

    visible = is_visible(world, x, y)
    if kind and not visible:
        return False  # Preserve the old dim remembered-object glyph.
    building = getattr(world, "get_building_at", lambda *_: None)(x, y)
    key = tile_key if tile_key in FLOORS else floor_beneath(world, x, y, building)
    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    variant = (x * 7 + y * 3) % 4
    token = ("interior-floor", key, variant, zoom)
    image = pixels.scaled(floor_surface(key, variant), unit, unit, token=token)
    tint = (255, 255, 255) if visible else (104, 110, 103)
    return pixels.stamp(
        console, image, (x - camera_x) * unit, (y - camera_y) * unit, token=token, tint=tint
    )


@lru_cache(maxsize=96)
def object_pixels(key, zoom):
    index, width, height = SPECS[key]
    source = atlas_regions.normalize(_sources[index], width, height)
    return pixels.resize(source, width * zoom // 2, height * zoom // 2)


def placement(key, zoom, x, y, camera_x, camera_y):
    image = object_pixels(key, zoom)
    unit = zoom * 16
    px = (x - camera_x) * unit + (unit - image.shape[1]) // 2
    py = (y - camera_y + 1) * unit - image.shape[0]
    return image, px, py


@lru_cache(maxsize=4)
def fire_pixels(phase):
    image = np.zeros((14, 14, 4), dtype=np.uint8)
    rect(image, 1, 10, 12, 3, (130, 64, 35))
    for x, height in ((3, 6 + phase % 3), (7, 10 - phase % 3), (10, 5 + phase % 2)):
        rect(image, x, 12 - height, 3, height, (215, 101, 39))
        rect(image, x + 1, 14 - height, 1, height - 2, (247, 188, 72))
    return image


def visible_furniture(world, camera_x, camera_y, bounds=None):
    """Yield real, visible fixtures in the view (or a small picking region)."""
    if not enabled(world):
        return
    from rendering.console_renderer import _get_world_view_dimensions, is_visible

    vw, vh = _get_world_view_dimensions(world)
    x0, y0, x1, y1 = bounds or (camera_x - 1, camera_y - 1, camera_x + vw + 1, camera_y + vh + 1)
    get_tile = getattr(world, "get_tile_at", lambda *_: None)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if not is_visible(world, x, y):
                continue
            tile = get_tile(x, y)
            key = furniture_key(tile)
            if key is not None:
                yield x, y, key, tile


def draw_object(console, world, camera_x, camera_y, fixture):
    from rendering.console_renderer import _get_zoom_factor, is_visible

    x, y, key, tile = fixture
    zoom = int(_get_zoom_factor(world))
    clip = lambda cx, cy: is_visible(world, camera_x + cx // zoom, camera_y + cy // zoom)
    image, px, py = placement(key, zoom, x, y, camera_x, camera_y)
    tint = pixels.world_tint(world, (x - camera_x) * zoom, (y - camera_y) * zoom)
    pixels.stamp(console, image, px, py, token=("furniture32", key, zoom), tint=tint, clip=clip)
    # Cold source artwork: an unlit hearth must not silently burn.
    if key in {"forge", "fireplace", "oven"} and tile.properties.get("is_lit", False):
        phase = int(getattr(world, "game_time", 0) // 2) % 4
        fire = pixels.scaled(
            fire_pixels(phase), zoom * 7, zoom * 7, token=("hearth-flame", phase, zoom)
        )
        pixels.stamp(
            console,
            fire,
            px + image.shape[1] // 2 - fire.shape[1] // 2,
            py + int(image.shape[0] * 0.56),
            token=("hearth-flame", phase, zoom),
            clip=clip,
        )


def draw_furniture(console, world, camera_x, camera_y):
    for fixture in visible_furniture(world, camera_x, camera_y):
        draw_object(console, world, camera_x, camera_y, fixture)


@lru_cache(maxsize=16)
def foreground_pixels(key, zoom):
    """Runtime layer of the ORIGINAL fixture, never a new simulated object.

    Beds retain the existing blanket and footboard over a reclined occupant.
    Chairs retain their front legs; the backrest and seat stay behind the body.
    """
    source = object_pixels(key, zoom)
    image = np.zeros_like(source)
    if key in {"wooden_bed", "bed_simple"}:
        start = round(source.shape[0] * (0.47 if key == "wooden_bed" else 0.40))
        image[start:] = source[start:]
    elif key == "wooden_chair":
        start = round(source.shape[0] * 0.76)
        # Only the side/front legs, not the crossbar behind the sitter's feet.
        edge = round(source.shape[1] * 0.27)
        image[start:, :edge] = source[start:, :edge]
        image[start:, -edge:] = source[start:, -edge:]
    return image


def support_socket(key, image):
    """Seat surface / pillow centre on the canonical front-facing furniture."""
    height = {"wooden_chair": 0.58, "wooden_stool": 0.34,
              "wooden_bed": 0.29, "bed_simple": 0.18}[key]
    return round(image.shape[1] * 0.5), round(image.shape[0] * height)


def draw_surface_item(console, world, camera_x, camera_y, x, y, item_key):
    if not enabled(world) or item_key not in ITEM_SPRITES:
        return False
    # Only the actual loose pile on this tile; never draw inaccessible stock
    # from a chest/building inventory as if it were already on the table.
    items = getattr(world, "items_on_map", {}).get((x, y), {})
    if items.get(item_key, 0) <= 0:
        return False
    key = furniture_key(world.get_tile_at(x, y))
    if key not in {"wooden_table", "workbench", "wall_shelf"}:
        return False
    from rendering.console_renderer import _get_zoom_factor, is_visible

    if not is_visible(world, x, y):
        return False
    zoom = int(_get_zoom_factor(world))
    image, px, py = placement(key, zoom, x, y, camera_x, camera_y)
    cp = ITEM_SPRITES[item_key]
    token = ("surface-item", cp, zoom)
    item = pixels.scaled(pixels.tile_pixels(cp), zoom * 8, zoom * 8, token=token)
    return pixels.stamp(
        console,
        item,
        px + (image.shape[1] - item.shape[1]) // 2,
        py + max(0, image.shape[0] // 5 - item.shape[0] // 2),
        token=token,
        tint=pixels.world_tint(world, (x - camera_x) * zoom, (y - camera_y) * zoom),
        clip=lambda cx, cy: is_visible(world, camera_x + cx // zoom, camera_y + cy // zoom),
    )


def hit_test(world, camera_x, camera_y, screen_x, screen_y):
    if not enabled(world) or not (0 <= screen_x < MAP_WIDTH and 3 <= screen_y < MAP_HEIGHT):
        return None
    from rendering.console_renderer import _get_zoom_factor, is_visible

    zoom = int(_get_zoom_factor(world))
    wx, wy = camera_x + screen_x // zoom, camera_y + screen_y // zoom
    if not is_visible(world, wx, wy):
        return None
    for y in range(wy + 1, wy - 2, -1):
        for x in range(wx + 1, wx - 2, -1):
            if not is_visible(world, x, y):
                continue
            key = furniture_key(world.get_tile_at(x, y))
            if key is None:
                continue
            image, px, py = placement(key, zoom, x, y, camera_x, camera_y)
            sx, sy = int(screen_x * 16 - px), int(screen_y * 16 - py)
            if sx + 16 <= 0 or sy + 16 <= 0 or sx >= image.shape[1] or sy >= image.shape[0]:
                continue
            if (image[max(0, sy) : sy + 16, max(0, sx) : sx + 16, 3] > 32).any():
                return x, y
    return None
