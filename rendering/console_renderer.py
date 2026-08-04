# rendering/console_renderer.py

from tcod_compat import tcod
import textwrap
import itertools
import math
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, STATUS_PANEL_WIDTH,
    MINIMAP_WIDTH, MINIMAP_HEIGHT, MINIMAP_X, MINIMAP_Y,
    COLOR_PLAYER_STATUS_WET, COLOR_PLAYER_STATUS_FREEZING, COLOR_CURSOR_INFO_TEXT,
    WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE, DAY_LENGTH_TICKS
)
from data.tiles import TILE_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from data.environment import WEATHER_DEFINITIONS
from data.dawnlike import get_entity_sprite, _get_equipment_overlays, ITEM_SPRITES
from entities.animal import Animal
from engine import Player
from rendering.sprite_atlas import ZOOMED_DAWNLIKE_LEVELS, zoomed_sprite_codepoint
from presentation.ambient_speech import (
    format_ambient_speech_for_player,
    visible_ambient_speech_lines,
)
from presentation.social_feedback import (
    collect_visible_social_indicators,
    social_hover_summary,
    social_marker_for_entity,
    social_tags_for_entity,
)

TRADE_CAPABLE_PROFESSIONS = {"Merchant", "Miller", "Scribe", "Traveling Merchant"}

TERRAIN_BACKGROUNDS = {
    "plains": (36, 64, 34),
    "forest": (18, 44, 24),
    "road": (82, 72, 56),
    "wood_wall": (58, 38, 24),
    "stone_wall": (54, 56, 60),
    "door": (78, 52, 28),
    "wood_floor": (76, 51, 31),
    "stone_floor": (58, 60, 63),
    "brick_floor": (76, 48, 38),
    "dirt_floor": (66, 45, 30),
    "window": (26, 49, 60),
    "water": (20, 55, 96),
    "deep_water": (8, 30, 70),
    "mountain": (66, 66, 70),
    "snow": (142, 152, 156),
    "tall_grass": (30, 68, 30),
    "flower": (64, 42, 58),
    "well": (50, 56, 66),
    "tilled_soil": (82, 50, 32),
    "wheat_plant_growing": (58, 84, 34),
    "wheat_plant": (122, 102, 36),
    "fire_trap_active": (96, 22, 12),
}

TERRAIN_FILL_TILE_KEYS = {
    "plains",
    "road",
    "wood_floor",
    "stone_floor",
    "brick_floor",
    "dirt_floor",
    "water",
    "deep_water",
    "snow",
    "tilled_soil",
    "forest",
    "mountain",
    "tall_grass",
    "flower",
    "wheat_plant_growing",
    "wheat_plant",
    "fire_trap_hidden",
    "fire_trap_active",
    "mossy_cobblestone",
}

TERRAIN_ACCENTS = {
    "plains": ("'", (86, 126, 66), 5),
    "road": (".", (112, 98, 72), 7),
    "wood_floor": (".", (112, 74, 42), 8),
    "stone_floor": (".", (98, 100, 104), 7),
    "brick_floor": (".", (112, 70, 58), 7),
    "dirt_floor": (".", (96, 66, 42), 5),
    "water": ("~", (80, 132, 184), 4),
    "deep_water": ("~", (48, 88, 142), 5),
    "snow": (".", (210, 220, 220), 6),
    "tilled_soil": (",", (118, 74, 44), 3),
    "forest": ("'", (72, 122, 60), 4),
    "mountain": ("^", (132, 132, 132), 7),
    "tall_grass": ("'", (94, 150, 70), 3),
    "flower": ("*", (226, 122, 180), 8),
    "wheat_plant_growing": ("'", (128, 186, 86), 3),
    "wheat_plant": ("'", (208, 174, 64), 3),
    "mossy_cobblestone": (".", (95, 120, 75), 6),
}

_LEGACY_UNUSED_DISPLAY_CHARS = {
    "plains": ".",
    "forest": "Y",
    "road": "=",
    "wood_wall": "█",
    "stone_wall": "█",
    "door": "+",
    "wood_floor": ".",
    "window": "o",
    "water": "~",
    "deep_water": "≈",
    "mountain": "▲",
    "snow": "*",
    "tall_grass": "\"",
    "flower": "*",
    "well": "O",
    "tilled_soil": "≈",
    "wheat_plant_growing": "i",
    "wheat_plant": "I",
    "fire_trap_active": "x",
}

def _clamp_color(color):
    return tuple(max(0, min(255, int(channel))) for channel in color)

def _dim_color(color, ratio=0.55):
    return _clamp_color((color[0] * ratio, color[1] * ratio, color[2] * ratio))


def _color_distance(color_a, color_b):
    return math.sqrt(sum((int(a) - int(b)) ** 2 for a, b in zip(color_a, color_b)))


def _ensure_entity_contrast(fg_color, bg_color):
    if bg_color is None or _color_distance(fg_color, bg_color) >= 90:
        return fg_color

    bg_luma = (bg_color[0] * 0.2126) + (bg_color[1] * 0.7152) + (bg_color[2] * 0.0722)
    if bg_luma < 128:
        return _lighten(fg_color, 0.35)
    return _dim_color(fg_color, 0.55)


def _ensure_player_contrast(bg_color):
    base_color = (255, 245, 140)
    if bg_color is None or _color_distance(base_color, bg_color) >= 110:
        return base_color

    bg_luma = (bg_color[0] * 0.2126) + (bg_color[1] * 0.7152) + (bg_color[2] * 0.0722)
    if bg_luma < 128:
        return (255, 255, 220)
    return (96, 54, 20)

def _get_tile_key(tile):
    if tile is None:
        return None

    for key, definition in TILE_DEFINITIONS.items():
        char_val = definition.get("char", " ")
        char_int = ord(char_val) if isinstance(char_val, str) else char_val
        if definition.get("name") == tile.name and char_int == tile.char:
            return key
    return None

def _get_tile_background(tile):
    tile_key = _get_tile_key(tile)
    if tile_key in TERRAIN_BACKGROUNDS:
        return TERRAIN_BACKGROUNDS[tile_key]

    if tile is None:
        return (0, 0, 0)
    if "water" in tile.name.lower():
        return (8, 20, 56)
    if "wall" in tile.name.lower():
        return (50, 36, 28)
    if "floor" in tile.name.lower():
        return (58, 40, 22)
    return _dim_color(tile.color, 0.22)

def _get_tile_char(tile):
    if tile is None:
        return " "
    return chr(tile.char)


def _format_world_clock(game_time):
    day_length = max(1, int(DAY_LENGTH_TICKS))
    tick = max(0, int(game_time))
    day = tick // day_length
    tick_in_day = tick % day_length
    minute_of_day = int((tick_in_day / day_length) * 24 * 60)
    hour = (minute_of_day // 60) % 24
    minute = minute_of_day % 60
    return f"Day {day}, {hour:02d}:{minute:02d}"


def _tune_floor_colors(tile_key, fg_color, bg_color):
    if tile_key == "wood_floor":
        return _dim_color(fg_color, 0.72), _lighten(bg_color, 0.06)
    return fg_color, bg_color


def _color_shift(color, amount):
    return _clamp_color((color[0] + amount, color[1] + amount, color[2] + amount))


def _visual_noise(world_x, world_y, local_x=0, local_y=0, salt=0):
    value = (
        (int(world_x) * 73856093)
        ^ (int(world_y) * 19349663)
        ^ (int(local_x) * 83492791)
        ^ (int(local_y) * 2654435761)
        ^ int(salt)
    )
    return value & 0xFFFFFFFF


def _is_terrain_fill_tile(tile, tile_key):
    if tile is None:
        return False
    if tile_key in TERRAIN_FILL_TILE_KEYS:
        return True
    lowered = tile.name.lower()
    return any(term in lowered for term in ("floor", "plains", "dirt", "soil", "road", "water", "snow", "cobblestone"))


def _draw_terrain_fill(console, rect, tile_key, glyph, *, fg, bg, world_x, world_y):
    if rect is None:
        return
    x0, y0, x1, y1 = rect
    if (x1 - x0 + 1) == 1 and (y1 - y0 + 1) == 1:
        console.print(x=x0, y=y0, string=glyph, fg=fg, bg=bg)
        return

    accent, accent_fg, cadence = TERRAIN_ACCENTS.get(tile_key or "", (" ", fg, 99))
    for draw_y in range(y0, y1 + 1):
        for draw_x in range(x0, x1 + 1):
            local_x = draw_x - x0
            local_y = draw_y - y0
            noise = _visual_noise(world_x, world_y, local_x, local_y, salt=17)
            shade = ((noise % 5) - 2) * 3
            cell_bg = _color_shift(bg, shade)
            mark = " "
            if cadence > 0 and noise % cadence == 0:
                mark = accent
            console.print(x=draw_x, y=draw_y, string=mark, fg=accent_fg, bg=cell_bg)


def _is_groundlike_tile(tile, tile_key):
    if tile is None:
        return False
    if tile_key in {
        "plains", "grass", "dirt", "road", "wood_floor", "water", "deep_water",
        "forest", "mountain", "tilled_soil", "wheat_plant_growing", "wheat_plant",
        "fire_trap_active",
    }:
        return True
    lowered = tile.name.lower()
    return any(term in lowered for term in ("floor", "grass", "plains", "dirt", "soil", "road", "water", "forest", "mountain", "plant"))


def _draw_world_tile(console, world, camera_x, camera_y, world_x, world_y, tile, fg_color, bg_color):
    rect = _world_to_screen_rect(world, camera_x, camera_y, world_x, world_y)
    if rect is None:
        return
    tile_key = _get_tile_key(tile)
    glyph = _get_tile_char(tile)
    if _is_terrain_fill_tile(tile, tile_key):
        _draw_terrain_fill(console, rect, tile_key, glyph, fg=fg_color, bg=bg_color, world_x=world_x, world_y=world_y)
        return
    if tile is not None and _draw_zoomed_sprite(console, world, rect, int(tile.char), fg=(255, 255, 255), bg=bg_color):
        return
    if _is_groundlike_tile(tile, tile_key):
        _draw_zoomed_glyph(console, rect, glyph, fg=fg_color, bg=bg_color)
        return

    x0, y0, x1, y1 = rect
    for draw_y in range(y0, y1 + 1):
        for draw_x in range(x0, x1 + 1):
            console.print(x=draw_x, y=draw_y, string=" ", fg=fg_color, bg=bg_color)

    screen_point = _screen_point_for_world(world, camera_x, camera_y, world_x, world_y)
    if screen_point is not None:
        screen_x, screen_y = screen_point
        console.print(x=screen_x, y=screen_y, string=glyph, fg=fg_color)

def _get_entity_foreground(entity):
    if getattr(getattr(entity, "physical", None), "is_dead", False):
        return (130, 130, 130)
    if isinstance(entity, Player):
        return (255, 245, 140)
    if isinstance(entity, Animal):
        return getattr(entity, "color", (180, 220, 140))
    return getattr(entity, "color", (255, 255, 255))


def _get_zoom_factor(world):
    zoom_levels = getattr(world, "zoom_levels", None)
    zoom_index = getattr(world, "zoom_index", 0)
    if not zoom_levels:
        return 1.0
    zoom_index = max(0, min(int(zoom_index), len(zoom_levels) - 1))
    return float(zoom_levels[zoom_index])


def _get_world_view_dimensions(world):
    zoom = _get_zoom_factor(world)
    view_width = max(1, int(math.ceil(MAP_WIDTH / zoom)))
    view_height = max(1, int(math.ceil(MAP_HEIGHT / zoom)))
    return min(WORLD_WIDTH, view_width), min(WORLD_HEIGHT, view_height)


def _screen_to_world(world, camera_x, camera_y, screen_x, screen_y):
    zoom = _get_zoom_factor(world)
    return camera_x + int(screen_x // zoom), camera_y + int(screen_y // zoom)


def _world_to_screen_rect(world, camera_x, camera_y, world_x, world_y):
    zoom = _get_zoom_factor(world)
    rel_x = world_x - camera_x
    rel_y = world_y - camera_y
    x0 = int(math.floor(rel_x * zoom))
    y0 = int(math.floor(rel_y * zoom))
    x1 = int(math.floor((rel_x + 1) * zoom) - 1)
    y1 = int(math.floor((rel_y + 1) * zoom) - 1)
    if x1 < x0:
        x1 = x0
    if y1 < y0:
        y1 = y0
    if x1 < 0 or y1 < 0 or x0 >= MAP_WIDTH or y0 >= MAP_HEIGHT:
        return None
    return max(0, x0), max(0, y0), min(MAP_WIDTH - 1, x1), min(MAP_HEIGHT - 1, y1)


def _draw_zoomed_glyph(console, rect, glyph, *, fg, bg=None):
    if rect is None:
        return
    x0, y0, x1, y1 = rect
    for draw_y in range(y0, y1 + 1):
        for draw_x in range(x0, x1 + 1):
            kwargs = {"x": draw_x, "y": draw_y, "string": glyph, "fg": fg}
            if bg is not None:
                kwargs["bg"] = bg
            console.print(**kwargs)


def _integer_zoom_for_rect(world, rect):
    if rect is None:
        return None
    zoom = _get_zoom_factor(world)
    integer_zoom = int(round(zoom))
    if abs(zoom - integer_zoom) > 0.01 or integer_zoom not in ZOOMED_DAWNLIKE_LEVELS:
        return None
    x0, y0, x1, y1 = rect
    if (x1 - x0 + 1) != integer_zoom or (y1 - y0 + 1) != integer_zoom:
        return None
    return integer_zoom


def _draw_zoomed_sprite(console, world, rect, base_codepoint, *, fg, bg=None):
    zoom = _integer_zoom_for_rect(world, rect)
    if zoom is None:
        return False
    x0, y0, _, _ = rect
    draw_calls = []
    for offset_y in range(zoom):
        for offset_x in range(zoom):
            codepoint = zoomed_sprite_codepoint(base_codepoint, zoom, offset_x, offset_y)
            if codepoint is None:
                return False
            kwargs = {
                "x": x0 + offset_x,
                "y": y0 + offset_y,
                "string": chr(codepoint),
                "fg": fg,
            }
            if bg is not None:
                kwargs["bg"] = bg
            draw_calls.append(kwargs)
    for kwargs in draw_calls:
        console.print(**kwargs)
    return True


PORTRAIT_ZOOM = 3


def _draw_entity_portrait(console, x, y, entity, *, zoom=PORTRAIT_ZOOM, fg=(255, 255, 255)):
    """Draw an entity's sprite as a small NxN portrait for menu UI (dialogue,
    social) at a fixed console-relative position.

    This intentionally does NOT reuse _draw_zoomed_sprite, because that
    helper derives its zoom level from the world camera's current zoom
    state (_get_zoom_factor/_integer_zoom_for_rect) and is meant for
    map-camera rects. A menu portrait has nothing to do with what zoom
    level the player currently has the map scrolled to, so this stamps
    the same pre-split DawnLike codepoints (via zoomed_sprite_codepoint)
    at a fixed zoom instead.

    Falls back to a single unzoomed sprite cell if the split-tile registry
    for `zoom` hasn't been populated (e.g. headless/test mode, where
    register_zoomed_dawnlike_tiles() is never called), so callers never
    need their own fallback branch.
    """
    base_codepoint = get_entity_sprite(entity)
    if base_codepoint is None:
        return False

    draw_calls = []
    for offset_y in range(zoom):
        for offset_x in range(zoom):
            codepoint = zoomed_sprite_codepoint(base_codepoint, zoom, offset_x, offset_y)
            if codepoint is None:
                console.print(x=x, y=y, string=chr(base_codepoint), fg=fg)
                return True
            draw_calls.append({"x": x + offset_x, "y": y + offset_y, "string": chr(codepoint), "fg": fg})
    for kwargs in draw_calls:
        console.print(**kwargs)
    return True


def _screen_point_for_world(world, camera_x, camera_y, world_x, world_y):
    rect = _world_to_screen_rect(world, camera_x, camera_y, world_x, world_y)
    if rect is None:
        return None
    x0, y0, x1, y1 = rect
    return x0 + ((x1 - x0) // 2), y0 + ((y1 - y0) // 2)


def _iter_render_entities(world):
    all_entities = itertools.chain(world.npcs, world.village_npcs, [world.player])
    return sorted(all_entities, key=lambda e: e.render_order.value if hasattr(e, "render_order") else 0)


def _draw_items(console, world, camera_x, camera_y):
    for (item_x, item_y), items in world.items_on_map.items():
        if not items or not is_visible(world, item_x, item_y):
            continue

        item_key = next(iter(items))
        item_def = ITEM_DEFINITIONS.get(item_key)
        if not item_def:
            continue

        char_val = item_def.get("char", "*")
        item_char = chr(char_val) if isinstance(char_val, int) else str(char_val)
        item_color = item_def.get("color", (255, 245, 160))

        rect = _world_to_screen_rect(world, camera_x, camera_y, item_x, item_y)
        if rect is not None and isinstance(char_val, int) and _draw_zoomed_sprite(console, world, rect, char_val, fg=(255, 255, 255)):
            continue

        screen_point = _screen_point_for_world(world, camera_x, camera_y, item_x, item_y)
        if screen_point is not None:
            screen_x, screen_y = screen_point
            console.print(x=screen_x, y=screen_y, string=item_char, fg=item_color)

def _draw_overlay_stamp(console, world, rect, overlay_codepoint, anchor_x, anchor_y, *, fg):
    """Stamp a single overlay sprite cell nearest to the anchor within a zoomed entity rect."""
    zoom = _integer_zoom_for_rect(world, rect)
    if zoom is None or zoom < 2:
        return False
    x0, y0, _, _ = rect
    ox = min(zoom - 1, int(anchor_x * zoom))
    oy = min(zoom - 1, int(anchor_y * zoom))
    sub_codepoint = zoomed_sprite_codepoint(overlay_codepoint, zoom, ox, oy)
    if sub_codepoint is None:
        return False
    console.print(x=x0 + ox, y=y0 + oy, string=chr(sub_codepoint), fg=fg)
    return True


def _get_item_icon_codepoint(item_key):
    """Return the DawnLike codepoint for an item's menu icon, if catalogued."""
    if not item_key:
        return None
    return ITEM_SPRITES.get(item_key)


def _draw_item_icon(console, x, y, item_key, *, fg=(255, 255, 255)):
    """Draw a single unzoomed item-sprite icon at a console cell for menu UI.

    Menu screens are drawn at native 1x console scale (not the zoomed world
    camera), so this stamps the base DawnLike codepoint directly instead of
    going through the zoomed sprite-splitting path used for the map.
    Returns True if an icon was drawn, False if this item has no catalogued
    sprite (callers should fall back to text-only layout in that case).
    """
    codepoint = _get_item_icon_codepoint(item_key)
    if codepoint is None:
        return False
    console.print(x=x, y=y, string=chr(codepoint), fg=fg)
    return True


QUALITY_ORDER = ("Poor", "Normal", "Fine", "Masterwork")
QUALITY_TEXT_COLORS = {
    "Poor": (150, 150, 150),
    "Normal": (255, 255, 255),
    "Fine": (110, 220, 130),
    "Masterwork": (255, 195, 60),
}


def _quality_text_color(quality):
    """Return the display color for an item's quality tier, defaulting to
    the Normal-tier color for unrecognized or missing values."""
    return QUALITY_TEXT_COLORS.get(quality, QUALITY_TEXT_COLORS["Normal"])


def _get_trade_row_item_reference(world, item_key, *, selling):
    """Best-effort lookup of a representative ItemReference for a trade row.

    Used only for quality-aware name/color display - never mutates state.
    The trade snapshot itself (built in engine.py) intentionally still
    aggregates by raw item_key/quantity/price; reworking that into
    quality-aware stacks would change trade mechanics (separate prices per
    quality tier, buy/sell indexing) rather than just how a row is drawn,
    so this only reaches into the underlying inventory to borrow one
    instance's quality/name for display.
    """
    if selling:
        inventory = getattr(getattr(world.player, "economic", None), "inventory", None)
        return inventory.get_item_reference(item_key) if inventory is not None else None

    npc_target = getattr(world, "trade_ui_npc_target", None)
    if npc_target is None:
        return None
    npc_inventory = getattr(getattr(npc_target, "economic", None), "npc_inventory", None)
    if npc_inventory is not None:
        ref = npc_inventory.get_item_reference(item_key)
        if ref is not None:
            return ref
    building_id = getattr(getattr(npc_target, "schedule", None), "work_building_id", None)
    building = world.buildings_by_id.get(building_id) if building_id else None
    building_inventory = getattr(building, "building_inventory", None)
    if building_inventory is not None:
        return building_inventory.get_item_reference(item_key)
    return None


def _draw_entities(console, world, camera_x, camera_y):
    for entity in _iter_render_entities(world):
        if isinstance(entity, Player) and entity.state.is_riding:
            continue
        if entity is not world.player and getattr(entity, "is_sleeping", False):
            continue

        r_x = getattr(entity, "render_x", entity.x)
        r_y = getattr(entity, "render_y", entity.y)
        draw_x = int(round(r_x))
        draw_y = int(round(r_y))

        if not is_visible(world, entity.x, entity.y):
            continue

        screen_point = _screen_point_for_world(world, camera_x, camera_y, draw_x, draw_y)
        if screen_point is not None:
            cell_bg = None
            if hasattr(console, "bg"):
                sample_x, sample_y = screen_point
                cell_bg = tuple(console.bg[sample_y, sample_x])
            fg = _get_entity_foreground(entity)
            if isinstance(entity, Player):
                fg = _ensure_player_contrast(cell_bg)
            else:
                fg = _ensure_entity_contrast(fg, cell_bg)
            screen_x, screen_y = screen_point
            sprite = get_entity_sprite(entity)
            rect = _world_to_screen_rect(world, camera_x, camera_y, draw_x, draw_y)
            sprite_fg = (180, 180, 180) if getattr(getattr(entity, "physical", None), "is_dead", False) else (255, 255, 255)
            zoomed = False
            if rect is not None and _draw_zoomed_sprite(console, world, rect, sprite, fg=sprite_fg):
                zoomed = True

            # Stamp equipment overlays on top of the base sprite
            if not getattr(getattr(entity, "physical", None), "is_dead", False):
                overlays = _get_equipment_overlays(entity)
                if overlays and rect is not None:
                    overlay_fg = (210, 210, 220)
                    for overlay_codepoint, ax, ay, _az in overlays:
                        if zoomed:
                            _draw_overlay_stamp(console, world, rect, overlay_codepoint, ax, ay, fg=overlay_fg)
                        else:
                            console.print(x=screen_x, y=screen_y, string=chr(overlay_codepoint), fg=overlay_fg)

            if not zoomed:
                console.print(x=screen_x, y=screen_y, string=chr(sprite), fg=fg)

def _get_entity_marker(entity, world=None):
    if getattr(getattr(entity, "physical", None), "is_dead", False):
        return None
    if getattr(getattr(entity, "combat", None), "is_hostile_to_player", False):
        return "!", (255, 120, 120)
    if hasattr(entity, "active_quest") and getattr(entity, "active_quest", None):
        return "?", (255, 215, 120)
    social_marker = social_marker_for_entity(entity, world)
    if social_marker is not None:
        return social_marker
    profession = getattr(getattr(entity, "economic", None), "profession", "")
    if profession in TRADE_CAPABLE_PROFESSIONS:
        return "$", (120, 255, 160)
    if profession in {"Guard", "Sheriff", "Hunter"}:
        return "+", (170, 210, 255)
    if isinstance(entity, Animal):
        return "^", (180, 220, 160)
    return None

def _get_visible_nearby_entities(world, limit=5):
    nearby = []
    for entity in itertools.chain(world.npcs, world.village_npcs):
        if getattr(getattr(entity, "physical", None), "is_dead", False) or getattr(entity, "is_sleeping", False):
            continue
        if not is_visible(world, entity.x, entity.y):
            continue
        distance = abs(world.player.x - entity.x) + abs(world.player.y - entity.y)
        nearby.append((distance, entity))
    nearby.sort(key=lambda item: item[0])
    return nearby[:limit]


def _should_draw_entity_label(distance, focus, entity):
    focused_entity = focus.get("entity") if isinstance(focus, dict) else None
    return distance <= 1 or focused_entity is entity


def _is_entity_hovered(world, camera_x, camera_y, entity):
    mouse_x, mouse_y = world.mouse_x, world.mouse_y
    if not (0 <= mouse_x < MAP_WIDTH and 0 <= mouse_y < MAP_HEIGHT):
        return False
    return _screen_to_world(world, camera_x, camera_y, mouse_x, mouse_y) == (entity.x, entity.y)


def _player_knows_entity_identity(world, entity):
    if entity is None or entity is getattr(world, "player", None):
        return True
    if hasattr(entity, "is_identity_concealed") and entity.is_identity_concealed():
        return False
    if getattr(entity, "identity_known_to_player", None) is not None:
        return bool(entity.identity_known_to_player)

    relation_summary = getattr(world, "get_entity_relationship_summary", lambda _entity: "")(entity)
    if relation_summary:
        return True

    known_memories = getattr(getattr(getattr(world, "player", None), "knowledge", None), "known_memories", {}) or {}
    entity_id = getattr(entity, "id", None)
    if entity_id is not None:
        for memory in known_memories.values():
            if getattr(memory, "subject_id", None) == entity_id or getattr(memory, "target_id", None) == entity_id:
                return True

    return False


def _get_entity_name_parts(entity):
    raw_name = str(getattr(entity, "name", "Unknown")).replace("_", " ").strip()
    if not raw_name:
        return ("Unknown", "")
    parts = raw_name.split()
    first_name = parts[0]
    full_name = raw_name
    return first_name, full_name


def _get_entity_overhead_label(world, entity, focus, *, hovered=False):
    if not _player_knows_entity_identity(world, entity):
        return "Unknown"

    first_name, full_name = _get_entity_name_parts(entity)
    focused_entity = focus.get("entity") if isinstance(focus, dict) else None
    if hovered or focused_entity is entity:
        return full_name[:18]
    label = first_name[:10]
    tags = social_tags_for_entity(entity, world, limit=1)
    if tags and len(label) <= 8:
        label = f"{label} {tags[0][:1]}"
    return label


def _is_overlay_cell_visible(world, overlay_x, overlay_y):
    return 0 <= overlay_x < WORLD_WIDTH and 0 <= overlay_y < WORLD_HEIGHT and is_visible(world, overlay_x, overlay_y)


def _is_entity_overlay_visible(world, entity, overlay_y):
    return is_visible(world, entity.x, entity.y) and _is_overlay_cell_visible(world, entity.x, overlay_y)


def _is_sheltered_from_weather(world, world_x, world_y):
    building = getattr(world, "get_building_at", lambda _x, _y: None)(world_x, world_y)
    if building is None:
        return False
    local_x = world_x - building.global_origin_x
    local_y = world_y - building.global_origin_y
    return 0 < local_x < building.width - 1 and 0 < local_y < building.height - 1

def _get_focus_summary(world):
    standing_tile = world.get_tile_at(world.player.x, world.player.y)
    standing_on = standing_tile.name if standing_tile else "Unknown"
    nearby = _get_visible_nearby_entities(world, limit=1)
    if nearby:
        distance, entity = nearby[0]
        return standing_on, f"{world.get_entity_display_name(entity, include_relationship=True)} ({distance}t)"
    return standing_on, "No one nearby"


def _format_hover_building_name(building):
    if building is None:
        return None
    name = getattr(building, "name", "") or getattr(building, "building_type", "")
    return str(name).replace("_", " ").title() if name else None


def _is_feature_tile_name(tile_name):
    if not tile_name:
        return False
    lowered = tile_name.lower()
    feature_terms = (
        "bed", "chair", "table", "desk", "bench", "counter", "shelf", "storage",
        "barrel", "chest", "bookcase", "cabinet", "door", "window", "wall",
        "well", "forge", "loom", "anvil", "hearth", "oven", "stool", "altar",
    )
    return any(term in lowered for term in feature_terms)


def _get_hover_inspect(world, camera_x, camera_y):
    mouse_x, mouse_y = world.mouse_x, world.mouse_y
    if not (0 <= mouse_x < MAP_WIDTH and 0 <= mouse_y < MAP_HEIGHT):
        return None

    world_x, world_y = _screen_to_world(world, camera_x, camera_y, mouse_x, mouse_y)
    if not (0 <= world_x < WORLD_WIDTH and 0 <= world_y < WORLD_HEIGHT):
        return None
    if not is_visible(world, world_x, world_y):
        return None

    tile = world.get_tile_at(world_x, world_y)
    if tile is None:
        return None

    inspect = {
        "coords": (world_x, world_y),
        "tile": tile.name,
        "entity": None,
        "object": None,
    }

    interactables = getattr(world, "_get_interactables_at", lambda _x, _y: [])(world_x, world_y)
    for interactable in interactables:
        kind = interactable.get("type")
        if kind in {"npc", "animal"} and inspect["entity"] is None:
            inspect["entity"] = interactable.get("name")
        elif kind in {"item", "blueprint"} and inspect["object"] is None:
            inspect["object"] = interactable.get("name")

    building = getattr(world, "get_building_at", lambda _x, _y: None)(world_x, world_y)
    if inspect["object"] is None:
        inspect["object"] = _format_hover_building_name(building)
    if inspect["object"] is None and _is_feature_tile_name(tile.name):
        inspect["object"] = tile.name

    claim_summary = getattr(world, "get_land_claim_summary", lambda _x, _y: None)(world_x, world_y)
    if claim_summary:
        inspect["territory"] = claim_summary

    inspect["social"] = social_hover_summary(world, (world_x, world_y))

    if getattr(world, "show_autonomy_overlay", False):
        for npc in world.all_npcs:
            if npc.x == world_x and npc.y == world_y and not getattr(npc, "is_sleeping", False) and not npc.physical.is_dead:
                debug_data = getattr(npc, "debug_autonomy", {})
                task = str(debug_data.get("last_task", "unknown") or "unknown")
                path_status = debug_data.get("path_status", "none")
                moved = debug_data.get("moved_this_tick", False)
                path_len = len(npc.schedule.current_path) if npc.schedule.current_path else 0

                parts = []
                parts.append(f"{task.replace('_', ' ').capitalize()}")

                if path_status == "blocked":
                    parts.append(f"Blocked (dest: {npc.schedule.current_destination_coords})")
                elif path_status == "failed":
                    parts.append("Path failed")
                elif path_status == "moving":
                    parts.append(f"Moving (path {path_len})")
                elif path_status == "pathing":
                    parts.append(f"Has path ({path_len}), didn't move")
                else:
                    if task == "idle":
                        parts.append("No destination")
                    elif task in {"working", "sleeping", "visiting_friend", "socializing", "gathering_social"}:
                        timer = getattr(npc, "task_timer", 0)
                        parts.append(f"{timer} ticks left")

                inspect["autonomy_summary"] = ", ".join(parts)
                break

    return inspect


def _draw_hover_inspect(console, world, camera_x, camera_y, panel_x, panel_y, panel_width):
    inspect = _get_hover_inspect(world, camera_x, camera_y)
    if not inspect:
        return panel_y

    panel_inner = panel_width - 2
    y = panel_y
    console.print(x=panel_x + 1, y=y, string="Hover", fg=(255, 215, 120))
    y += 1
    world_x, world_y = inspect["coords"]
    console.print(x=panel_x + 1, y=y, string=f"At: ({world_x}, {world_y})"[:panel_inner], fg=(200, 200, 200))
    y += 1
    console.print(x=panel_x + 1, y=y, string=f"Tile: {inspect['tile']}"[:panel_inner], fg=(180, 220, 180))
    y += 1
    if inspect["entity"]:
        console.print(x=panel_x + 1, y=y, string=f"Entity: {inspect['entity']}"[:panel_inner], fg=(255, 210, 150))
        y += 1
    if inspect["object"]:
        console.print(x=panel_x + 1, y=y, string=f"Object: {inspect['object']}"[:panel_inner], fg=(170, 210, 255))
        y += 1
    if inspect.get("territory"):
        console.print(x=panel_x + 1, y=y, string=f"Land: {inspect['territory']}"[:panel_inner], fg=(190, 210, 130))
        y += 1
    if inspect.get("social"):
        console.print(x=panel_x + 1, y=y, string=f"Social: {inspect['social']}"[:panel_inner], fg=(210, 190, 230))
        y += 1
    if inspect.get("autonomy_summary"):
        console.print(x=panel_x + 1, y=y, string=f"Auto: {inspect['autonomy_summary']}"[:panel_inner], fg=(255, 100, 255))
        y += 1
    return y

def _draw_meter(console, x, y, width, label, value, maximum, fill_color, empty_color):
    maximum = max(1, maximum)
    safe_width = max(10, width - len(label) - len(f"{value}/{maximum}") - 4)
    filled_width = int(safe_width * max(0.0, min(1.0, value / maximum)))
    meter = "#" * filled_width + "-" * (safe_width - filled_width)
    console.print(x=x, y=y, string=f"{label} {meter}", fg=(210, 210, 210))
    if filled_width > 0:
        console.print(x=x + len(label) + 1, y=y, string="#" * filled_width, fg=fill_color)
    if filled_width < safe_width:
        console.print(x=x + len(label) + 1 + filled_width, y=y, string="-" * (safe_width - filled_width), fg=empty_color)
    console.print(x=x + width - len(f"{value}/{maximum}"), y=y, string=f"{value}/{maximum}", fg=(255, 255, 255))

def _draw_mini_health_bar(console, x, y, width, value, maximum, fill_color=(255, 90, 90), empty_color=(70, 25, 25)):
    """Draw a compact, label-less HP bar for overhead display above an
    entity in the world view.

    Unlike _draw_meter (used in the status panel, where there's room for a
    text label and a numeric "value/max" readout), this is stamped directly
    above a tile-sized sprite, so it's just a row of filled/empty cells.
    """
    maximum = max(1, maximum)
    ratio = max(0.0, min(1.0, value / maximum))
    filled_width = int(round(width * ratio))
    if value > 0:
        filled_width = max(1, filled_width)  # any remaining HP shows at least a sliver
    filled_width = min(width, filled_width)
    if filled_width > 0:
        console.print(x=x, y=y, string="#" * filled_width, fg=fill_color)
    if filled_width < width:
        console.print(x=x + filled_width, y=y, string="-" * (width - filled_width), fg=empty_color)


def _pulse(world, speed=14.0, low=0.55, high=1.0, phase=0.0):
    normalized = (math.sin((world.game_time / speed) + phase) + 1.0) * 0.5
    return low + (high - low) * normalized

def _lighten(color, factor):
    return _clamp_color((color[0] + (255 - color[0]) * factor, color[1] + (255 - color[1]) * factor, color[2] + (255 - color[2]) * factor))

def _animate_tile_colors(world, tile, fg_color, bg_color, world_x, world_y):
    tile_key = _get_tile_key(tile)
    time_band = ((world.game_time // 5) + world_x + world_y) % 6
    if tile_key in {"water", "deep_water"}:
        shimmer = 0.08 + (0.08 if time_band in {0, 1} else 0.0)
        return _lighten(fg_color, shimmer), _lighten(bg_color, shimmer * 0.7)
    if tile_key == "forest":
        return fg_color, _lighten(bg_color, 0.04 if time_band in {2, 3} else 0.0)
    if tile_key == "road":
        return _lighten(fg_color, 0.04 if time_band == 0 else 0.0), bg_color
    if tile_key == "wood_floor":
        return _lighten(fg_color, 0.02 if time_band == 0 else 0.0), bg_color
    if tile_key == "fire_trap_active":
        flicker = 0.12 if time_band in {0, 2, 4} else 0.02
        return _lighten(fg_color, flicker), _lighten(bg_color, flicker)
    return fg_color, bg_color

def _get_focus_target(world, camera_x, camera_y):
    focus = {"x": None, "y": None, "label": "", "actions": [], "source": "", "entity": None}

    def assign_focus(x, y, label, actions, source, entity=None):
        focus["x"] = x
        focus["y"] = y
        focus["label"] = label
        focus["actions"] = actions
        focus["source"] = source
        focus["entity"] = entity

    if world.interaction_context.get("active") and world.interaction_context.get("target_entities"):
        entity = world.interaction_context["target_entities"][world.interaction_context["selected_entity_index"]]
        assign_focus(
            world.interaction_context["x"],
            world.interaction_context["y"],
            entity["name"],
            list(world.interaction_context.get("available_actions", [])),
            "interact",
            entity,
        )
        return focus

    candidates = []
    mouse_world_x, mouse_world_y = _screen_to_world(world, camera_x, camera_y, world.mouse_x, world.mouse_y)
    if 0 <= world.mouse_x < MAP_WIDTH and 0 <= world.mouse_y < MAP_HEIGHT and is_visible(world, mouse_world_x, mouse_world_y):
        candidates.append((mouse_world_x, mouse_world_y, "mouse"))
    candidates.append((world.player.x + world.player.state.last_dx, world.player.y + world.player.state.last_dy, "facing"))

    for target_x, target_y, source in candidates:
        if not (0 <= target_x < WORLD_WIDTH and 0 <= target_y < WORLD_HEIGHT):
            continue
        tile = world.get_tile_at(target_x, target_y)
        entities = world._get_interactables_at(target_x, target_y)
        if entities:
            entity = entities[0]
            actions = list(world._get_actions_for_entity(entity))
            if actions:
                assign_focus(target_x, target_y, entity["name"], actions, source, entity)
                return focus
        if tile and is_visible(world, target_x, target_y):
            label = tile.name
            if source == "facing":
                label = f"Facing {label}"
            assign_focus(target_x, target_y, label, [], source, None)
            return focus

    return focus

def _get_log_color(message):
    lowered = message.lower()
    if "quest" in lowered or "objective" in lowered:
        return (255, 215, 120)
    if any(word in lowered for word in ["attack", "damage", "hostile", "threat", "freezing", "burning"]):
        return (255, 140, 140)
    if any(word in lowered for word in ["hello", "says", "trade", "talk"]):
        return (170, 210, 255)
    if any(word in lowered for word in ["gain", "equip", "craft", "harvest", "picked up"]):
        return (180, 235, 180)
    return (225, 225, 225)

def _draw_focus_badge(console, world, focus, camera_x, camera_y):
    if focus["x"] is None or focus["y"] is None:
        return

    screen_point = _screen_point_for_world(world, camera_x, camera_y, focus["x"], focus["y"])
    if screen_point is None:
        return
    screen_x, screen_y = screen_point

    # Only draw the floating badge above NPCs/Animals
    # focus["entity"] might be a dictionary (from _get_interactables_at) or an object (if passed directly).
    entity_obj = focus.get("entity")
    if isinstance(entity_obj, dict):
        entity_type = entity_obj.get("type", "")
        if entity_type not in ("npc", "animal"):
            return
    elif entity_obj is None:
        return # If there's no entity, don't draw a floating badge
    else:
        # It's an object, check its class or type
        if not hasattr(entity_obj, "physical") or getattr(entity_obj.physical, "is_dead", False):
            # Only living NPCs/Animals get floating text in this context
            # (Assuming living things have 'physical' components, and inanimate objects don't)
            return

    info = focus["label"][:22]
    badge_x = max(0, min(MAP_WIDTH - len(info), screen_x - (len(info) // 2)))
    badge_y = screen_y - 1 if screen_y > 1 else screen_y + 1
    _, world_badge_y = _screen_to_world(world, camera_x, camera_y, screen_x, badge_y)
    if not _is_overlay_cell_visible(world, focus["x"], world_badge_y):
        return
    pulse = _pulse(world, speed=18.0, low=0.12, high=0.22, phase=1.2)
    console.bg[screen_y, screen_x] = _lighten(tuple(console.bg[screen_y, screen_x]), pulse)
    console.print(x=badge_x, y=badge_y, string=info, fg=(235, 232, 210))

def _draw_minimap_panel(console, world, panel_x, start_y, width, height):
    console.draw_frame(x=panel_x, y=start_y, width=width, height=height, title="Minimap", clear=True, fg=(220, 220, 220), bg=(10, 12, 18))
    inner_w = max(1, width - 2)
    inner_h = max(1, height - 2)
    chunk_cols = len(world.chunks[0]) if world.chunks else 0
    chunk_rows = len(world.chunks)
    if chunk_cols == 0 or chunk_rows == 0:
        return start_y + height

    for sy in range(inner_h):
        world_y = int((sy / inner_h) * WORLD_HEIGHT)
        chunk_y = min(chunk_rows - 1, max(0, world_y // CHUNK_SIZE))
        local_y = world_y % CHUNK_SIZE
        for sx in range(inner_w):
            world_x = int((sx / inner_w) * WORLD_WIDTH)
            chunk_x = min(chunk_cols - 1, max(0, world_x // CHUNK_SIZE))
            chunk = world.chunks[chunk_y][chunk_x]

            if not chunk.is_terrain_generated:
                continue

            tile = chunk.tiles[local_y][world_x % CHUNK_SIZE]
            if tile is None:
                continue

            # If there's a village and the player has explored this chunk (or we just want to show POIs), render V or R
            # Wait, let's only show discovered POIs. If it's explored map:
            if hasattr(world, 'explored_map') and world.explored_map[world_y, world_x]:
                if chunk.poi_type == "village":
                    console.print(x=panel_x + 1 + sx, y=start_y + 1 + sy, string="V", fg=(255, 215, 0), bg=(0, 0, 0))
                elif chunk.poi_type == "ruin":
                    console.print(x=panel_x + 1 + sx, y=start_y + 1 + sy, string="R", fg=(180, 100, 200), bg=(0, 0, 0))
                else:
                    bg = _dim_color(_get_tile_background(tile), 0.9)
                    fg = _dim_color(tile.color, 0.7)
                    console.print(x=panel_x + 1 + sx, y=start_y + 1 + sy, string=".", fg=fg, bg=bg)
            else:
                # Unexplored, don't show POI but maybe show general terrain colors faintly
                bg = _dim_color(_get_tile_background(tile), 0.95)
                fg = _dim_color(tile.color, 0.8)
                console.print(x=panel_x + 1 + sx, y=start_y + 1 + sy, string=".", fg=fg, bg=bg)

    player_x = panel_x + 1 + min(inner_w - 1, int((world.player.x / max(1, WORLD_WIDTH - 1)) * inner_w))
    player_y = start_y + 1 + min(inner_h - 1, int((world.player.y / max(1, WORLD_HEIGHT - 1)) * inner_h))
    console.print(x=player_x, y=player_y, string="@", fg=(255, 245, 140), bg=(120, 55, 20))

    # Active Quest Marker
    active_quests = list(world.player.knowledge.active_quests.values())
    if active_quests and "target_location" in active_quests[0]:
        t_loc = active_quests[0]["target_location"]
        q_x = panel_x + 1 + min(inner_w - 1, int((t_loc[0] / max(1, WORLD_WIDTH - 1)) * inner_w))
        q_y = start_y + 1 + min(inner_h - 1, int((t_loc[1] / max(1, WORLD_HEIGHT - 1)) * inner_h))
        console.print(x=q_x, y=q_y, string="?", fg=(255, 100, 100), bg=(0, 0, 0))

    return start_y + height


def _ambient_speech_color(line):
    source_type = str(getattr(line, "source_type", "small_talk") or "small_talk")
    tone = str(getattr(line, "scene_tone", "") or "")
    if source_type == "warning" or tone in {"tense", "fearful"}:
        return (255, 150, 110)
    if source_type == "celebration" or tone == "celebratory":
        return (255, 225, 120)
    if tone in {"grieving", "somber"}:
        return (175, 175, 210)
    if source_type == "known_fact":
        return (180, 220, 255)
    if source_type == "social_reaction":
        return (220, 185, 230)
    return (190, 190, 205)


def _speech_fade_ratio(world, line):
    ttl = max(1, int(getattr(line, "expires_tick", 0)) - int(getattr(line, "created_tick", 0)))
    age = max(0, int(getattr(world, "game_time", 0)) - int(getattr(line, "created_tick", 0)))
    remaining = max(0, int(getattr(line, "expires_tick", 0)) - int(getattr(world, "game_time", 0)))
    fade_in = min(1.0, age / max(1, ttl * 0.2))
    fade_out = min(1.0, remaining / max(1, ttl * 0.35))
    return max(0.35, min(1.0, fade_in, fade_out))


def _draw_ambient_speech(console, world, camera_x, camera_y, max_world_lines=3):
    lines = visible_ambient_speech_lines(
        world,
        visibility_fn=is_visible,
        max_lines=max_world_lines + 2,
    )
    drawn_at: dict[tuple[int, int], int] = {}
    for line in lines[:max_world_lines]:
        text = format_ambient_speech_for_player(line, world.player, max_width=34)
        if not text:
            continue
        world_x, world_y = getattr(line, "position", (0, 0))
        stack_count = drawn_at.get((world_x, world_y), 0)
        marker_y = int(world_y) - 2 - stack_count
        if not _is_overlay_cell_visible(world, int(world_x), marker_y):
            marker_y = int(world_y) - 1 - stack_count
        if not _is_overlay_cell_visible(world, int(world_x), marker_y):
            continue
        screen_point = _screen_point_for_world(world, camera_x, camera_y, int(world_x), marker_y)
        if screen_point is None:
            continue
        screen_x, screen_y = screen_point
        draw_x = max(0, min(MAP_WIDTH - len(text), screen_x - (len(text) // 2)))
        color = _dim_color(_ambient_speech_color(line), _speech_fade_ratio(world, line))
        console.print(x=draw_x, y=screen_y, string=text, fg=color)
        drawn_at[(world_x, world_y)] = stack_count + 1


def _draw_chatter_panel(console, world, panel_y):
    lines = visible_ambient_speech_lines(world, visibility_fn=is_visible, max_lines=3)
    if not lines:
        return panel_y
    y = max(2, panel_y - len(lines) - 2)
    console.print(x=1, y=y, string="Nearby chatter", fg=(160, 160, 175), bg=(0, 0, 0))
    y += 1
    for line in lines:
        text = format_ambient_speech_for_player(line, world.player, max_width=MAP_WIDTH - 5)
        color = _dim_color(_ambient_speech_color(line), _speech_fade_ratio(world, line))
        console.print(x=2, y=y, string=("• " + text)[:MAP_WIDTH - 4], fg=color, bg=(0, 0, 0))
        y += 1
    return y

def _light_radius_for_world(world):
    return max(3, int(getattr(world, "current_fov_radius", 15)))


# Subtle per-channel color wash applied on top of the existing brightness
# dimming in _apply_lighting_and_depth, keyed by world.current_light_level_name:
# a cool/blue cast at night, a warm/orange cast at dawn and dusk. DAY and any
# unrecognized light level name are left neutral (no tint).
LIGHT_LEVEL_TINTS = {
    "DAWN": (1.12, 1.0, 0.88),
    "DUSK": (1.15, 0.95, 0.85),
    "NIGHT": (0.85, 0.92, 1.15),
    "PITCH BLACK": (0.78, 0.86, 1.22),
}


def _tint_for_light_level(color, light_level_name):
    """Apply the time-of-day color wash for `light_level_name` to `color`.

    Returns the color unchanged (clamped) for DAY or any light level name
    without a configured tint, so this is safe to call unconditionally.
    """
    multipliers = LIGHT_LEVEL_TINTS.get(light_level_name)
    if multipliers is None:
        return _clamp_color(color)
    r_mult, g_mult, b_mult = multipliers
    return _clamp_color((color[0] * r_mult, color[1] * g_mult, color[2] * b_mult))


def _apply_lighting_and_depth(console, world, camera_x, camera_y):
    light_radius = _light_radius_for_world(world)
    light_level_name = getattr(world, "current_light_level_name", "DAY")
    console_height = min(MAP_HEIGHT, getattr(console, "height", MAP_HEIGHT), console.bg.shape[0], console.fg.shape[0])
    console_width = min(MAP_WIDTH, getattr(console, "width", MAP_WIDTH), console.bg.shape[1], console.fg.shape[1])

    for y in range(console_height):
        _, map_y = _screen_to_world(world, camera_x, camera_y, 0, y)
        if not (0 <= map_y < WORLD_HEIGHT):
            continue
        for x in range(console_width):
            map_x, map_y = _screen_to_world(world, camera_x, camera_y, x, y)
            if not (0 <= map_x < WORLD_WIDTH):
                continue
            if not is_visible(world, map_x, map_y):
                continue

            tile = world.get_tile_at(map_x, map_y)
            if tile is None:
                continue

            dist = max(abs(world.player.x - map_x), abs(world.player.y - map_y))
            falloff = max(0.28, 1.0 - max(0, dist - 1) / max(4, light_radius + 2))
            edge_falloff = 0.92 - (0.12 * max(x / max(1, MAP_WIDTH - 1), y / max(1, MAP_HEIGHT - 1)))
            light_strength = max(0.2, min(1.0, falloff * edge_falloff))
            dimmed_fg = _dim_color(tuple(console.fg[y, x]), 0.65 + (0.45 * light_strength))
            dimmed_bg = _dim_color(tuple(console.bg[y, x]), 0.55 + (0.5 * light_strength))
            console.fg[y, x] = _tint_for_light_level(dimmed_fg, light_level_name)
            console.bg[y, x] = _tint_for_light_level(dimmed_bg, light_level_name)

            if getattr(tile, "blocks_fov", False):
                for shadow_dx, shadow_dy in ((1, 0), (0, 1), (1, 1)):
                    sx = x + shadow_dx
                    sy = y + shadow_dy
                    if 0 <= sx < console_width and 0 <= sy < console_height:
                        shadowed_bg = _dim_color(tuple(console.bg[sy, sx]), 0.75)
                        console.bg[sy, sx] = _tint_for_light_level(shadowed_bg, light_level_name)

def _draw_entity_markers(console, world, camera_x, camera_y, focus=None):
    for entity in itertools.chain(world.npcs, world.village_npcs):
        if getattr(entity, "is_sleeping", False):
            continue
        focused_entity = focus.get("entity") if isinstance(focus, dict) else None
        if focused_entity is not entity:
            continue
        marker = _get_entity_marker(entity, world)
        marker_world_y = entity.y - 1
        if marker is None or not _is_entity_overlay_visible(world, entity, marker_world_y):
            continue

        marker_char, marker_color = marker
        screen_point = _screen_point_for_world(world, camera_x, camera_y, entity.x, marker_world_y)
        if screen_point is not None:
            screen_x, screen_y = screen_point
            console.print(x=screen_x, y=screen_y, string=marker_char, fg=marker_color)

HEALTH_BAR_WIDTH = 5


def _draw_entity_health_bars(console, world, camera_x, camera_y, focus=None):
    """Draw a compact HP bar above any NPC that's hostile to the player or
    is the player's current focus/interaction target, so combat state is
    visible directly in the world view rather than only in the side panel.
    """
    focused_entity = focus.get("entity") if isinstance(focus, dict) else None
    for entity in itertools.chain(world.npcs, world.village_npcs):
        if getattr(getattr(entity, "physical", None), "is_dead", False):
            continue
        combat = getattr(entity, "combat", None)
        if combat is None:
            continue
        is_hostile = getattr(combat, "is_hostile_to_player", False)
        is_targeted = focused_entity is entity
        if not (is_hostile or is_targeted):
            continue

        max_hp = getattr(combat, "max_hp", None)
        hp = getattr(combat, "hp", None)
        if not max_hp or hp is None:
            continue

        bar_world_y = entity.y - 1
        if not _is_entity_overlay_visible(world, entity, bar_world_y):
            continue
        screen_point = _screen_point_for_world(world, camera_x, camera_y, entity.x, bar_world_y)
        if screen_point is None:
            continue
        screen_x, screen_y = screen_point
        bar_x = screen_x - (HEALTH_BAR_WIDTH // 2)
        _draw_mini_health_bar(console, bar_x, screen_y, HEALTH_BAR_WIDTH, hp, max_hp)

def _draw_social_indicators(console, world, camera_x, camera_y, max_markers=8):
    marked = 0
    for indicator in collect_visible_social_indicators(world, visibility_fn=is_visible):
        if marked >= max_markers:
            break
        marker_world_y = indicator.location[1] - 1
        marker_x = indicator.location[0]
        if not _is_overlay_cell_visible(world, marker_x, marker_world_y):
            marker_world_y = indicator.location[1]
        if not _is_overlay_cell_visible(world, marker_x, marker_world_y):
            continue
        screen_point = _screen_point_for_world(world, camera_x, camera_y, marker_x, marker_world_y)
        if screen_point is None:
            continue
        screen_x, screen_y = screen_point
        console.print(x=screen_x, y=screen_y, string=indicator.glyph, fg=indicator.color)
        if indicator.density in {"cluster", "crowd"} and screen_x + 1 < MAP_WIDTH:
            console.print(x=screen_x + 1, y=screen_y, string="'", fg=_dim_color(indicator.color, 0.75))
        marked += 1


def _draw_world_markers(console, world, camera_x, camera_y):
    _draw_social_indicators(console, world, camera_x, camera_y)

    # Render construction components
    for blueprint in getattr(world, "blueprints_by_id", {}).values():
        if not getattr(blueprint, "components", []):
            screen_point = _screen_point_for_world(world, camera_x, camera_y, blueprint.x, blueprint.y)
            if screen_point is not None:
                screen_x, screen_y = screen_point
                console.print(x=screen_x, y=screen_y, string="C", fg=(245, 220, 75))
            continue
        for comp in blueprint.components:
            screen_point = _screen_point_for_world(world, camera_x, camera_y, comp.x, comp.y)
            if screen_point is not None and is_visible(world, comp.x, comp.y):
                screen_x, screen_y = screen_point
                status = getattr(comp, "status", "pending")
                comp_char = "#" if status == "complete" else ("c" if status == "building" else "C")
                comp_color = (150, 150, 150) if status == "complete" else (245, 220, 75)
                console.print(x=screen_x, y=screen_y, string=comp_char, fg=comp_color)

    marked = 0
    max_markers = 18

    for dy in range(-8, 9):
        if marked >= max_markers:
            break
        for dx in range(-8, 9):
            if marked >= max_markers:
                break
            world_x = world.player.x + dx
            world_y = world.player.y + dy
            if not (0 <= world_x < WORLD_WIDTH and 0 <= world_y < WORLD_HEIGHT):
                continue
            if not is_visible(world, world_x, world_y):
                continue
            tile = world.get_tile_at(world_x, world_y)
            if tile is None:
                continue

            marker_char = None
            marker_color = None
            if tile.name == "Door":
                marker_char, marker_color = "+", (210, 180, 120)
            elif tile.name == "Well":
                marker_char, marker_color = "W", (150, 200, 255)
            elif tile.name in {"Tilled Soil", "Growing Wheat", "Wheat"}:
                marker_char, marker_color = ":", (200, 220, 140)

            if marker_char is None:
                continue

            marker_world_y = world_y - 1
            if not _is_overlay_cell_visible(world, world_x, marker_world_y):
                continue
            screen_point = _screen_point_for_world(world, camera_x, camera_y, world_x, marker_world_y)
            if screen_point is not None:
                screen_x, screen_y = screen_point
                console.print(x=screen_x, y=screen_y, string=marker_char, fg=marker_color)
                marked += 1

def draw_status_panel(console, world, camera_x, camera_y):
    """Draws the status panel on the right side of the screen."""
    panel_x = MAP_WIDTH
    panel_width = STATUS_PANEL_WIDTH
    focus = _get_focus_target(world, camera_x, camera_y)
    console.draw_frame(
        x=panel_x, y=0, width=panel_width, height=SCREEN_HEIGHT,
        title="Field Guide", clear=True, fg=(255, 255, 255), bg=(8, 10, 16)
    )

    y = 2
    time_str = _format_world_clock(world.game_time)
    season = world.seasons[world.current_season_index]
    weather = world.weather.replace("_", " ").title()
    standing_on, focus_target = _get_focus_summary(world)
    bar_width = panel_width - 3
    panel_inner = panel_width - 2

    console.print(x=panel_x + 1, y=y, string="Scene", fg=(255, 215, 120))
    y += 1
    console.print(x=panel_x + 1, y=y, string=time_str, fg=(220, 220, 220))
    y += 1
    console.print(x=panel_x + 1, y=y, string=f"{season} / {weather}", fg=(140, 170, 255))
    y += 1
    console.print(x=panel_x + 1, y=y, string=f"Standing: {standing_on}"[:panel_inner], fg=(180, 220, 180))
    y += 1
    if focus["label"]:
        focus_line = f"Focus: {focus['label']}"
    else:
        focus_line = f"Focus: {focus_target}"
    console.print(x=panel_x + 1, y=y, string=focus_line[:panel_inner], fg=(255, 210, 150))
    y += 1
    hover_y = _draw_hover_inspect(console, world, camera_x, camera_y, panel_x, y, panel_width)
    if hover_y > y:
        y = hover_y + 1
    else:
        y += 1

    y = _draw_minimap_panel(console, world, panel_x, y, panel_width, 12) + 1

    if getattr(world, "show_autonomy_overlay", False):
        console.print(x=panel_x + 1, y=y, string="Autonomy Audit", fg=(255, 100, 255))
        y += 1
        counters = getattr(world, "autonomy_counters", {})
        console.print(x=panel_x + 2, y=y, string=f"Vis/Act: {counters.get('visible', 0)}/{counters.get('active', 0)}"[:panel_inner], fg=(200, 200, 200))
        y += 1
        console.print(x=panel_x + 2, y=y, string=f"Path/Mov: {counters.get('with_path', 0)}/{counters.get('moved', 0)}"[:panel_inner], fg=(200, 200, 200))
        y += 1
        console.print(x=panel_x + 2, y=y, string=f"Idle/Wrk: {counters.get('idle', 0)}/{counters.get('at_work_home', 0)}"[:panel_inner], fg=(200, 200, 200))
        y += 1
        console.print(x=panel_x + 2, y=y, string=f"Wait/Fail: {counters.get('in_timed_activity', 0)}/{counters.get('blocked_path_failed', 0)}"[:panel_inner], fg=(200, 200, 200))
        y += 1

    console.print(x=panel_x + 1, y=y, string="Vitals", fg=(255, 215, 120))
    y += 1
    _draw_meter(console, panel_x + 1, y, bar_width, "HP", world.player.combat.hp, world.player.combat.max_hp, (255, 90, 90), (90, 35, 35))
    y += 1

    hunger_pct = min(1.0, world.player.physical.hunger / max(1, world.player.physical.max_hunger))
    hunger_color = (0, 255, 0)
    if hunger_pct > 0.5:
        hunger_color = (255, 255, 0)
    if hunger_pct > 0.8:
        hunger_color = (255, 0, 0)
    _draw_meter(
        console, panel_x + 1, y, bar_width, "HU",
        int(world.player.physical.hunger), int(world.player.physical.max_hunger),
        hunger_color, (72, 72, 20)
    )
    y += 1

    thirst_pct = min(1.0, world.player.physical.thirst / max(1, world.player.physical.max_thirst))
    thirst_color = (0, 255, 255)
    if thirst_pct > 0.5:
        thirst_color = (0, 150, 255)
    if thirst_pct > 0.8:
        thirst_color = (0, 0, 255)
    _draw_meter(
        console, panel_x + 1, y, bar_width, "TH",
        int(world.player.physical.thirst), int(world.player.physical.max_thirst),
        thirst_color, (18, 28, 72)
    )
    y += 2

    if world.player.physical.status_effects:
        console.print(x=panel_x + 1, y=y, string="Alerts", fg=(255, 215, 120))
        y += 1
        for effect in world.player.physical.status_effects:
            color = (255, 255, 255)
            if effect == "Wet":
                color = COLOR_PLAYER_STATUS_WET
            elif effect == "Freezing":
                color = COLOR_PLAYER_STATUS_FREEZING
            elif effect == "Overheating":
                color = (255, 100, 0)
            console.print(x=panel_x + 2, y=y, string=f"! {effect}"[:panel_width - 3], fg=color)
            y += 1
        y += 1

    active_quests = list(world.player.knowledge.active_quests.values())
    if active_quests:
        console.print(x=panel_x + 1, y=y, string="[Active Quest]", fg=(255, 215, 0))
        y += 1
        quest = active_quests[0]
        title_lines = textwrap.wrap(f"{quest['title']}", width=panel_width - 2)
        for line in title_lines:
            console.print(x=panel_x + 1, y=y, string=line, fg=(200, 240, 255))
            y += 1

        if quest["type"] == "fetch":
            item_key = quest["item_to_fetch_key"]
            req = quest["item_fetch_count"]
            # world.player.economic.inventory is an Inventory (dict of
            # item_key -> total count), so a plain get() already gives the
            # aggregate quantity - no need to iterate instances here.
            curr = world.player.economic.inventory.get(item_key, 0)

            color = (0, 255, 0) if curr >= req else (220, 220, 220)
            console.print(x=panel_x + 2, y=y, string=f"Fetch {ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)}: {curr}/{req}", fg=color)
            y += 1
        elif quest["type"] == "kill":
            req = quest.get("target_count", 1)
            curr = quest.get("progress", 0)
            color = (0, 255, 0) if curr >= req else (220, 220, 220)
            console.print(x=panel_x + 2, y=y, string=f"Targets Defeated: {curr}/{req}", fg=color)
            y += 1

        if len(active_quests) > 1:
            console.print(x=panel_x + 1, y=y, string=f"+ {len(active_quests)-1} more (Q)", fg=(100, 100, 100))
            y += 1
    else:
        console.print(x=panel_x + 1, y=y, string="[Active Quest]", fg=(255, 215, 0))
        y += 1
        console.print(x=panel_x + 2, y=y, string="Explore and talk", fg=(160, 160, 160))
        y += 2

    console.print(x=panel_x + 1, y=y, string="Nearby", fg=(255, 215, 120))
    y += 1
    nearby_entities = _get_visible_nearby_entities(world, limit=4)
    if not nearby_entities:
        console.print(x=panel_x + 2, y=y, string="None visible", fg=(120, 120, 120))
        y += 1
    else:
        for distance, entity in nearby_entities:
            label = "Animal" if isinstance(entity, Animal) else "NPC"
            entity_name = world.get_entity_display_name(entity, include_relationship=True)
            console.print(x=panel_x + 2, y=y, string=f"{distance}t {label}: {entity_name}"[:panel_width - 3], fg=(200, 200, 200))
            y += 1

    y += 1
    console.print(x=panel_x + 1, y=y, string="Reputation", fg=(255, 215, 120))
    y += 1
    shown_rep = False
    for faction, rep in world.player.social.reputation.items():
        if rep != 0:
            shown_rep = True
            console.print(x=panel_x + 2, y=y, string=f"{faction[:3].upper()}: {rep}"[:panel_width - 3], fg=(200, 200, 200))
            y += 1
    if not shown_rep:
        console.print(x=panel_x + 2, y=y, string="Neutral", fg=(120, 120, 120))
        y += 1

    controls_y = SCREEN_HEIGHT - 8
    console.print(x=panel_x + 1, y=controls_y, string="Legend", fg=(255, 215, 120))
    console.print(x=panel_x + 2, y=controls_y + 1, string="@ You", fg=(255, 245, 140))
    console.print(x=panel_x + 2, y=controls_y + 2, string="! hostile  ? quest", fg=(170, 200, 255))
    console.print(x=panel_x + 2, y=controls_y + 3, string="$ trader   * loot", fg=(170, 220, 170))
    console.print(x=panel_x + 2, y=controls_y + 4, string="Pulse = focus", fg=(220, 220, 220))
    console.print(x=panel_x + 2, y=controls_y + 5, string="E/T act  + civic", fg=(220, 220, 220))

def draw_minimap(console, world):
    """Draws a minimap in the corner of the screen."""
    # Draw frame for the minimap
    console.draw_frame(x=MINIMAP_X, y=MINIMAP_Y, width=MINIMAP_WIDTH, height=MINIMAP_HEIGHT,
                       title="World Map", clear=True, fg=(255, 255, 255), bg=(0, 0, 0))

    world_map = world.get_world_map_data() # This method needs to exist in World

    for y in range(MINIMAP_HEIGHT - 2):
        for x in range(MINIMAP_WIDTH - 2):
            map_x = int((x / (MINIMAP_WIDTH - 2)) * world.chunk_width)
            map_y = int((y / (MINIMAP_HEIGHT - 2)) * world.chunk_height)

            if 0 <= map_y < world.chunk_height and 0 <= map_x < world.chunk_width:
                tile_info = world_map[map_y][map_x]
                char, color, bg_color = tile_info['char'], tile_info['color'], tile_info['bg_color']

                console.print(x=MINIMAP_X + 1 + x, y=MINIMAP_Y + 1 + y, string=char, fg=color, bg=bg_color)

    # Draw player position on minimap
    player_map_x = int((world.player.x / world.width) * (MINIMAP_WIDTH - 2))
    player_map_y = int((world.player.y / world.height) * (MINIMAP_HEIGHT - 2))
    console.print(x=MINIMAP_X + 1 + player_map_x, y=MINIMAP_Y + 1 + player_map_y,
                  string="@", fg=(255, 0, 0))


def draw_cursor_info(console, world, camera_x, camera_y):
    """Legacy no-op kept for compatibility; hover inspect now lives in the status panel."""
    return

def is_visible(world, x, y):
    """Checks if a world coordinate is within the player's local FOV map."""
    fov_map = getattr(world, 'player_fov_map', None)
    if fov_map is None:
        # Fallback if FOV system isn't fully initialized
        return True

    if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
        return fov_map[y, x]
    return False

def _draw_visual_effect(console, world, effect, camera_x, camera_y):
    effect_type = getattr(effect, "effect_type", None)
    draw_point = _screen_point_for_world(world, camera_x, camera_y, int(round(getattr(effect, "x", 0))), int(round(getattr(effect, "y", 0))))
    if draw_point is None:
        return
    draw_x, draw_y = draw_point

    if effect_type == "floating_text":
        console.print(x=draw_x, y=draw_y, string=getattr(effect, "text", ""), fg=getattr(effect, "color", (255, 255, 255)))
    elif effect_type == "projectile":
        console.print(x=draw_x, y=draw_y, string=getattr(effect, "char", "*"), fg=getattr(effect, "color", (255, 255, 0)))
    elif effect_type == "hit_flash":
        shake_fn = getattr(effect, "shake_offset", None)
        offset_x, offset_y = shake_fn() if shake_fn else (0, 0)
        console.print(
            x=draw_x + offset_x,
            y=draw_y + offset_y,
            string="*",
            fg=getattr(effect, "color", (255, 60, 60)),
        )
    elif effect_type == "particle_burst":
        fade_fn = getattr(effect, "fade_ratio", None)
        fade = fade_fn() if fade_fn else 1.0
        color = _dim_color(getattr(effect, "color", (200, 200, 200)), 0.35 + (0.65 * fade))
        for offset_x, offset_y, char in getattr(effect, "particles", []):
            px, py = draw_x + offset_x, draw_y + offset_y
            if 0 <= px < MAP_WIDTH and 0 <= py < MAP_HEIGHT:
                console.print(x=px, y=py, string=char, fg=color)

def _draw_active_game_state_menu(console, world):
    """Draw whichever menu draw_*_menu function matches world.game_state,
    if any. Extracted out of draw() so it can be wrapped with a fade-in
    ramp (see _draw_active_game_state_menu_with_fade) without duplicating
    this dispatch list."""
    if world.game_state == "CRAFTING_MENU":
        draw_crafting_menu(console, world)

    if world.game_state == "BUILDING_MENU":
        draw_building_menu(console, world)

    if world.game_state == "INFO_MENU":
        draw_info_menu(console, world)

    if world.game_state == "INVENTORY_MENU":
        draw_inventory_menu(console, world)

    if world.game_state == "KNOWLEDGE_MENU":
        draw_knowledge_menu(console, world)

    if world.game_state == "QUEST_MENU":
        draw_quest_menu(console, world)

    if world.game_state == "NOTICEBOARD_MENU":
        draw_noticeboard_menu(console, world)

    if world.game_state == "COMPANY_LEDGER_MENU":
        draw_company_ledger_menu(console, world)

    if world.game_state == "SOCIAL_MENU":
        draw_social_menu(console, world)

    if world.game_state == "GOVERNANCE_MENU":
        draw_governance_menu(console, world)

    if world.game_state == "DIALOGUE" or world.chat_ui_active:
        draw_dialogue_menu(console, world)

    if world.game_state == "BOOK_READING":
        draw_book_reading_ui(console, world)

    if world.game_state == "TRADE_MENU" or world.trade_ui_active:
        draw_trade_menu(console, world)

    if world.game_state == "HELP_MENU":
        draw_help_menu(console)


def _draw_active_game_state_menu_with_fade(console, world, fade_ratio):
    """Draw the active game_state menu (if any), fading it in from the
    world view underneath over the first few frames after it opens.

    tcod menus are drawn as plain console.print/print_box/draw_frame calls
    with no shared opacity concept, and there are ~14 unrelated menu draw
    functions dispatched above - threading an opacity parameter through
    every one of them (and every console.print call inside each) would be
    a large, risky change for a "few frames of fade" polish pass. Instead
    this snapshots the console's fg/bg buffers before the menu draws (i.e.
    the already-rendered world view/status panel), lets the menu draw
    normally on top, then linearly blends the "before" and "after" buffers
    by fade_ratio. At fade_ratio >= 1.0 - the steady state once a menu has
    been open past the fade window, and the default when no caller passes
    a ratio at all - this is a no-op passthrough with no snapshot/blend
    cost, so callers that don't care about fades (including every existing
    test that calls draw() directly) are unaffected.
    """
    if fade_ratio >= 1.0 or not hasattr(console, "fg") or not hasattr(console, "bg"):
        _draw_active_game_state_menu(console, world)
        return

    fg_before = console.fg.copy()
    bg_before = console.bg.copy()
    _draw_active_game_state_menu(console, world)

    ratio = max(0.0, fade_ratio)
    console.fg[:] = fg_before + (console.fg.astype("int16") - fg_before.astype("int16")) * ratio
    console.bg[:] = bg_before + (console.bg.astype("int16") - bg_before.astype("int16")) * ratio


def draw(console, world, camera_x, camera_y, menu_fade_ratio=1.0):
    """Draws the main game screen."""
    console.clear()

    # Draw the map
    fov_map = getattr(world, 'player_fov_map', None)
    exp_map = world.explored_map

    view_width, view_height = _get_world_view_dimensions(world)

    for map_y in range(camera_y, min(WORLD_HEIGHT, camera_y + view_height)):
        if not (0 <= map_y < WORLD_HEIGHT):
            continue

        chunk_y = map_y // CHUNK_SIZE
        local_y = map_y % CHUNK_SIZE
        chunk_row = world.chunks[chunk_y]

        for map_x in range(camera_x, min(WORLD_WIDTH, camera_x + view_width)):
            if not (0 <= map_x < WORLD_WIDTH):
                continue

            chunk_x = map_x // CHUNK_SIZE
            chunk = chunk_row[chunk_x]

            if not chunk.is_terrain_generated:
                world._generate_chunk_detail(chunk, chunk_x, chunk_y)

            tile = chunk.tiles[local_y][map_x % CHUNK_SIZE]

            if tile:
                is_in_fov = fov_map[map_y, map_x] if fov_map is not None else True
                tile_key = _get_tile_key(tile)
                bg_color = _get_tile_background(tile)
                fg_color = tile.color
                fg_color, bg_color = _tune_floor_colors(tile_key, fg_color, bg_color)
                fg_color, bg_color = _animate_tile_colors(world, tile, fg_color, bg_color, map_x, map_y)
                if is_in_fov:
                    _draw_world_tile(console, world, camera_x, camera_y, map_x, map_y, tile, fg_color, bg_color)
                    exp_map[map_y, map_x] = True
                elif exp_map[map_y, map_x]:
                    _draw_world_tile(
                        console,
                        world,
                        camera_x,
                        camera_y,
                        map_x,
                        map_y,
                        tile,
                        _dim_color(fg_color, 0.45),
                        _dim_color(bg_color, 0.5),
                    )

    _apply_lighting_and_depth(console, world, camera_x, camera_y)
    _draw_items(console, world, camera_x, camera_y)
    _draw_entities(console, world, camera_x, camera_y)
    # Draw path visualizer
    if hasattr(world.player.state, 'current_path') and world.player.state.current_path:
        for px, py in world.player.state.current_path:
            screen_point = _screen_point_for_world(world, camera_x, camera_y, px, py)
            if screen_point is not None and is_visible(world, px, py):
                screen_x, screen_y = screen_point
                console.print(x=screen_x, y=screen_y, string="•", fg=(0, 255, 0))

    # Draw Visual Effects
    for effect in world.visual_effects:
        _draw_visual_effect(console, world, effect, camera_x, camera_y)

    focus = _get_focus_target(world, camera_x, camera_y)
    _draw_entity_health_bars(console, world, camera_x, camera_y, focus)
    _draw_entity_markers(console, world, camera_x, camera_y, focus)
    _draw_world_markers(console, world, camera_x, camera_y)
    _draw_ambient_speech(console, world, camera_x, camera_y)
    for distance, entity in _get_visible_nearby_entities(world, limit=3):
        if not _should_draw_entity_label(distance, focus, entity):
            continue
        label_world_y = entity.y - 2
        if label_world_y < 0 or not _is_entity_overlay_visible(world, entity, label_world_y):
            label_world_y = entity.y - 1
        if not _is_entity_overlay_visible(world, entity, label_world_y):
            continue
        screen_point = _screen_point_for_world(world, camera_x, camera_y, entity.x, label_world_y)
        if screen_point is not None:
            screen_x, screen_y = screen_point
            label = _get_entity_overhead_label(
                world,
                entity,
                focus,
                hovered=_is_entity_hovered(world, camera_x, camera_y, entity),
            )
            label_x = max(0, min(MAP_WIDTH - len(label), screen_x - (len(label) // 2)))
            console.print(x=label_x, y=screen_y, string=label, fg=(142, 148, 156))

    current_tile = world.get_tile_at(world.player.x, world.player.y)
    area_label = current_tile.name if current_tile else "Unknown"
    hud_text = f"@ {area_label}  [{world.player.x},{world.player.y}]  {world.weather.replace('_', ' ').title()}"
    console.print(x=1, y=1, string=hud_text[:MAP_WIDTH - 2], fg=(255, 255, 255), bg=(0, 0, 0))

    _draw_focus_badge(console, world, focus, camera_x, camera_y)

    draw_status_panel(console, world, camera_x, camera_y)

    # Draw chat/interaction UI if active
    if world.interaction_context["active"]:
        draw_interaction_menu(console, world)

    _draw_active_game_state_menu_with_fade(console, world, menu_fade_ratio)

    # Draw weather overlay
    draw_weather_overlay(console, world, camera_x, camera_y)

    # Draw chat log at the bottom
    y = SCREEN_HEIGHT - 6
    _draw_chatter_panel(console, world, y)
    console.draw_frame(x=0, y=y, width=MAP_WIDTH, height=6, title="Log",
                       clear=True, fg=(255, 255, 255), bg=(6, 8, 12))
    for i, message in enumerate(world.chat_log[-4:]):
        console.print(x=1, y=y + 1 + i, string=message[:MAP_WIDTH - 2], fg=_get_log_color(message))

def draw_weather_overlay(console, world, camera_x, camera_y):
    """Draws a simple screen overlay based on the current weather."""
    if world.weather in ["clear", "heatwave"]:
        return

    import random

    # Simple stateless particle effect using map coordinates hash
    weather_def = WEATHER_DEFINITIONS.get(world.weather, {})
    weather_char = weather_def.get("char", " ")
    char = chr(weather_char) if isinstance(weather_char, int) else str(weather_char)

    if world.weather == "rain" or world.weather == "storm":
        color = weather_def.get("color", (100, 150, 255) if world.weather == "rain" else (150, 150, 200))
        density = 0.1 if world.weather == "rain" else 0.3
    elif world.weather == "snow":
        color = weather_def.get("color", (255, 255, 255))
        density = 0.05
    else:
        return

    # Offset by time to create movement
    time_offset = world.game_time % 100

    view_width, view_height = _get_world_view_dimensions(world)
    for world_y in range(camera_y, min(WORLD_HEIGHT, camera_y + view_height)):
        for world_x in range(camera_x, min(WORLD_WIDTH, camera_x + view_width)):
            if _is_sheltered_from_weather(world, world_x, world_y):
                continue
            # Using coordinate hash to generate deterministic pseudo-random layout that changes with time
            h = hash((world_x + time_offset, world_y + time_offset)) % 1000
            if h < density * 1000:
                if is_visible(world, world_x, world_y):
                    rect = _world_to_screen_rect(world, camera_x, camera_y, world_x, world_y)
                    _draw_zoomed_glyph(console, rect, char, fg=color)

def draw_interaction_menu(console, world):
    """Draws the context-sensitive interaction menu."""
    ctx = world.interaction_context
    x, y = world.mouse_x, world.mouse_y

    # Find longest action to determine menu width
    longest_action = 0
    if ctx["available_actions"]:
        longest_action = max(len(action) for action in ctx["available_actions"])
    width = max(15, longest_action + 4)
    height = len(ctx["available_actions"]) + 2

    # Adjust position to keep menu on screen
    if x + width > MAP_WIDTH:
        x = MAP_WIDTH - width
    if y + height > MAP_HEIGHT:
        y = MAP_HEIGHT - height

    console.draw_frame(x=x, y=y, width=width, height=height,
                       title=f"Interact: {ctx['target_entities'][ctx['selected_entity_index']]['name']}",
                       clear=True, fg=(255, 255, 255), bg=(50, 50, 50))

    for i, action in enumerate(ctx["available_actions"]):
        text_color = (255, 255, 255)
        if i == ctx["selected_action_index"]:
            text_color = (0, 255, 255) # Highlight selected action
        console.print(x=x + 1, y=y + 1 + i, string=action, fg=text_color)

def draw_crafting_menu(console, world):
    """Draws the crafting menu UI."""
    menu_width = 50
    x = (MAP_WIDTH - menu_width) // 2
    all_recipes = world.crafting_menu_context.get("all_recipes", [])
    num_recipes = len(all_recipes)
    menu_height = min(30, num_recipes + 4) # Limit height
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Crafting", clear=True)

    if not all_recipes:
        console.print_box(x=x+1, y=y+1, width=menu_width-2, height=menu_height-2,
                          string="No recipes available.", fg=(128, 128, 128))
        return

    selected_index = world.crafting_menu_context.get("selected_recipe_index", 0)
    scroll_offset = world.crafting_menu_context.get("scroll_offset", 0)
    display_height = menu_height - 2

    # Adjust scroll offset if selection is out of view
    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + display_height:
        scroll_offset = selected_index - display_height + 1
    world.crafting_menu_context["scroll_offset"] = scroll_offset

    # Display recipes
    for i in range(display_height):
        list_index = scroll_offset + i
        if list_index < num_recipes:
            recipe_key = all_recipes[list_index]
            item_def = TILE_DEFINITIONS.get(recipe_key, {}) # Using TILE_DEFINITIONS, assuming item defs are there.
            item_name = item_def.get("name", recipe_key)
            can_craft = world.player_can_craft(recipe_key)
            color = (255, 255, 255) if can_craft else (128, 128, 128)
            if list_index == selected_index:
                color = (0, 255, 255)
            row_y = y + 1 + i
            icon_drawn = _draw_item_icon(console, x + 2, row_y, recipe_key)
            text_x = x + 4 if icon_drawn else x + 2
            console.print(x=text_x, y=row_y, string=item_name, fg=color)

    # Display selected recipe details
    if 0 <= selected_index < num_recipes:
        details_x = x + menu_width
        details_width = 40
        details_height = 20
        console.draw_frame(x=details_x, y=y, width=details_width, height=details_height, title="Recipe Details", clear=True)

        selected_key = all_recipes[selected_index]
        item_def = TILE_DEFINITIONS.get(selected_key, {})
        recipe = item_def.get("crafting_recipe", {})

        detail_y = y + 2
        console.print(x=details_x + 2, y=detail_y, string=f"Requires:", fg=(255, 255, 0))
        detail_y += 1
        for res_key, qty in recipe.items():
            res_def = TILE_DEFINITIONS.get(res_key, {})
            res_name = res_def.get("name", res_key)
            has_enough = world.player.has_item(res_key, qty)
            color = (255, 255, 255) if has_enough else (255, 0, 0)
            console.print(x=details_x + 3, y=detail_y, string=f"- {res_name}: {qty}", fg=color)
            detail_y += 1

        req_station = item_def.get("required_workstation")
        if req_station:
            detail_y += 1
            is_near = world._is_player_near_workstation(req_station)
            color = (255, 255, 255) if is_near else (255, 0, 0)
            console.print(x=details_x + 2, y=detail_y, string=f"Needs: {req_station}", fg=color)

def draw_building_menu(console, world):
    """Draws the building menu UI."""
    menu_width = 50
    x = (MAP_WIDTH - menu_width) // 2
    all_recipes = world.building_menu_context.get("all_recipes", [])
    num_recipes = len(all_recipes)
    menu_height = min(30, num_recipes + 4)
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Construction", clear=True)

    if not all_recipes:
        console.print_box(x=x+1, y=y+1, width=menu_width-2, height=menu_height-2,
                          string="No construction options.", fg=(128, 128, 128))
        return

    selected_index = world.building_menu_context.get("selected_recipe_index", 0)
    scroll_offset = world.building_menu_context.get("scroll_offset", 0)
    display_height = menu_height - 2

    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + display_height:
        scroll_offset = selected_index - display_height + 1
    world.building_menu_context["scroll_offset"] = scroll_offset

    for i in range(display_height):
        list_index = scroll_offset + i
        if list_index < num_recipes:
            recipe_key = all_recipes[list_index]
            recipe = CONSTRUCTION_RECIPES.get(recipe_key, {})
            name = recipe.get("name", recipe_key)

            # Check if player has materials
            can_build = True
            for mat_key, mat_qty in recipe.get("materials", {}).items():
                if not world.player.has_item(mat_key, mat_qty):
                    can_build = False
                    break

            color = (255, 255, 255) if can_build else (128, 128, 128)
            if list_index == selected_index:
                color = (0, 255, 255)
            console.print(x=x + 2, y=y + 1 + i, string=name, fg=color)

    # Display details
    if 0 <= selected_index < num_recipes:
        details_x = x + menu_width
        details_width = 40
        details_height = 20
        console.draw_frame(x=details_x, y=y, width=details_width, height=details_height, title="Build Details", clear=True)

        selected_key = all_recipes[selected_index]
        recipe = CONSTRUCTION_RECIPES.get(selected_key, {})

        detail_y = y + 2
        console.print(x=details_x + 2, y=detail_y, string=f"Materials:", fg=(255, 255, 0))
        detail_y += 1
        for mat_key, mat_qty in recipe.get("materials", {}).items():
            item_def = ITEM_DEFINITIONS.get(mat_key)
            tile_def = TILE_DEFINITIONS.get(mat_key)
            mat_name = (
                (item_def or {}).get("name")
                or (tile_def or {}).get("name")
                or mat_key.replace("_", " ").title()
            )
            has_enough = world.player.has_item(mat_key, mat_qty)
            color = (255, 255, 255) if has_enough else (255, 0, 0)
            console.print(x=details_x + 3, y=detail_y, string=f"- {mat_name}: {mat_qty}", fg=color)
            detail_y += 1

        description = recipe.get("description", "")
        if description:
            detail_y += 1
            console.print_box(x=details_x + 2, y=detail_y, width=details_width-4, height=5, string=description, fg=(200, 200, 200))

def draw_noticeboard_menu(console, world):
    """Draw the TownBoard hauling notices and player-claimed tasks."""
    menu_width = 66
    menu_height = 20
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2
    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Noticeboard", clear=True)

    if world.noticeboard_menu_context.get("mode") == "post_job":
        building = world._get_job_posting_building()
        role_options = world._get_job_posting_role_options(building)
        selected_role_index = world.noticeboard_menu_context.get("selected_role_index", 0)
        selected_role = role_options[selected_role_index] if role_options else "No valid roles"
        wage = world.get_job_posting_wage()
        building_name = str(getattr(building, "building_type", "Unassigned")).replace("_", " ").title()

        console.print(x=x + 2, y=y + 2, string="Post Job Listing", fg=(255, 255, 0))
        console.print(x=x + 2, y=y + 4, string=f"Business: {building_name}"[: menu_width - 4], fg=(255, 255, 255))
        console.print(x=x + 2, y=y + 5, string=f"Role: {selected_role}"[: menu_width - 4], fg=(0, 255, 255))
        console.print(x=x + 2, y=y + 6, string=f"Daily Wage: {wage} coins"[: menu_width - 4], fg=(255, 255, 255))
        console.print(
            x=x + 2,
            y=y + 8,
            string="Up/Down role  Left/Right wage  Tab building  Enter post  Esc cancel"[: menu_width - 4],
            fg=(180, 180, 180),
        )

        current_y = y + 10
        console.print(x=x + 2, y=current_y, string="Available Roles:", fg=(255, 255, 0))
        for index, role in enumerate(role_options[: menu_height - 13]):
            color = (0, 255, 255) if index == selected_role_index else (255, 255, 255)
            console.print(x=x + 4, y=current_y + 1 + index, string=role[: menu_width - 8], fg=color)
        return

    task_ids = world.noticeboard_menu_context.get("task_ids", [])
    selected_index = world.noticeboard_menu_context.get("selected_task_index", 0)
    if not task_ids:
        console.print_box(x=x + 2, y=y + 2, width=menu_width - 4, height=menu_height - 6, string="No active notices.", fg=(180, 180, 180))
        console.print(x=x + 2, y=y + menu_height - 2, string="P = Post Job", fg=(180, 180, 180))
        return

    display_height = menu_height - 4
    scroll_offset = world.noticeboard_menu_context.get("scroll_offset", 0)
    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + display_height:
        scroll_offset = selected_index - display_height + 1
    world.noticeboard_menu_context["scroll_offset"] = scroll_offset

    for i in range(display_height):
        list_index = scroll_offset + i
        if list_index >= len(task_ids):
            break
        notice_id = task_ids[list_index]
        if notice_id.startswith("job:"):
            job_task = world.town_board.get_employment_task(notice_id.split(":", 1)[1])
            if job_task is None:
                continue
            building = world.buildings_by_id.get(job_task.target_building_id)
            building_name = str(getattr(building, "building_type", "Unknown")).replace("_", " ")
            line = f"JOB: {job_task.profession_role} @ {building_name} - {job_task.daily_wage}/day"
            color = (0, 255, 255) if list_index == selected_index else (144, 220, 255)
        elif notice_id.startswith("need:"):
            need_id = notice_id.split(":", 1)[1]
            need = next((n for n in getattr(world.town_board, "economic_needs", []) if n.id == need_id), None)
            if need is None:
                continue
            line = f"NEED: {need.description}"
            color = (0, 255, 255) if list_index == selected_index else (255, 100, 100)
        else:
            task = world.town_board.get_task(notice_id.split(":", 1)[1] if ":" in notice_id else notice_id)
            if task is None:
                continue
            blueprint = world.blueprints_by_id.get(task.blueprint_id)
            if blueprint is None:
                continue
            status = "Claimed" if task.assigned_entity_id == world.player.id else "Open"
            line = f"HAUL: {task.item_key.replace('_', ' ')} -> {blueprint.target_build.replace('_', ' ')} @ ({task.destination_x},{task.destination_y}) [{status}]"
            color = (0, 255, 255) if list_index == selected_index else ((255, 255, 255) if status == "Open" else (255, 215, 0))
        console.print(x=x + 2, y=y + 2 + i, string=line[:menu_width - 4], fg=color)
    console.print(x=x + 2, y=y + menu_height - 2, string="Enter = claim haul notice   P = Post Job"[: menu_width - 4], fg=(180, 180, 180))

def draw_company_ledger_menu(console, world):
    """Draw the ledger for a player-owned building."""
    menu_width = 74
    menu_height = 22
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2
    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Company Ledger", clear=True)

    building = world.get_company_ledger_building()
    if building is None:
        console.print_box(
            x=x + 2,
            y=y + 2,
            width=menu_width - 4,
            height=menu_height - 4,
            string="No owned property is currently linked to this ledger.",
            fg=(180, 180, 180),
        )
        return

    building_name = str(getattr(building, "building_type", "business")).replace("_", " ").title()
    building_cash = world._get_trade_money_balance(building)
    player_cash = world._get_trade_money_balance(world.player)
    selected_action_index = world.company_ledger_menu_context.get("selected_action_index", 0)
    amount_options = world.company_ledger_menu_context.get("amount_options", [1, 10, 50, 100])
    amount = world.get_company_ledger_amount()

    console.print(x=x + 2, y=y + 2, string=f"Property: {building_name}", fg=(255, 255, 0))
    console.print(x=x + 2, y=y + 3, string=f"Company Cash: {building_cash} coins", fg=(255, 255, 255))
    console.print(x=x + 2, y=y + 4, string=f"Your Wallet: {player_cash} coins", fg=(255, 255, 255))
    console.print(
        x=x + 2,
        y=y + 5,
        string=f"Transfer Amount: {amount}  (Left/Right to adjust)",
        fg=(180, 180, 180),
    )

    action_labels = ["Deposit Funds", "Withdraw Funds"]
    for index, label in enumerate(action_labels):
        color = (0, 255, 255) if index == selected_action_index else (255, 255, 255)
        console.print(x=x + 2, y=y + 7 + index, string=label, fg=color)

    amount_label = " / ".join(
        f"[{option}]" if option == amount else str(option)
        for option in amount_options
    )
    console.print(x=x + 2, y=y + 10, string=f"Quick Amounts: {amount_label}"[: menu_width - 4], fg=(160, 160, 160))
    console.print(x=x + 2, y=y + 12, string="Stock:", fg=(255, 255, 0))

    stock = world.get_company_ledger_stock_snapshot(building)
    if not stock:
        console.print(x=x + 4, y=y + 13, string="No stock on hand.", fg=(180, 180, 180))
    else:
        max_rows = menu_height - 15
        for row_index, (item_key, quantity) in enumerate(stock[:max_rows]):
            item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key.replace("_", " ").title())
            console.print(
                x=x + 4,
                y=y + 13 + row_index,
                string=f"- {item_name}: {quantity}"[: menu_width - 8],
                fg=(255, 255, 255),
            )

def draw_social_menu(console, world):
    """Draw the player social interaction menu for the selected NPC."""
    menu_width = 74
    menu_height = 24
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2
    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Social", clear=True)

    npc = world.get_social_menu_target()
    if npc is None:
        console.print_box(
            x=x + 2,
            y=y + 2,
            width=menu_width - 4,
            height=menu_height - 4,
            string="No social target is available.",
            fg=(180, 180, 180),
        )
        return

    attitude_label, attitude_score = world.get_social_attitude_label(npc)
    profession = getattr(getattr(npc, "economic", None), "profession", "Unemployed") or "Unemployed"
    mode = world.social_menu_context.get("mode", "root")

    portrait_x = x + menu_width - 2 - PORTRAIT_ZOOM
    portrait_y = y + 2
    _draw_entity_portrait(console, portrait_x, portrait_y, npc)

    console.print(x=x + 2, y=y + 2, string=f"Name: {npc.name}", fg=(255, 255, 0))
    console.print(x=x + 2, y=y + 3, string=f"Job: {profession}", fg=(220, 220, 220))
    console.print(x=x + 2, y=y + 4, string=f"Attitude: {attitude_label} ({attitude_score:+d})", fg=(200, 255, 255))

    if mode == "root":
        console.print(x=x + 2, y=y + 6, string="Choose how you want to approach them:", fg=(180, 180, 180))
        for index, label in enumerate(world.get_social_menu_actions()):
            color = (0, 255, 255) if index == world.social_menu_context.get("selected_action_index", 0) else (255, 255, 255)
            console.print(x=x + 4, y=y + 8 + index, string=label, fg=color)
        console.print(
            x=x + 2,
            y=y + menu_height - 2,
            string="Up/Down = select   Enter = confirm   Esc = close",
            fg=(150, 150, 150),
        )
        return

    if mode == "gift":
        options = world.get_social_gift_options()
        title = f"Give Gift   Wallet: {world.player.economic.money} coins"
    else:
        options = world.get_player_gossip_options()
        title = "Share Gossip"
    console.print(x=x + 2, y=y + 6, string=title[: menu_width - 4], fg=(180, 180, 180))

    if not options:
        empty_text = "You have nothing available to gift." if mode == "gift" else "You do not know any memories worth sharing."
        console.print_box(
            x=x + 2,
            y=y + 8,
            width=menu_width - 4,
            height=menu_height - 12,
            string=empty_text,
            fg=(180, 180, 180),
        )
        console.print(
            x=x + 2,
            y=y + menu_height - 2,
            string="Esc = back",
            fg=(150, 150, 150),
        )
        return

    selected_index = max(0, min(len(options) - 1, world.social_menu_context.get("selected_option_index", 0)))
    display_height = menu_height - 10
    scroll_offset = world.social_menu_context.get("scroll_offset", 0)
    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + display_height:
        scroll_offset = selected_index - display_height + 1
    world.social_menu_context["scroll_offset"] = scroll_offset

    for row in range(display_height):
        list_index = scroll_offset + row
        if list_index >= len(options):
            break
        option = options[list_index]
        if mode == "gift":
            line = f"{option['label']}  (value {option.get('value', 0)})"
        else:
            headline = option.headline or option.event_type.replace("_", " ").title()
            line = f"{headline}  [{option.importance_score}]"
        color = (0, 255, 255) if list_index == selected_index else (255, 255, 255)
        console.print(x=x + 2, y=y + 8 + row, string=line[: menu_width - 4], fg=color)

    console.print(
        x=x + 2,
        y=y + menu_height - 2,
        string="Up/Down = select   Enter = confirm   Esc = back",
        fg=(150, 150, 150),
    )

def draw_governance_menu(console, world):
    """Draw the Town Hall governance menu."""
    menu_width = 78
    menu_height = 25
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2
    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Governance", clear=True)

    town_hall = world.get_town_hall_building()
    treasury = world._get_trade_money_balance(town_hall) if town_hall is not None else 0
    tax_rate = int(float(getattr(world.politics, "tax_rate", 0.10)) * 100)
    console.print(x=x + 2, y=y + 2, string=f"Treasury: {treasury} coins", fg=(255, 255, 0))
    console.print(x=x + 2, y=y + 3, string=f"Tax Rate: {tax_rate}%", fg=(220, 220, 220))
    console.print(x=x + 2, y=y + 4, string=f"Mayor: {world.get_office_holder_name('Mayor')}", fg=(200, 255, 255))
    console.print(x=x + 2, y=y + 5, string=f"Captain: {world.get_office_holder_name('Captain of the Guard')}", fg=(200, 255, 255))

    ctx = world.governance_menu_context
    mode = ctx.get("mode", "root")
    if mode == "root":
        actions = world.get_governance_actions()
        for index, label in enumerate(actions):
            color = (0, 255, 255) if index == ctx.get("selected_action_index", 0) else (255, 255, 255)
            console.print(x=x + 4, y=y + 8 + index, string=label, fg=color)
        console.print(
            x=x + 2,
            y=y + menu_height - 2,
            string="Up/Down = select   Left/Right = adjust taxes   Enter = confirm   Esc = close",
            fg=(150, 150, 150),
        )
        return

    targets = world.get_governance_targets()
    pending_action = ctx.get("pending_action", "Issue Order")
    console.print(x=x + 2, y=y + 8, string=f"{pending_action}: choose a target", fg=(180, 180, 180))
    if not targets:
        console.print(x=x + 4, y=y + 10, string="No valid targets.", fg=(180, 180, 180))
        return

    selected_index = max(0, min(len(targets) - 1, ctx.get("selected_target_index", 0)))
    display_height = menu_height - 12
    scroll_offset = ctx.get("scroll_offset", 0)
    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + display_height:
        scroll_offset = selected_index - display_height + 1
    ctx["scroll_offset"] = scroll_offset

    for row in range(display_height):
        list_index = scroll_offset + row
        if list_index >= len(targets):
            break
        target = targets[list_index]
        profession = getattr(getattr(target, "economic", None), "profession", "Citizen") or "Citizen"
        line = f"{target.name} (ID {target.id}) - {profession}"
        color = (0, 255, 255) if list_index == selected_index else (255, 255, 255)
        console.print(x=x + 2, y=y + 10 + row, string=line[: menu_width - 4], fg=color)

    console.print(
        x=x + 2,
        y=y + menu_height - 2,
        string="Up/Down = select   Enter = issue order   Esc = back",
        fg=(150, 150, 150),
    )

def draw_info_menu(console, world):
    """Draws the player information menu (stats and inventory)."""
    menu_width = 60
    x = (MAP_WIDTH - menu_width) // 2
    menu_height = 40
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Character Information", clear=True)

    # Stats section
    stat_y = y + 2
    console.print(x=x + 2, y=stat_y, string=f"Fame: {world.player.social.fame}", fg=(255, 255, 0))
    stat_y += 1
    console.print(x=x + 2, y=stat_y, string=f"Infamy: {world.player.social.infamy}", fg=(255, 0, 0))
    stat_y += 1

    title = world.player.social.title
    if not title:
        # Fallback to career title or profession
        title = world.player.career.display_title()
        if not title:
            prof = str(getattr(world.player.economic, "profession", "Unemployed")).strip()
            if prof and prof.lower() not in {"unemployed", "creature"}:
                title = prof

    if title:
        console.print(x=x + 2, y=stat_y, string=f"Title: {title}", fg=(0, 255, 255))
        stat_y += 1

    if world.player.economic.job_building_id:
        village = None
        building = world.buildings_by_id.get(world.player.economic.job_building_id)
        if building and building.settlement_id:
            atlas = getattr(world, "atlas", None)
            if atlas and hasattr(atlas, "get_village"):
                village = atlas.get_village(building.settlement_id)
        wage = world._get_employment_daily_wage(world.player.economic.profession, village=village)
        if world.player.economic.work_performance > 80:
            wage += int(wage * 0.2)
        console.print(x=x + 2, y=stat_y, string=f"Expected Wage: {wage} coins/day", fg=(0, 255, 0))
        stat_y += 1

    stat_y += 1

    # Equipment section
    stat_y += 1
    console.print(x=x + 2, y=stat_y, string="Equipment:", fg=(255, 255, 0))
    stat_y += 1

    # Show active light source
    light_str = "None"
    if world.player.equipment.equipped_light_item_key:
        light_def = TILE_DEFINITIONS.get(world.player.equipment.equipped_light_item_key) or ITEM_DEFINITIONS.get(world.player.equipment.equipped_light_item_key, {})
        light_str = light_def.get("name", world.player.equipment.equipped_light_item_key)
    console.print(x=x + 3, y=stat_y, string=f"- Light Source: {light_str}")
    stat_y += 1

    # Show armor slots
    for slot in ["head", "body", "hands", "feet"]:
        item_key = world.player.equipment.equipped_armor.get(slot)
        item_str = "None"
        if item_key:
            item_def = TILE_DEFINITIONS.get(item_key) or ITEM_DEFINITIONS.get(item_key, {})
            item_str = item_def.get("name", item_key)
        console.print(x=x + 3, y=stat_y, string=f"- {slot.capitalize()}: {item_str}")
        stat_y += 1

    stat_y += 1

    # Display note to use dedicated inventory menu
    inv_y = stat_y
    console.print(x=x + 2, y=inv_y, string=f"Inventory has been moved to its own menu. Press 'U' to view.", fg=(180, 180, 180))

    inv_y += 3
    console.print(x=x + 2, y=inv_y, string="Active Quests:", fg=(255, 255, 0))
    inv_y += 1
    if not world.player.knowledge.active_quests:
        console.print(x=x + 3, y=inv_y, string="- None", fg=(128, 128, 128))
    else:
        for quest_id, quest_data in world.player.knowledge.active_quests.items():
            console.print(x=x + 3, y=inv_y, string=f"- {quest_data['title']}")
            inv_y += 1

    inv_y += 2
    console.print(x=x + 2, y=inv_y, string="Faction Status:", fg=(255, 255, 0))
    inv_y += 1
    wars_found = False
    for v in world.villages:
        if v.at_war_with:
            wars_found = True
            for enemy_id in v.at_war_with:
                console.print(x=x + 3, y=inv_y, string=f"- Village {v.id[:4]} is at WAR with Village {enemy_id[:4]}", fg=(255, 100, 100))
                inv_y += 1
    if not wars_found:
        console.print(x=x + 3, y=inv_y, string="- The realm is at peace.", fg=(150, 200, 150))

def draw_inventory_menu(console, world):
    """Draws the dedicated scrollable inventory menu, grouping items by category."""
    menu_width = 60
    menu_height = 40
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Inventory", clear=True)

    console.print(x=x + 2, y=y + menu_height - 2, string="Up/Down to scroll | ESC to close", fg=(150, 150, 150))

    # Aggregate and categorize inventory
    categories = {
        "Weapons/Armor": [],
        "Food/Drink": [],
        "Materials": [],
        "Miscellaneous": []
    }

    # Group individual item instances by (item_key, quality, title) instead
    # of by raw item_key alone. world.player.economic.inventory is an
    # Inventory (dict of item_key -> total count) backed by per-instance
    # ItemReference objects; grouping only by item_key would silently merge
    # different quality tiers (and differently-titled unique items, e.g.
    # written books) into one line and lose that info entirely.
    inventory = world.player.economic.inventory
    grouped = {}
    group_order = []
    for item_key in list(inventory.keys()):
        for item_ref in inventory.iter_item_references(item_key):
            group_key = (item_key, item_ref.quality, item_ref.title)
            if group_key not in grouped:
                grouped[group_key] = [item_ref, 0]
                group_order.append(group_key)
            grouped[group_key][1] += 1

    def _quality_sort_rank(quality):
        return QUALITY_ORDER.index(quality) if quality in QUALITY_ORDER else len(QUALITY_ORDER)

    group_order.sort(key=lambda k: (k[0], _quality_sort_rank(k[1]), k[2] or ""))

    for group_key in group_order:
        item_key, quality, _title = group_key
        item_ref, quantity = grouped[group_key]
        item_def = TILE_DEFINITIONS.get(item_key) or ITEM_DEFINITIONS.get(item_key, {})
        tags = item_def.get("item_type_tags", [])

        entry = (f"{item_ref.name} x{quantity}", item_key, quality)

        if "armor" in tags or "weapon" in tags:
            categories["Weapons/Armor"].append(entry)
        elif "food" in tags or "drink" in tags or "consumable" in tags:
            categories["Food/Drink"].append(entry)
        elif "resource" in tags or "material" in tags:
            categories["Materials"].append(entry)
        else:
            categories["Miscellaneous"].append(entry)

    # Build the flattened list of (text, item_key, quality) lines to draw.
    # item_key/quality are None for headers/blank/money lines, which have no
    # icon and use the default text color; the icon itself provides the
    # visual indent for item lines, so no leading spaces needed.
    lines = []
    lines.append((f"Money: {world.player.economic.money} coins", None, None))
    lines.append(("", None, None))

    for cat_name, items in categories.items():
        if items:
            lines.append((f"--- {cat_name} ---", None, None))
            for item_text, item_key, quality in items:
                lines.append((item_text, item_key, quality))
            lines.append(("", None, None))

    if not lines:
        lines.append(("Your inventory is empty.", None, None))

    # Implement scrolling
    max_lines_to_display = menu_height - 4

    if "inventory_scroll_offset" not in world.interaction_context:
        world.interaction_context["inventory_scroll_offset"] = 0

    scroll_offset = world.interaction_context["inventory_scroll_offset"]

    # Bound check
    max_scroll = max(0, len(lines) - max_lines_to_display)
    if scroll_offset > max_scroll:
        scroll_offset = max_scroll
        world.interaction_context["inventory_scroll_offset"] = scroll_offset
    elif scroll_offset < 0:
        scroll_offset = 0
        world.interaction_context["inventory_scroll_offset"] = scroll_offset

    for i in range(max_lines_to_display):
        list_index = scroll_offset + i
        if list_index < len(lines):
            line_text, item_key, quality = lines[list_index]
            fg_color = (255, 255, 255)
            if line_text.startswith("--- "):
                fg_color = (255, 215, 0)
            elif line_text.startswith("Money:"):
                fg_color = (150, 255, 150)
            elif quality is not None:
                fg_color = _quality_text_color(quality)
            row_y = y + 2 + i
            icon_drawn = item_key is not None and _draw_item_icon(console, x + 2, row_y, item_key)
            text_x = x + 4 if icon_drawn else x + 2
            max_text_width = (menu_width - 6) if icon_drawn else (menu_width - 4)
            console.print(x=text_x, y=row_y, string=line_text[:max_text_width], fg=fg_color)

    # Draw scrollbar if needed
    if len(lines) > max_lines_to_display:
        scrollbar_y = y + 2 + int((scroll_offset / max_scroll) * (max_lines_to_display - 1))
        console.print(x=x + menu_width - 1, y=scrollbar_y, string="█", fg=(100, 100, 100))


def draw_trade_menu(console, world):
    """Draws the trade menu UI."""
    menu_width = 60
    menu_height = 24
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2
    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Trade", clear=True)

    target_name = world.trade_ui_npc_target.name if world.trade_ui_npc_target else "Trader"
    mode = "Selling to" if world.trade_ui_player_selling else "Buying from"
    console.print(x=x + 2, y=y + 2, string=f"{mode} {target_name}", fg=(255, 255, 0))
    console.print(x=x + 2, y=y + 3, string="TAB switch view | ENTER trade | ESC close", fg=(180, 180, 180))

    items = world.trade_ui_player_inventory_snapshot if world.trade_ui_player_selling else world.trade_ui_merchant_inventory_snapshot
    selected_index = world.trade_ui_player_item_index if world.trade_ui_player_selling else world.trade_ui_merchant_item_index

    if not items:
        console.print(x=x + 2, y=y + 5, string="No items available.", fg=(150, 150, 150))
        return

    visible_height = menu_height - 7
    scroll_offset = max(0, min(selected_index, max(0, len(items) - visible_height)))
    for row in range(visible_height):
        item_index = scroll_offset + row
        if item_index >= len(items):
            break

        item_key, quantity, price = items[item_index]
        item_ref = _get_trade_row_item_reference(world, item_key, selling=world.trade_ui_player_selling)
        if item_ref is not None:
            item_name = item_ref.name
        else:
            item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
        if item_index == selected_index:
            color = (0, 255, 255)
        elif item_ref is not None:
            color = _quality_text_color(item_ref.quality)
        else:
            color = (255, 255, 255)
        row_y = y + 5 + row
        icon_drawn = _draw_item_icon(console, x + 2, row_y, item_key)
        text_x = x + 4 if icon_drawn else x + 2
        name_width = 26 if icon_drawn else 28
        console.print(
            x=text_x,
            y=row_y,
            string=f"{item_name[:name_width]:{name_width}} x{quantity:<3} {price:>4}g",
            fg=color,
        )


def draw_knowledge_menu(console, world):
    """Draws the player's knowledge menu (known books, etc.)."""
    menu_width = 60
    menu_height = 30
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Knowledge", clear=True)

    line = y + 2
    console.print(x=x + 2, y=line, string="Books Read:", fg=(255, 255, 0))
    line += 1

    if not world.player.knowledge.known_books:
        console.print(x=x + 3, y=line, string="- None", fg=(128, 128, 128))
    else:
        for book_id in sorted(list(world.player.knowledge.known_books)):
            book = next((b for b in world.books if b.id == book_id), None)
            if book:
                console.print(x=x + 3, y=line, string=f"- {book.title}")
                line += 1

def draw_dialogue_menu(console, world):
    """Draws the interactive Dialogue UI."""
    width = 60
    height = 20
    from config import MAP_WIDTH, SCREEN_HEIGHT
    x = max(0, (MAP_WIDTH - width) // 2)
    y = max(0, (SCREEN_HEIGHT - height) // 2)
    
    npc_name = world.get_entity_display_name(world.chat_ui_target_npc, include_relationship=True) if getattr(world, 'chat_ui_target_npc', None) else "Unknown"
    title = f" Conversation with {npc_name} "
    
    console.draw_frame(x=x, y=y, width=width, height=height, title=title, clear=True, fg=(255, 255, 255), bg=(12, 14, 20))

    import textwrap

    target_npc = getattr(world, 'chat_ui_target_npc', None)
    raw_target_name = getattr(target_npc, 'name', None)
    display_target_name = world.get_entity_display_name(target_npc) if target_npc else None

    portrait_top = y + 1
    header_rows = 0
    if target_npc is not None:
        _draw_entity_portrait(console, x + 2, portrait_top, target_npc)
        console.print(
            x=x + 2 + PORTRAIT_ZOOM + 1,
            y=portrait_top + (PORTRAIT_ZOOM // 2),
            string=(display_target_name or npc_name)[: width - 4 - PORTRAIT_ZOOM - 1],
            fg=(255, 255, 0),
        )
        header_rows = PORTRAIT_ZOOM + 1

    history_start_y = y + 2 + header_rows
    max_history_lines = max(1, height - 4 - header_rows)
    wrapped_lines = []

    for speaker, text in getattr(world, 'chat_ui_history', []):
        if raw_target_name and speaker == raw_target_name:
            speaker = display_target_name
        color = (200, 240, 255) if speaker == "Player" else (255, 215, 120)
        prefix = f"{speaker}: "
        lines = textwrap.wrap(prefix + text, width=width - 4)
        for line in lines:
            wrapped_lines.append((line, color))

    start_idx = max(0, len(wrapped_lines) - max_history_lines)
    display_lines = wrapped_lines[start_idx:]

    cur_y = history_start_y
    for line_text, color in display_lines:
        console.print(x=x + 2, y=cur_y, string=line_text, fg=color)
        cur_y += 1
        
    input_y = y + height - 2
    console.print(x=x + 2, y=input_y, string="> " + getattr(world, 'chat_ui_input_line', '') + "_", fg=(255, 255, 255))

def draw_quest_menu(console, world):
    """Draws the quest log menu."""
    menu_width = 70
    menu_height = 40
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Quest Log", clear=True)

    # List width
    list_width = 25
    details_x = x + list_width + 1

    # Draw separator line
    console.draw_rect(x=x+list_width, y=y+1, width=1, height=menu_height-2, ch=ord('|'), fg=(100, 100, 100))

    active_quests = list(world.player.knowledge.active_quests.values())
    num_quests = len(active_quests)

    if not active_quests:
        console.print(x=x + 2, y=y + 2, string="No active quests.", fg=(150, 150, 150))
        return

    ctx = world.quest_menu_context
    selected_index = ctx.get("selected_quest_index", 0)
    scroll_offset = ctx.get("scroll_offset", 0)
    list_height = menu_height - 4

    # Scrolling logic
    if selected_index < 0: selected_index = 0
    if selected_index >= num_quests: selected_index = num_quests - 1
    ctx["selected_quest_index"] = selected_index

    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + list_height:
        scroll_offset = selected_index - list_height + 1
    ctx["scroll_offset"] = scroll_offset

    # Draw List
    for i in range(list_height):
        idx = scroll_offset + i
        if idx < num_quests:
            quest = active_quests[idx]
            title = quest["title"]
            if len(title) > list_width - 3:
                title = title[:list_width - 6] + "..."

            color = (255, 255, 255)
            if idx == selected_index:
                color = (0, 255, 255)
                console.print(x=x + 1, y=y + 2 + i, string=">", fg=color)

            console.print(x=x + 3, y=y + 2 + i, string=title, fg=color)

    # Draw Details
    if 0 <= selected_index < num_quests:
        selected_quest = active_quests[selected_index]

        detail_y = y + 2
        # Title
        console.print_box(x=details_x + 1, y=detail_y, width=menu_width - list_width - 3, height=2, string=selected_quest["title"], fg=(255, 255, 0))
        detail_y += 2

        # Description
        desc = selected_quest["description"]
        desc_height = console.get_height_rect(x=details_x + 1, y=detail_y, width=menu_width - list_width - 3, height=10, string=desc)
        console.print_box(x=details_x + 1, y=detail_y, width=menu_width - list_width - 3, height=desc_height, string=desc)
        detail_y += desc_height + 1

        # Objectives
        console.print(x=details_x + 1, y=detail_y, string="Objectives:", fg=(200, 200, 200))
        detail_y += 1

        if selected_quest["type"] == "fetch":
            item_name = selected_quest["item_to_fetch_key"].replace("_", " ").title()
            count = selected_quest["item_fetch_count"]

            # Check player inventory for progress display. inventory is an
            # Inventory (dict of item_key -> total count), so get() already
            # gives the aggregate quantity - no need to iterate instances.
            current_count = world.player.economic.inventory.get(selected_quest["item_to_fetch_key"], 0)

            progress_str = f"- Fetch {item_name}: {current_count}/{count}"
            color = (0, 255, 0) if current_count >= count else (255, 255, 255)
            console.print(x=details_x + 2, y=detail_y, string=progress_str, fg=color)

        elif selected_quest["type"] == "kill":
            target_count = selected_quest.get("target_count", 1)
            progress = selected_quest.get("progress", 0)
            progress_str = f"- Defeat targets: {progress}/{target_count}"
            color = (0, 255, 0) if progress >= target_count else (255, 255, 255)
            console.print(x=details_x + 2, y=detail_y, string=progress_str, fg=color)

def draw_help_menu(console):
    """Draws the help menu with controls."""
    menu_width = 50
    menu_height = 30
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title="Help / Controls", clear=True)

    controls = [
        ("Movement", "Arrows / Left Click"),
        ("Interact", "E / Right Click"),
        ("Wait", "."),
        ("Talk", "T"),
        ("Character Info", "I"),
        ("Crafting", "C"),
        ("Building", "B"),
        ("Quests", "Q (Planned)"),
        ("Help", "?"),
        ("Save & Menu", "ESC"),
    ]

    y_offset = y + 3
    for action, key in controls:
        console.print(x=x + 4, y=y_offset, string=f"{action:<20} : {key}")
        y_offset += 2

    console.print(x=x + menu_width // 2, y=y + menu_height - 3, string="Press ESC to close", alignment=tcod.CENTER)


def draw_book_reading_ui(console, world):
    """Draws the UI for reading a book."""
    ctx = world.book_reading_context
    book_id = ctx.get("book_id")
    if not book_id:
        return

    book = next((b for b in world.books if b.id == book_id), None)
    if not book:
        return

    menu_width = 80
    menu_height = 50
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    console.draw_frame(x=x, y=y, width=menu_width, height=menu_height, title=f"Reading: {book.title}", clear=True)

    # Content preparation
    header = f"by {book.author_name} ({book.year_written})\n\n"
    full_text = header + book.content

    # Text wrapping
    text_width = menu_width - 4
    wrapped_lines = []
    for line in full_text.splitlines():
        if line:
            wrapped_lines.extend(textwrap.wrap(line, width=text_width))
        else:
            wrapped_lines.append("") # Preserve empty lines

    # Scrolling
    scroll_offset = ctx.get("scroll_offset", 0)
    display_height = menu_height - 4

    # Bound scrolling (simple method)
    max_scroll = max(0, len(wrapped_lines) - display_height)
    if scroll_offset > max_scroll:
        scroll_offset = max_scroll
        ctx["scroll_offset"] = scroll_offset # Update context to clamp it

    visible_lines = wrapped_lines[scroll_offset : scroll_offset + display_height]

    for i, line in enumerate(visible_lines):
        console.print(x=x + 2, y=y + 2 + i, string=line)

    # Scrollbar indicator (optional but helpful)
    if len(wrapped_lines) > display_height:
        pct = scroll_offset / max_scroll
        bar_y = int(y + 2 + (display_height * pct))
        if bar_y >= y + menu_height - 1: bar_y = y + menu_height - 2
        console.print(x=x + menu_width - 1, y=bar_y, string="█", fg=(100, 100, 100))
