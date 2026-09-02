# rendering/console_renderer.py

from tcod_compat import tcod
import textwrap
import itertools
import math
from typing import NamedTuple
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, STATUS_PANEL_WIDTH,
    COLOR_PLAYER_STATUS_WET, COLOR_PLAYER_STATUS_FREEZING,
    WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE, DAY_LENGTH_TICKS
)
from data.tiles import TILE_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from data.environment import WEATHER_DEFINITIONS
from data.dawnlike import get_entity_sprite, _get_equipment_overlays, _get_appearance_overlays, ITEM_SPRITES
from entities.animal import Animal
from engine import Player
from rendering.sprite_atlas import ZOOMED_DAWNLIKE_LEVELS, zoomed_sprite_codepoint
from rendering import lighting
from rendering import ui_theme as theme
from rendering import widgets
from runtime_compat import np
from presentation import message_log
from presentation.sensory_observation import (
    describe_focus_target,
    list_tile_focus_targets,
)
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


# Re-exported from ui_theme so the palette has a single definition; both
# names are kept because callers (and tests) already reference them here.
QUALITY_ORDER = theme.QUALITY_ORDER
QUALITY_TEXT_COLORS = theme.QUALITY_COLORS


def _quality_text_color(quality):
    """Return the display color for an item's quality tier, defaulting to
    the Normal-tier color for unrecognized or missing values."""
    return theme.quality_color(quality)


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

            # Stamp appearance (hair/facial hair) and equipment overlays on
            # top of the base sprite, merged into one z-ordered pass so
            # draw order stays correct across both categories (e.g. a
            # z=1 headwear item painting after a z=0 body-armor item).
            if not getattr(getattr(entity, "physical", None), "is_dead", False):
                overlays = _get_appearance_overlays(entity) + _get_equipment_overlays(entity)
                overlays.sort(key=lambda entry: entry[3])
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
    # Name the building as well as the floor. A player standing in the bakery was
    # told "Wood Floor" - the building's identity only appeared if they happened
    # to hover the mouse over it - which matters more now that a shop will sell
    # you what is on its shelves: you have to be able to tell you are in one.
    inside = getattr(world, "get_building_at", lambda _x, _y: None)(
        world.player.x, world.player.y
    )
    building_name = _format_hover_building_name(inside)
    if building_name:
        standing_on = f"{standing_on} - {building_name}"
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

def _draw_mini_health_bar(console, x, y, width, value, maximum, colors=theme.METER_ENTITY_HP):
    """Draw a compact, label-less HP bar for overhead display above an
    entity in the world view.

    Unlike widgets.meter (used in the status panel, where there's room for a
    text label and a numeric "value/max" readout), this is stamped directly
    above a tile-sized sprite, so it's just a row of filled/empty cells.
    """
    maximum = max(1, maximum)
    ratio = max(0.0, min(1.0, value / maximum))
    filled_width = int(round(width * ratio))
    if value > 0:
        filled_width = max(1, filled_width)  # any remaining HP shows at least a sliver
    filled_width = min(width, filled_width)
    fill_color, track_color = colors
    if filled_width > 0:
        console.print(x=x, y=y, string=theme.BAR_CELL * filled_width, fg=fill_color)
    if filled_width < width:
        console.print(
            x=x + filled_width, y=y,
            string=theme.BAR_CELL * (width - filled_width), fg=track_color,
        )


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

LOG_PANEL_HEIGHT = 6
LOG_VISIBLE_LINES = LOG_PANEL_HEIGHT - 2


def _get_log_entries(world):
    """The log's display model, tolerating worlds that only have the plain
    string list (older saves, and the minimal fakes used in tests)."""
    entries = getattr(world, "chat_log_entries", None)
    if not entries:
        entries = message_log.entries_from_plain_log(getattr(world, "chat_log", []) or [])
    return message_log.visible_entries(
        entries, include_debug=getattr(world, "show_debug_log", False)
    )


def _draw_log_panel(console, world):
    """Draw the message log docked along the bottom of the world view.

    Older lines are dimmed by age rather than being all one brightness, so
    the eye lands on what just happened; the player can scroll back through
    the history with PageUp/PageDown.
    """
    y = SCREEN_HEIGHT - LOG_PANEL_HEIGHT
    _draw_chatter_panel(console, world, y)

    entries = _get_log_entries(world)
    scroll = max(0, min(int(getattr(world, "chat_log_scroll", 0)),
                        max(0, len(entries) - LOG_VISIBLE_LINES)))

    title = "Log" if scroll == 0 else f"Log (-{scroll})"
    widgets.panel(console, 0, y, MAP_WIDTH, LOG_PANEL_HEIGHT, title=title, bg=theme.LOG_BG)

    end = len(entries) - scroll
    visible = entries[max(0, end - LOG_VISIBLE_LINES):end]
    current_tick = getattr(world, "game_time", 0)
    for index, entry in enumerate(visible):
        color = _dim_color(
            theme.log_color(entry.category),
            message_log.fade_ratio(entry, current_tick),
        )
        console.print(
            x=1, y=y + 1 + index,
            string=entry.display_text()[:MAP_WIDTH - 2],
            fg=color,
        )

    if scroll > 0:
        console.print(x=MAP_WIDTH - 2, y=y + 1, string=theme.ARROW_UP, fg=theme.TEXT_MUTED)
    if scroll < max(0, len(entries) - LOG_VISIBLE_LINES):
        console.print(x=MAP_WIDTH - 2, y=y + LOG_PANEL_HEIGHT - 2,
                      string=theme.ARROW_DOWN, fg=theme.TEXT_MUTED)

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

# Per-channel color wash for the time of day, keyed by
# world.current_light_level_name: a cool/blue cast at night, a warm/orange
# cast at dawn and dusk. DAY and any unrecognized light level name are left
# neutral. _apply_lighting_and_depth blends this toward a nearby fire's own
# color where one is lighting the cell, so firelight overrides the ambient
# wash rather than being tinted by it.
LIGHT_LEVEL_TINTS = {
    "DAWN": (1.12, 1.0, 0.88),
    "DUSK": (1.15, 0.95, 0.85),
    "NIGHT": (0.85, 0.92, 1.15),
    "PITCH BLACK": (0.78, 0.86, 1.22),
}


# Per-channel color wash for the time of year, composed with the time-of-day
# wash above. The seasons are load-bearing in the simulation - they set the base
# temperature an entity is measured against, decide which weather is possible,
# scale what a Farmer harvests and gate animal mating - but the only place a
# season reached the player was one word in the HUD, so a winter that can freeze
# you looked exactly like summer. Deliberately gentler than LIGHT_LEVEL_TINTS,
# because the two multiply: winter at night should read as a cold night, not as
# a blue screen.
SEASON_TINTS = {
    "Spring": (0.98, 1.05, 0.97),
    "Summer": (1.04, 1.01, 0.93),
    "Autumn": (1.09, 0.98, 0.87),
    "Winter": (0.95, 0.99, 1.08),
}


def current_season_name(world):
    """The world's season, or "" if it has none.

    Guarded because the renderer is called with stand-in worlds in the tests,
    and an unguarded attribute read here would fail them for a reason that has
    nothing to do with what they check.
    """
    seasons = getattr(world, "seasons", None)
    index = getattr(world, "current_season_index", None)
    if not seasons or not isinstance(index, int):
        return ""
    if 0 <= index < len(seasons):
        return str(seasons[index])
    return ""


def _season_tint_array(season_name):
    multipliers = SEASON_TINTS.get(season_name)
    if multipliers is None:
        return np.ones(3, dtype=np.float32)
    return np.asarray(multipliers, dtype=np.float32)


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


def _view_coordinate_arrays(world, camera_x, camera_y, console_width, console_height):
    """World coordinate of every console column and row, as two arrays.

    At zoom > 1 several console cells map to the same world tile, which is
    exactly what the integer division reproduces - the same mapping
    `_screen_to_world` does one cell at a time.
    """
    zoom = _get_zoom_factor(world)
    columns = camera_x + (np.arange(console_width) // zoom).astype(np.int32)
    rows = camera_y + (np.arange(console_height) // zoom).astype(np.int32)
    return columns, rows


def _view_masks(world, columns, rows):
    """Visibility and sight-blocking masks for the view, shaped (H, W).

    Both come from one pass at *tile* resolution rather than console-cell
    resolution: at zoom 3 the same world tile covers a 3x3 block of cells,
    so querying per cell asks the world the same question nine times. The
    small per-tile results are then expanded back out to cell resolution
    with an index lookup, which is the part that vectorizes.

    Visibility still goes through `is_visible` so this shares one definition
    with the rest of the renderer instead of reaching into the FOV map
    directly and quietly diverging from it.
    """
    unique_x = np.unique(columns)
    unique_y = np.unique(rows)
    tile_visible = np.zeros((len(unique_y), len(unique_x)), dtype=bool)
    tile_blocking = np.zeros_like(tile_visible)

    get_tile_at = getattr(world, "get_tile_at", None)
    for row_index, world_y in enumerate(unique_y):
        if not (0 <= world_y < WORLD_HEIGHT):
            continue
        for col_index, world_x in enumerate(unique_x):
            if not (0 <= world_x < WORLD_WIDTH):
                continue
            if not is_visible(world, int(world_x), int(world_y)):
                continue
            tile_visible[row_index, col_index] = True
            if get_tile_at is None:
                continue
            tile = get_tile_at(int(world_x), int(world_y))
            if tile is not None and getattr(tile, "blocks_fov", False):
                tile_blocking[row_index, col_index] = True

    col_lookup = np.searchsorted(unique_x, columns)
    row_lookup = np.searchsorted(unique_y, rows)
    expand = np.ix_(row_lookup, col_lookup)
    return tile_visible[expand], tile_blocking[expand]


def _light_level_tint_array(light_level_name):
    multipliers = LIGHT_LEVEL_TINTS.get(light_level_name)
    if multipliers is None:
        return np.ones(3, dtype=np.float32)
    return np.asarray(multipliers, dtype=np.float32)


def _apply_lighting_and_depth(console, world, camera_x, camera_y):
    """Shade the world view by ambient light, local light sources and depth.

    Runs as whole-array numpy operations over the map area rather than a
    per-cell Python loop, which is what makes room for the light-source
    pass without costing frame time.
    """
    light_level_name = getattr(world, "current_light_level_name", "DAY")
    ambient = lighting.ambient_for_light_level(light_level_name)

    # The root console is built row-major (see main.create_console): fg/bg are
    # shaped (height, width, 3) and indexed [y, x], which is the order every
    # array in this function uses.
    console_height = min(MAP_HEIGHT, getattr(console, "height", MAP_HEIGHT), console.bg.shape[0], console.fg.shape[0])
    console_width = min(MAP_WIDTH, getattr(console, "width", MAP_WIDTH), console.bg.shape[1], console.fg.shape[1])
    if console_height <= 0 or console_width <= 0:
        return

    columns, rows = _view_coordinate_arrays(world, camera_x, camera_y, console_width, console_height)
    visible, blocking = _view_masks(world, columns, rows)
    if not visible.any():
        return

    # --- Local light sources -------------------------------------------
    strength = np.zeros((console_height, console_width), dtype=np.float32)
    warm = np.zeros_like(strength)
    warm_tint = np.zeros((console_height, console_width, 3), dtype=np.float32)
    if ambient < 1.0:
        padding = lighting.MAX_LIGHT_RADIUS
        view_bounds = (
            int(columns[0]) - padding, int(rows[0]) - padding,
            int(columns[-1]) + padding, int(rows[-1]) + padding,
        )
        sources = lighting.collect_light_sources(world, view_bounds)
        get_tile_at = getattr(world, "get_tile_at", None)
        if get_tile_at is not None:
            tile_bounds = (int(columns[0]), int(rows[0]), int(columns[-1]), int(rows[-1]))
            sources += lighting.collect_tile_light_sources(world, tile_bounds, get_tile_at=get_tile_at)
        strength, warm, warm_tint = lighting.build_light_map(sources, columns, rows, ambient)

    # --- Depth cue ------------------------------------------------------
    # A gentle vignette toward the bottom-right keeps the view from reading
    # as a flat sheet; it was in the original per-cell code as edge_falloff.
    edge_x = np.arange(console_width, dtype=np.float32) / max(1, MAP_WIDTH - 1)
    edge_y = np.arange(console_height, dtype=np.float32) / max(1, MAP_HEIGHT - 1)
    edge = 0.92 - (0.12 * np.maximum(edge_x[np.newaxis, :], edge_y[:, np.newaxis]))

    light = np.clip((ambient + (1.0 - ambient) * strength) * edge, 0.12, 1.0)

    fg_scale = 0.55 + (0.45 * light)
    bg_scale = 0.45 + (0.55 * light)

    # Time of day and time of year wash the view together. Composed here rather
    # than applied as a second pass so that the firelight blend below still
    # overrides both: a hearth in January should look like a hearth.
    level_tint = _light_level_tint_array(light_level_name) * _season_tint_array(
        current_season_name(world)
    )
    # Where a warm source dominates, blend the cool night wash toward that
    # source's color - this is what makes firelight read as fire rather
    # than as "slightly less dark".
    blend = np.clip(warm, 0.0, 1.0)[..., np.newaxis]
    warm_normalized = np.where(
        warm[..., np.newaxis] > 0,
        warm_tint / 255.0 * 1.35,
        1.0,
    ).astype(np.float32)
    tint = (level_tint[np.newaxis, np.newaxis, :] * (1.0 - blend)) + (warm_normalized * blend)

    fg = console.fg[:console_height, :console_width].astype(np.float32)
    bg = console.bg[:console_height, :console_width].astype(np.float32)
    lit_fg = np.clip(fg * fg_scale[..., np.newaxis] * tint, 0, 255)
    lit_bg = np.clip(bg * bg_scale[..., np.newaxis] * tint, 0, 255)

    mask = visible[..., np.newaxis]
    console.fg[:console_height, :console_width] = np.where(mask, lit_fg, fg).astype(console.fg.dtype)
    console.bg[:console_height, :console_width] = np.where(mask, lit_bg, bg).astype(console.bg.dtype)

    # --- Contact shadows -------------------------------------------------
    # Shift the blocking mask one cell down/right/diagonal and darken what
    # lands under it, the vectorized form of the original triple-offset loop.
    blocking = blocking & visible
    if blocking.any():
        shadow = np.zeros_like(blocking)
        shadow[:, 1:] |= blocking[:, :-1]
        shadow[1:, :] |= blocking[:-1, :]
        shadow[1:, 1:] |= blocking[:-1, :-1]
        shadow &= visible
        shadow &= ~blocking
        if shadow.any():
            shadowed = console.bg[:console_height, :console_width].astype(np.float32) * 0.75
            console.bg[:console_height, :console_width] = np.where(
                shadow[..., np.newaxis],
                np.clip(shadowed, 0, 255),
                console.bg[:console_height, :console_width],
            ).astype(console.bg.dtype)

def _entity_shows_health_bar(entity, focused_entity):
    """True if _draw_entity_health_bars would draw a bar for this entity
    (alive, with valid HP data, and either hostile or the current focus
    target). Shared with _draw_entity_markers so the "!" marker can avoid
    the health bar's row instead of overwriting one of its cells - both
    are drawn on entity.y - 1 by default.
    """
    if getattr(getattr(entity, "physical", None), "is_dead", False):
        return False
    combat = getattr(entity, "combat", None)
    if combat is None:
        return False
    is_hostile = getattr(combat, "is_hostile_to_player", False)
    is_targeted = focused_entity is entity
    if not (is_hostile or is_targeted):
        return False
    max_hp = getattr(combat, "max_hp", None)
    hp = getattr(combat, "hp", None)
    return bool(max_hp) and hp is not None


def _draw_entity_markers(console, world, camera_x, camera_y, focus=None):
    focused_entity = focus.get("entity") if isinstance(focus, dict) else None
    for entity in itertools.chain(world.npcs, world.village_npcs):
        if getattr(entity, "is_sleeping", False):
            continue
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
            # This entity also gets a health bar drawn on this same row
            # (see _draw_entity_health_bars, entity.y - 1) - without an
            # offset the marker would land dead center on the bar and
            # overwrite one of its cells. Shifting the marker to y - 2
            # (the row used by the overhead name label) isn't a real fix
            # either: a marker only ever draws for the focused entity, and
            # the label always draws for the focused entity too, so that
            # would trade one guaranteed collision for another. Nudging
            # the marker sideways past the bar's right edge keeps all
            # three overlays legible without touching the label's row.
            if _entity_shows_health_bar(entity, focused_entity):
                offset_x = (HEALTH_BAR_WIDTH // 2) + 1
                if screen_x + offset_x < MAP_WIDTH:
                    screen_x += offset_x
            console.print(x=screen_x, y=screen_y, string=marker_char, fg=marker_color)

HEALTH_BAR_WIDTH = 5


def _draw_entity_health_bars(console, world, camera_x, camera_y, focus=None):
    """Draw a compact HP bar above any NPC that's hostile to the player or
    is the player's current focus/interaction target, so combat state is
    visible directly in the world view rather than only in the side panel.
    """
    focused_entity = focus.get("entity") if isinstance(focus, dict) else None
    for entity in itertools.chain(world.npcs, world.village_npcs):
        if not _entity_shows_health_bar(entity, focused_entity):
            continue

        bar_world_y = entity.y - 1
        if not _is_entity_overlay_visible(world, entity, bar_world_y):
            continue
        screen_point = _screen_point_for_world(world, camera_x, camera_y, entity.x, bar_world_y)
        if screen_point is None:
            continue
        screen_x, screen_y = screen_point
        bar_x = screen_x - (HEALTH_BAR_WIDTH // 2)
        _draw_mini_health_bar(console, bar_x, screen_y, HEALTH_BAR_WIDTH, entity.combat.hp, entity.combat.max_hp)

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

# Glyph key, then the controls themselves. The controls are here because the
# only place they existed was the help menu, which a player has to already know
# to press "?" to find - so the inventory and the character sheet may as well
# not have had keys at all.
STATUS_LEGEND_ROWS_CONTENT = (
    ("@ You", (255, 245, 140)),
    ("! hostile  ? quest", "INFO"),
    ("$ trader   * loot", "SUCCESS"),
    ("Pulse = focus", "TEXT_DIM"),
    ("Keys", "HEADING"),
    ("E act    T talk", "TEXT_DIM"),
    ("I sheet  U bag", "TEXT_DIM"),
    ("L look   ? help", "TEXT_DIM"),
)
STATUS_LEGEND_ROWS = len(STATUS_LEGEND_ROWS_CONTENT) + 1


class _PanelCursor:
    """Top-down write cursor for the status column, with a hard bottom stop.

    The panel's sections vary in height - status effects, nearby entities
    and quest objectives all grow with world state - while the legend is
    pinned to the bottom of the column. The previous code advanced a bare
    `y += 1` with no idea how much room was left, so a frame with several
    alerts and a full quest simply drew straight through the legend.

    This makes the remaining budget explicit: a section asks whether it has
    room for the rows it needs, and is skipped whole rather than drawn on
    top of something else.
    """

    def __init__(self, console, x, y, width, limit):
        self.console = console
        self.x = x
        self.y = y
        self.width = width
        self.limit = limit

    @property
    def remaining(self):
        return max(0, self.limit - self.y)

    def fits(self, rows=1):
        return self.remaining >= rows

    def blank(self, rows=1):
        self.y = min(self.limit, self.y + rows)

    def heading(self, text):
        if not self.fits():
            return False
        self.y = widgets.heading(self.console, self.x, self.y, text)
        return True

    def line(self, text, *, color=None, indent=0):
        if not self.fits():
            return False
        self.y = widgets.text_line(
            self.console, self.x + indent, self.y, text,
            color=color, width=self.width - indent,
        )
        return True

    def meter(self, label, value, maximum, colors):
        if not self.fits():
            return False
        self.y = widgets.meter(self.console, self.x, self.y, self.width, label, value, maximum, colors)
        return True


def _hunger_meter_colors(ratio):
    """Hunger climbs toward max, so a *high* ratio is the dangerous end."""
    if ratio > 0.8:
        return theme.METER_HUNGER_CRIT
    if ratio > 0.5:
        return theme.METER_HUNGER_WARN
    return theme.METER_HUNGER_OK


def _thirst_meter_colors(ratio):
    if ratio > 0.8:
        return theme.METER_THIRST_CRIT
    if ratio > 0.5:
        return theme.METER_THIRST_WARN
    return theme.METER_THIRST_OK


def _status_effect_color(effect):
    if effect == "Wet":
        return COLOR_PLAYER_STATUS_WET
    if effect == "Freezing":
        return COLOR_PLAYER_STATUS_FREEZING
    if effect == "Overheating":
        return (255, 100, 0)
    return theme.TEXT


def _draw_status_legend(console, panel_x, panel_width):
    """Draw the glyph legend pinned to the bottom of the status column."""
    y = SCREEN_HEIGHT - 1 - STATUS_LEGEND_ROWS - 1
    widgets.heading(console, panel_x + 1, y, "Legend")
    for offset, (text, color) in enumerate(STATUS_LEGEND_ROWS_CONTENT, start=1):
        resolved = getattr(theme, color) if isinstance(color, str) else color
        console.print(x=panel_x + 2, y=y + offset, string=text[: panel_width - 3], fg=resolved)
    return y


def _draw_status_quest_section(cursor, world):
    """Draw the tracked-quest block. Returns False if there was no room."""
    active_quests = list(world.player.knowledge.active_quests.values())
    if not active_quests:
        if not cursor.fits(2):
            return False
        cursor.heading("Active Quest")
        cursor.line("Explore and talk", color=theme.TEXT_MUTED, indent=1)
        return True

    quest = active_quests[0]
    title_lines = textwrap.wrap(str(quest['title']), width=cursor.width)
    # heading + title + objective + optional "more" line
    needed = 1 + len(title_lines) + 1 + (1 if len(active_quests) > 1 else 0)
    if not cursor.fits(needed):
        return False

    cursor.heading("Active Quest")
    for line in title_lines:
        cursor.line(line, color=theme.INFO)

    if quest["type"] == "fetch":
        item_key = quest["item_to_fetch_key"]
        required = quest["item_fetch_count"]
        # inventory is an Inventory (item_key -> total count), so a plain
        # get() already gives the aggregate quantity.
        current = world.player.economic.inventory.get(item_key, 0)
        item_name = ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)
        cursor.line(
            f"Fetch {item_name}: {current}/{required}",
            color=theme.SUCCESS if current >= required else theme.TEXT_DIM,
            indent=1,
        )
    elif quest["type"] == "kill":
        required = quest.get("target_count", 1)
        current = quest.get("progress", 0)
        cursor.line(
            f"Targets Defeated: {current}/{required}",
            color=theme.SUCCESS if current >= required else theme.TEXT_DIM,
            indent=1,
        )

    if len(active_quests) > 1:
        cursor.line(f"+ {len(active_quests) - 1} more (Q)", color=theme.TEXT_MUTED)
    return True


def draw_status_panel(console, world, camera_x, camera_y):
    """Draws the status panel on the right side of the screen."""
    panel_x = MAP_WIDTH
    panel_width = STATUS_PANEL_WIDTH
    focus = _get_focus_target(world, camera_x, camera_y)
    widgets.panel(
        console, panel_x, 0, panel_width, SCREEN_HEIGHT,
        title="Field Guide", bg=theme.PANEL_BG_DEEP,
    )

    legend_top = _draw_status_legend(console, panel_x, panel_width)
    cursor = _PanelCursor(console, panel_x + 1, 2, panel_width - 3, legend_top - 1)

    standing_on, focus_target = _get_focus_summary(world)

    # Who the player is. Nothing on the main screen named the character, and
    # the character sheet did not either, so a player had no way to learn their
    # own name short of reading a save file.
    cursor.heading("You")
    cursor.line(str(getattr(world.player, "name", "You")), color=theme.HEADING)
    cursor.line(
        f"{world.player.economic.profession} - {world.player.economic.money}c",
        color=theme.TEXT_DIM,
    )
    cursor.blank()

    cursor.heading("Scene")
    clock_str = _format_world_clock(world.game_time)
    if getattr(world, "is_paused", False):
        speed_badge = " [PAUSED]"
    else:
        speed = getattr(world, "simulation_speed", 1.0)
        if speed >= 4.0:
            speed_badge = " [>>> 4x]"
        elif speed >= 2.0:
            speed_badge = " [>> 2x]"
        else:
            speed_badge = " [> 1x]"
    cursor.line(f"{clock_str}{speed_badge}", color=theme.TEXT_DIM)
    cursor.line(
        f"{world.seasons[world.current_season_index]} / {world.weather.replace('_', ' ').title()}",
        color=theme.INFO,
    )
    cursor.line(f"Standing: {standing_on}", color=theme.SUCCESS)
    cursor.line(f"Focus: {focus['label'] or focus_target}", color=theme.WARNING)

    hover_y = _draw_hover_inspect(console, world, camera_x, camera_y, panel_x, cursor.y, panel_width)
    cursor.y = (hover_y + 1) if hover_y > cursor.y else (cursor.y + 1)

    if cursor.fits(13):
        cursor.y = _draw_minimap_panel(console, world, panel_x, cursor.y, panel_width, 12) + 1

    if getattr(world, "show_autonomy_overlay", False) and cursor.fits(5):
        counters = getattr(world, "autonomy_counters", {})
        cursor.heading("Autonomy Audit")
        cursor.line(f"Vis/Act: {counters.get('visible', 0)}/{counters.get('active', 0)}", indent=1, color=theme.TEXT_DIM)
        cursor.line(f"Path/Mov: {counters.get('with_path', 0)}/{counters.get('moved', 0)}", indent=1, color=theme.TEXT_DIM)
        cursor.line(f"Idle/Wrk: {counters.get('idle', 0)}/{counters.get('at_work_home', 0)}", indent=1, color=theme.TEXT_DIM)
        cursor.line(f"Wait/Fail: {counters.get('in_timed_activity', 0)}/{counters.get('blocked_path_failed', 0)}", indent=1, color=theme.TEXT_DIM)

    physical = world.player.physical
    if cursor.fits(4):
        cursor.heading("Vitals")
        cursor.meter("HP", world.player.combat.hp, world.player.combat.max_hp, theme.METER_HP)
        hunger_ratio = min(1.0, physical.hunger / max(1, physical.max_hunger))
        cursor.meter("HU", int(physical.hunger), int(physical.max_hunger), _hunger_meter_colors(hunger_ratio))
        thirst_ratio = min(1.0, physical.thirst / max(1, physical.max_thirst))
        cursor.meter("TH", int(physical.thirst), int(physical.max_thirst), _thirst_meter_colors(thirst_ratio))
        cursor.blank()

    if physical.status_effects and cursor.fits(1 + len(physical.status_effects)):
        cursor.heading("Alerts")
        for effect in physical.status_effects:
            cursor.line(f"! {effect}", color=_status_effect_color(effect), indent=1)
        cursor.blank()

    if _draw_status_quest_section(cursor, world):
        cursor.blank()

    nearby_entities = _get_visible_nearby_entities(world, limit=4)
    if cursor.fits(2):
        cursor.heading("Nearby")
        if not nearby_entities:
            cursor.line("None visible", color=theme.TEXT_MUTED, indent=1)
        else:
            for distance, entity in nearby_entities:
                label = "Animal" if isinstance(entity, Animal) else "NPC"
                entity_name = world.get_entity_display_name(entity, include_relationship=True)
                cursor.line(f"{distance}t {label}: {entity_name}", color=theme.TEXT_DIM, indent=1)
        cursor.blank()

    reputations = [(faction, rep) for faction, rep in world.player.social.reputation.items() if rep != 0]
    if cursor.fits(2):
        cursor.heading("Reputation")
        if not reputations:
            cursor.line("Neutral", color=theme.TEXT_MUTED, indent=1)
        else:
            for faction, rep in reputations:
                cursor.line(f"{faction[:3].upper()}: {rep}", color=theme.TEXT_DIM, indent=1)

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

    if world.game_state == "LOOK_MODE":
        draw_look_mode_ui(console, world)


LOOK_CURSOR_BG = (150, 120, 20)
LOOK_CURSOR_FG = (255, 255, 190)
LOOK_CURSOR_CORNERS = ("\u250c", "\u2510", "\u2514", "\u2518")


def draw_look_cursor(console, world, camera_x, camera_y):
    """Mark the tile Look Mode is pointing at, on the map itself.

    Look Mode used to report only a pair of coordinates in its banner, which
    told the player nothing they could act on - there was no way to see which
    tile the cursor was actually on. The tile is highlighted, and at zoom levels
    where a tile is more than one cell it also gets corner brackets, which read
    as a reticle rather than as a coloured floor tile.
    """
    if getattr(world, "game_state", None) != "LOOK_MODE":
        return
    cursor_x = getattr(world, "look_cursor_x", getattr(world.player, "x", 0))
    cursor_y = getattr(world, "look_cursor_y", getattr(world.player, "y", 0))
    rect = _world_to_screen_rect(world, camera_x, camera_y, cursor_x, cursor_y)
    if rect is None:
        return

    x0, y0, x1, y1 = rect
    for draw_y in range(y0, y1 + 1):
        for draw_x in range(x0, x1 + 1):
            console.bg[draw_y, draw_x] = LOOK_CURSOR_BG

    if x1 > x0 and y1 > y0:
        corners = ((x0, y0), (x1, y0), (x0, y1), (x1, y1))
        for (corner_x, corner_y), glyph in zip(corners, LOOK_CURSOR_CORNERS):
            console.print(x=corner_x, y=corner_y, string=glyph, fg=LOOK_CURSOR_FG, bg=LOOK_CURSOR_BG)


def draw_look_mode_ui(console, world):
    """Draw the Look Mode banner: what is focused, and what else shares the tile."""
    cursor_x = getattr(world, "look_cursor_x", getattr(world.player, "x", 0))
    cursor_y = getattr(world, "look_cursor_y", getattr(world.player, "y", 0))

    targets = list_tile_focus_targets(world, cursor_x, cursor_y)
    if targets:
        index = int(getattr(world, "look_focus_index", 0)) % len(targets)
        focus_text = describe_focus_target(world, targets[index])
        counter = f" {index + 1}/{len(targets)}" if len(targets) > 1 else ""
    else:
        focus_text = world.get_sensory_summary(cursor_x, cursor_y) if hasattr(world, "get_sensory_summary") else ""
        counter = ""

    banner_text = f" [LOOK] ({cursor_x}, {cursor_y}){counter} {focus_text} "
    hint_text = " [Arrows: Move | Tab: Next thing here | Enter/E: Examine | Esc: Exit] "
    console.print_box(
        0,
        max(0, console.height - 2),
        console.width,
        1,
        banner_text[:console.width - 2],
        fg=(255, 255, 120),
        bg=(30, 30, 60),
    )
    console.print_box(
        0,
        max(0, console.height - 1),
        console.width,
        1,
        hint_text[:console.width - 2],
        fg=(190, 185, 140),
        bg=(30, 30, 60),
    )


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

    draw_look_cursor(console, world, camera_x, camera_y)

    current_tile = world.get_tile_at(world.player.x, world.player.y)
    area_label = current_tile.name if current_tile else "Unknown"
    player_name = getattr(world.player, "name", "You")
    hud_text = (
        f"{player_name}  @ {area_label}  [{world.player.x},{world.player.y}]  "
        f"{world.weather.replace('_', ' ').title()}"
    )
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
    _draw_log_panel(console, world)

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

class MenuHitRegion(NamedTuple):
    """Where a menu drew its selectable rows, and what was in them.

    Mouse handling needs to turn a click position back into a list index,
    and several menus size themselves from their content (the crafting menu
    is as tall as it has recipes, up to a cap). Rather than recompute that
    layout in the input handler - a second copy that would silently drift
    from this one - each menu publishes what it actually drew, and
    main._menu_mouse_binding looks it up by game_state.
    """

    region: object
    scroll_offset: int
    total: int

    def index_at(self, mouse_x, mouse_y):
        return self.region.index_at(mouse_x, mouse_y, self.scroll_offset, self.total)


def _register_hit_region(world, key, region, *, scroll_offset=0, total=0):
    """Publish a menu's drawn row area for mouse hit-testing."""
    regions = getattr(world, "menu_hit_regions", None)
    if not isinstance(regions, dict):
        regions = {}
        try:
            world.menu_hit_regions = regions
        except AttributeError:
            return None
    record = MenuHitRegion(region=region, scroll_offset=int(scroll_offset), total=int(total))
    regions[key] = record
    return record


def _prepare_list(world, key, region, *, total, selected_index=0, scroll_offset=0):
    """Settle a list's scroll position, publish its hit region, and find the
    hovered row.

    Doing all three together is what keeps them consistent: the hover
    highlight, the click hit-test and the rows actually drawn all have to
    agree on the same scroll offset, and list_view clamps it internally.
    Clamping here first (idempotently) means every caller passes the same
    settled value to all three.
    """
    if selected_index is not None:
        scroll_offset = widgets.clamp_scroll(selected_index, scroll_offset, region.height)
    scroll_offset = max(0, min(int(scroll_offset), max(0, int(total) - region.height)))
    _register_hit_region(world, key, region, scroll_offset=scroll_offset, total=total)
    hovered = region.index_at(
        getattr(world, "mouse_x", None),
        getattr(world, "mouse_y", None),
        scroll_offset,
        total,
    )
    return scroll_offset, hovered


def draw_interaction_menu(console, world):
    """Draws the context-sensitive interaction menu."""
    ctx = world.interaction_context
    x, y = world.mouse_x, world.mouse_y

    actions = ctx["available_actions"]
    # Find longest action to determine menu width
    longest_action = max((len(action) for action in actions), default=0)
    width = max(15, longest_action + 5)
    height = len(actions) + 2

    # Adjust position to keep menu on screen
    if x + width > MAP_WIDTH:
        x = MAP_WIDTH - width
    if y + height > MAP_HEIGHT:
        y = MAP_HEIGHT - height

    target_name = ctx['target_entities'][ctx['selected_entity_index']]['name']
    widgets.panel(
        console, x, y, width, height,
        title=f"Interact: {target_name}", focused=True, bg=theme.PANEL_BG_RAISED,
    )

    region = widgets.ListRegion(x=x + 1, y=y + 1, width=width - 2, height=len(actions))
    _, hovered = _prepare_list(world, "INTERACTION_MENU", region, total=len(actions),
                               selected_index=ctx["selected_action_index"])
    widgets.list_view(
        console,
        region,
        [widgets.Row(text=action) for action in actions],
        selected_index=ctx["selected_action_index"],
        hovered_index=hovered,
        show_scrollbar=False,
    )

def _draw_recipe_detail_panel(console, x, y, width, height, title, *, requirement_label, requirements, footer=None):
    """Draw the side panel listing what a recipe needs.

    Shared by the crafting and construction menus, which differ only in
    where their ingredient list comes from and what the heading calls it.
    Each requirement is (name, quantity, satisfied).
    """
    widgets.panel(console, x, y, width, height, title=title)
    detail_y = y + theme.PAD_TOP
    detail_y = widgets.heading(console, x + theme.PAD_X, detail_y, requirement_label)
    for name, quantity, satisfied in requirements:
        detail_y = widgets.text_line(
            console, x + theme.PAD_X + 1, detail_y,
            f"- {name}: {quantity}",
            color=theme.TEXT if satisfied else theme.DANGER,
            width=width - theme.PAD_X - 3,
        )
    if footer is not None:
        footer_text, satisfied = footer
        detail_y += 1
        widgets.text_line(
            console, x + theme.PAD_X, detail_y, footer_text,
            color=theme.TEXT if satisfied else theme.DANGER,
            width=width - (theme.PAD_X * 2),
        )
    return detail_y


def draw_crafting_menu(console, world):
    """Draws the crafting menu UI."""
    all_recipes = world.crafting_menu_context.get("all_recipes", [])
    num_recipes = len(all_recipes)
    geometry = widgets.centered_menu(50, min(30, max(6, num_recipes + 4)))
    widgets.panel(console, *geometry, title="Crafting", focused=True)

    region = geometry.list_region(top_offset=0, bottom_margin=2)
    scroll_offset, hovered = _prepare_list(
        world, "CRAFTING_MENU", region, total=num_recipes,
        selected_index=world.crafting_menu_context.get("selected_recipe_index", 0),
        scroll_offset=world.crafting_menu_context.get("scroll_offset", 0),
    )

    if not all_recipes:
        widgets.empty_state(console, region, "No recipes available.")
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("Esc", "close")])
        return

    selected_index = world.crafting_menu_context.get("selected_recipe_index", 0)
    rows = []
    for recipe_key in all_recipes:
        item_def = TILE_DEFINITIONS.get(recipe_key, {})
        rows.append(widgets.Row(
            text=item_def.get("name", recipe_key),
            enabled=world.player_can_craft(recipe_key),
            icon_key=recipe_key,
        ))

    world.crafting_menu_context["scroll_offset"] = widgets.list_view(
        console,
        region,
        rows,
        selected_index=selected_index,
        scroll_offset=scroll_offset,
        hovered_index=hovered,
        icon_drawer=_draw_item_icon,
    )
    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Up/Down", "select"), ("Enter", "craft"), ("Esc", "close")])

    # Display selected recipe details
    if 0 <= selected_index < num_recipes:
        selected_key = all_recipes[selected_index]
        item_def = TILE_DEFINITIONS.get(selected_key, {})
        recipe = item_def.get("crafting_recipe", {})

        requirements = []
        for res_key, qty in recipe.items():
            res_def = TILE_DEFINITIONS.get(res_key, {})
            requirements.append((
                res_def.get("name", res_key),
                qty,
                world.player.has_item(res_key, qty),
            ))

        req_station = item_def.get("required_workstation")
        footer = None
        if req_station:
            footer = (f"Needs: {req_station}", world._is_player_near_workstation(req_station))

        _draw_recipe_detail_panel(
            console, geometry.x + geometry.width, geometry.y, 40, 20,
            "Recipe Details", requirement_label="Requires:",
            requirements=requirements, footer=footer,
        )

def _construction_material_name(material_key):
    """Display name for a build material, which may be defined as an item or
    as a placeable tile depending on the material."""
    item_def = ITEM_DEFINITIONS.get(material_key)
    tile_def = TILE_DEFINITIONS.get(material_key)
    return (
        (item_def or {}).get("name")
        or (tile_def or {}).get("name")
        or material_key.replace("_", " ").title()
    )


def draw_building_menu(console, world):
    """Draws the building menu UI."""
    all_recipes = world.building_menu_context.get("all_recipes", [])
    num_recipes = len(all_recipes)
    geometry = widgets.centered_menu(50, min(30, max(6, num_recipes + 4)))
    widgets.panel(console, *geometry, title="Construction", focused=True)

    region = geometry.list_region(top_offset=0, bottom_margin=2)
    scroll_offset, hovered = _prepare_list(
        world, "BUILDING_MENU", region, total=num_recipes,
        selected_index=world.building_menu_context.get("selected_recipe_index", 0),
        scroll_offset=world.building_menu_context.get("scroll_offset", 0),
    )

    if not all_recipes:
        widgets.empty_state(console, region, "No construction options.")
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("Esc", "close")])
        return

    selected_index = world.building_menu_context.get("selected_recipe_index", 0)
    rows = []
    for recipe_key in all_recipes:
        recipe = CONSTRUCTION_RECIPES.get(recipe_key, {})
        can_build = all(
            world.player.has_item(mat_key, mat_qty)
            for mat_key, mat_qty in recipe.get("materials", {}).items()
        )
        rows.append(widgets.Row(text=recipe.get("name", recipe_key), enabled=can_build))

    world.building_menu_context["scroll_offset"] = widgets.list_view(
        console,
        region,
        rows,
        selected_index=selected_index,
        scroll_offset=scroll_offset,
        hovered_index=hovered,
    )
    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Up/Down", "select"), ("Enter", "build"), ("Esc", "close")])

    # Display details
    if 0 <= selected_index < num_recipes:
        recipe = CONSTRUCTION_RECIPES.get(all_recipes[selected_index], {})
        details_x = geometry.x + geometry.width
        details_width = 40
        requirements = [
            (_construction_material_name(mat_key), mat_qty, world.player.has_item(mat_key, mat_qty))
            for mat_key, mat_qty in recipe.get("materials", {}).items()
        ]
        detail_y = _draw_recipe_detail_panel(
            console, details_x, geometry.y, details_width, 20,
            "Build Details", requirement_label="Materials:", requirements=requirements,
        )

        description = recipe.get("description", "")
        if description:
            console.print_box(
                x=details_x + theme.PAD_X, y=detail_y + 1,
                width=details_width - (theme.PAD_X * 2), height=5,
                string=description, fg=theme.TEXT_DIM,
            )

def _noticeboard_row(world, notice_id):
    """Build the display row for one noticeboard entry.

    Returns None for notices whose backing task/blueprint has since been
    resolved or removed, so stale ids are skipped rather than drawn blank.
    """
    if notice_id.startswith("job:"):
        job_task = world.town_board.get_employment_task(notice_id.split(":", 1)[1])
        if job_task is None:
            return None
        building = world.buildings_by_id.get(job_task.target_building_id)
        building_name = str(getattr(building, "building_type", "Unknown")).replace("_", " ")
        return widgets.Row(
            text=f"JOB: {job_task.profession_role} @ {building_name} - {job_task.daily_wage}/day",
            color=theme.INFO,
        )
    if notice_id.startswith("need:"):
        need_id = notice_id.split(":", 1)[1]
        need = next((n for n in getattr(world.town_board, "economic_needs", []) if n.id == need_id), None)
        if need is None:
            return None
        return widgets.Row(text=f"NEED: {need.description}", color=theme.DANGER)

    task = world.town_board.get_task(notice_id.split(":", 1)[1] if ":" in notice_id else notice_id)
    if task is None:
        return None
    blueprint = world.blueprints_by_id.get(task.blueprint_id)
    if blueprint is None:
        return None
    claimed = task.assigned_entity_id == world.player.id
    status = "Claimed" if claimed else "Open"
    return widgets.Row(
        text=(
            f"HAUL: {task.item_key.replace('_', ' ')} -> "
            f"{blueprint.target_build.replace('_', ' ')} "
            f"@ ({task.destination_x},{task.destination_y}) [{status}]"
        ),
        color=theme.HEADING if claimed else theme.TEXT,
    )


def _draw_noticeboard_post_job(console, world, geometry):
    """Draw the 'post a job listing' sub-screen of the noticeboard."""
    ctx = world.noticeboard_menu_context
    building = world._get_job_posting_building()
    role_options = world._get_job_posting_role_options(building)
    selected_role_index = ctx.get("selected_role_index", 0)
    selected_role = role_options[selected_role_index] if role_options else "No valid roles"
    building_name = str(getattr(building, "building_type", "Unassigned")).replace("_", " ").title()

    y = geometry.inner_y
    y = widgets.heading(console, geometry.inner_x, y, "Post Job Listing")
    y += 1
    y = widgets.field(console, geometry.inner_x, y, "Business", building_name, width=geometry.inner_width)
    y = widgets.field(console, geometry.inner_x, y, "Role", selected_role,
                      width=geometry.inner_width, value_color=theme.SELECTION)
    y = widgets.field(console, geometry.inner_x, y, "Daily Wage", f"{world.get_job_posting_wage()} coins",
                      width=geometry.inner_width)
    y += 1

    y = widgets.heading(console, geometry.inner_x, y, "Available Roles:")
    region = widgets.ListRegion(
        x=geometry.inner_x + 2, y=y,
        width=geometry.inner_width - 2,
        height=max(0, geometry.hint_row - y),
    )
    _, hovered = _prepare_list(world, "NOTICEBOARD_ROLES", region,
                               total=len(role_options), selected_index=selected_role_index)
    widgets.list_view(
        console, region,
        [widgets.Row(text=role) for role in role_options],
        selected_index=selected_role_index,
        hovered_index=hovered,
        show_cursor=False,
    )
    widgets.hint_bar(
        console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
        [("Up/Down", "role"), ("Left/Right", "wage"), ("Tab", "building"),
         ("Enter", "post"), ("Esc", "cancel")],
    )


def draw_noticeboard_menu(console, world):
    """Draw the TownBoard hauling notices and player-claimed tasks."""
    geometry = widgets.centered_menu(66, 20)
    widgets.panel(console, *geometry, title="Noticeboard", focused=True)

    if world.noticeboard_menu_context.get("mode") == "post_job":
        _draw_noticeboard_post_job(console, world, geometry)
        return

    task_ids = world.noticeboard_menu_context.get("task_ids", [])
    region = geometry.list_region(top_offset=0, bottom_margin=2)
    scroll_offset, hovered = _prepare_list(
        world, "NOTICEBOARD_MENU", region, total=len(task_ids),
        selected_index=world.noticeboard_menu_context.get("selected_task_index", 0),
        scroll_offset=world.noticeboard_menu_context.get("scroll_offset", 0),
    )

    if not task_ids:
        widgets.empty_state(console, region, "No active notices.")
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("P", "post job"), ("Esc", "close")])
        return

    # Rows are built for every notice (not just the visible window) so that
    # a notice whose task vanished doesn't shift the selection index.
    rows = [_noticeboard_row(world, notice_id) or widgets.Row(text="", enabled=False) for notice_id in task_ids]

    world.noticeboard_menu_context["scroll_offset"] = widgets.list_view(
        console, region, rows,
        selected_index=world.noticeboard_menu_context.get("selected_task_index", 0),
        scroll_offset=scroll_offset,
        hovered_index=hovered,
        show_cursor=False,
    )
    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Enter", "claim"), ("P", "post job"), ("Esc", "close")])

def draw_company_ledger_menu(console, world):
    """Draw the ledger for a player-owned building."""
    geometry = widgets.centered_menu(74, 22)
    widgets.panel(console, *geometry, title="Company Ledger", focused=True)

    building = world.get_company_ledger_building()
    if building is None:
        console.print_box(
            x=geometry.inner_x, y=geometry.inner_y,
            width=geometry.inner_width, height=geometry.height - 4,
            string="No owned property is currently linked to this ledger.",
            fg=theme.TEXT_MUTED,
        )
        return

    building_name = str(getattr(building, "building_type", "business")).replace("_", " ").title()
    selected_action_index = world.company_ledger_menu_context.get("selected_action_index", 0)
    amount_options = world.company_ledger_menu_context.get("amount_options", [1, 10, 50, 100])
    amount = world.get_company_ledger_amount()

    y = geometry.inner_y
    y = widgets.field(console, geometry.inner_x, y, "Property", building_name,
                      width=geometry.inner_width, value_color=theme.HEADING)
    y = widgets.field(console, geometry.inner_x, y, "Company Cash",
                      f"{world._get_trade_money_balance(building)} coins", width=geometry.inner_width)
    y = widgets.field(console, geometry.inner_x, y, "Your Wallet",
                      f"{world._get_trade_money_balance(world.player)} coins", width=geometry.inner_width)
    y = widgets.field(console, geometry.inner_x, y, "Transfer Amount", str(amount),
                      width=geometry.inner_width, value_color=theme.SELECTION)
    y += 1

    action_region = widgets.ListRegion(x=geometry.inner_x, y=y, width=geometry.inner_width, height=2)
    _, hovered = _prepare_list(world, "COMPANY_LEDGER_MENU", action_region,
                               total=2, selected_index=selected_action_index)
    widgets.list_view(
        console, action_region,
        [widgets.Row(text="Deposit Funds"), widgets.Row(text="Withdraw Funds")],
        selected_index=selected_action_index,
        hovered_index=hovered,
        show_scrollbar=False,
    )
    y += 3

    amount_label = " / ".join(
        f"[{option}]" if option == amount else str(option)
        for option in amount_options
    )
    y = widgets.text_line(console, geometry.inner_x, y, f"Quick Amounts: {amount_label}",
                          color=theme.TEXT_MUTED, width=geometry.inner_width)
    y += 1
    y = widgets.heading(console, geometry.inner_x, y, "Stock:")

    stock = world.get_company_ledger_stock_snapshot(building)
    if not stock:
        widgets.text_line(console, geometry.inner_x + 2, y, "No stock on hand.", color=theme.TEXT_MUTED)
    else:
        max_rows = max(0, geometry.hint_row - y)
        for item_key, quantity in stock[:max_rows]:
            item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key.replace("_", " ").title())
            y = widgets.text_line(console, geometry.inner_x + 2, y, f"- {item_name}: {quantity}",
                                  width=geometry.inner_width - 2)

    widgets.hint_bar(
        console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
        [("Up/Down", "action"), ("Left/Right", "amount"), ("Enter", "confirm"), ("Esc", "close")],
    )

def draw_social_menu(console, world):
    """Draw the player social interaction menu for the selected NPC."""
    geometry = widgets.centered_menu(74, 24)
    widgets.panel(console, *geometry, title="Social", focused=True)

    npc = world.get_social_menu_target()
    if npc is None:
        console.print_box(
            x=geometry.inner_x, y=geometry.inner_y,
            width=geometry.inner_width, height=geometry.height - 4,
            string="No social target is available.",
            fg=theme.TEXT_MUTED,
        )
        return

    attitude_label, attitude_score = world.get_social_attitude_label(npc)
    profession = getattr(getattr(npc, "economic", None), "profession", "Unemployed") or "Unemployed"
    mode = world.social_menu_context.get("mode", "root")

    _draw_entity_portrait(
        console,
        geometry.x + geometry.width - 2 - PORTRAIT_ZOOM,
        geometry.inner_y,
        npc,
    )

    y = geometry.inner_y
    y = widgets.field(console, geometry.inner_x, y, "Name", npc.name,
                      width=geometry.inner_width, value_color=theme.HEADING)
    y = widgets.field(console, geometry.inner_x, y, "Job", profession, width=geometry.inner_width)
    y = widgets.field(console, geometry.inner_x, y, "Attitude",
                      f"{attitude_label} ({attitude_score:+d})",
                      width=geometry.inner_width, value_color=theme.SOCIAL)
    y += 1

    if mode == "root":
        y = widgets.text_line(console, geometry.inner_x, y,
                              "Choose how you want to approach them:", color=theme.TEXT_MUTED)
        y += 1
        actions = world.get_social_menu_actions()
        region = widgets.ListRegion(x=geometry.inner_x + 2, y=y,
                                    width=geometry.inner_width - 2,
                                    height=max(0, geometry.hint_row - y))
        _, hovered = _prepare_list(
            world, "SOCIAL_MENU", region, total=len(actions),
            selected_index=world.social_menu_context.get("selected_action_index", 0),
        )
        widgets.list_view(
            console, region,
            [widgets.Row(text=label) for label in actions],
            selected_index=world.social_menu_context.get("selected_action_index", 0),
            hovered_index=hovered,
        )
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("Up/Down", "select"), ("Enter", "confirm"), ("Esc", "close")])
        return

    if mode == "gift":
        options = world.get_social_gift_options()
        subtitle = f"Give Gift   Wallet: {world.player.economic.money} coins"
    else:
        options = world.get_player_gossip_options()
        subtitle = "Share Gossip"
    y = widgets.text_line(console, geometry.inner_x, y, subtitle,
                          color=theme.TEXT_MUTED, width=geometry.inner_width)
    y += 1

    region = widgets.ListRegion(x=geometry.inner_x, y=y, width=geometry.inner_width,
                                height=max(0, geometry.hint_row - y))
    selected_option = max(0, min(len(options) - 1, world.social_menu_context.get("selected_option_index", 0)))
    scroll_offset, hovered = _prepare_list(
        world, "SOCIAL_MENU", region, total=len(options),
        selected_index=selected_option,
        scroll_offset=world.social_menu_context.get("scroll_offset", 0),
    )

    if not options:
        empty_text = (
            "You have nothing available to gift." if mode == "gift"
            else "You do not know any memories worth sharing."
        )
        console.print_box(
            x=region.x, y=region.y, width=region.width, height=max(1, region.height),
            string=empty_text, fg=theme.TEXT_MUTED,
        )
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("Esc", "back")])
        return

    rows = []
    for option in options:
        if mode == "gift":
            rows.append(widgets.Row(text=f"{option['label']}  (value {option.get('value', 0)})"))
        else:
            headline = option.headline or option.event_type.replace("_", " ").title()
            rows.append(widgets.Row(text=f"{headline}  [{option.importance_score}]"))

    world.social_menu_context["scroll_offset"] = widgets.list_view(
        console, region, rows,
        selected_index=selected_option,
        scroll_offset=scroll_offset,
        hovered_index=hovered,
        show_cursor=False,
    )
    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Up/Down", "select"), ("Enter", "confirm"), ("Esc", "back")])

def draw_governance_menu(console, world):
    """Draw the Town Hall governance menu."""
    geometry = widgets.centered_menu(78, 25)
    widgets.panel(console, *geometry, title="Governance", focused=True)

    town_hall = world.get_town_hall_building()
    treasury = world._get_trade_money_balance(town_hall) if town_hall is not None else 0
    tax_rate = int(float(getattr(world.politics, "tax_rate", 0.10)) * 100)

    y = geometry.inner_y
    y = widgets.field(console, geometry.inner_x, y, "Treasury", f"{treasury} coins",
                      width=geometry.inner_width, value_color=theme.HEADING)
    y = widgets.field(console, geometry.inner_x, y, "Tax Rate", f"{tax_rate}%", width=geometry.inner_width)
    y = widgets.field(console, geometry.inner_x, y, "Mayor", world.get_office_holder_name('Mayor'),
                      width=geometry.inner_width, value_color=theme.INFO)
    y = widgets.field(console, geometry.inner_x, y, "Captain",
                      world.get_office_holder_name('Captain of the Guard'),
                      width=geometry.inner_width, value_color=theme.INFO)
    y += 1

    ctx = world.governance_menu_context
    mode = ctx.get("mode", "root")
    if mode == "root":
        actions = world.get_governance_actions()
        region = widgets.ListRegion(x=geometry.inner_x + 2, y=y + 1,
                                    width=geometry.inner_width - 2,
                                    height=max(0, geometry.hint_row - y - 1))
        _, hovered = _prepare_list(world, "GOVERNANCE_MENU", region, total=len(actions),
                                   selected_index=ctx.get("selected_action_index", 0))
        widgets.list_view(
            console, region,
            [widgets.Row(text=label) for label in actions],
            selected_index=ctx.get("selected_action_index", 0),
            hovered_index=hovered,
        )
        widgets.hint_bar(
            console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
            [("Up/Down", "select"), ("Left/Right", "taxes"), ("Enter", "confirm"), ("Esc", "close")],
        )
        return

    targets = world.get_governance_targets()
    pending_action = ctx.get("pending_action", "Issue Order")
    y += 1
    y = widgets.text_line(console, geometry.inner_x, y,
                          f"{pending_action}: choose a target", color=theme.TEXT_MUTED)
    y += 1

    region = widgets.ListRegion(x=geometry.inner_x, y=y, width=geometry.inner_width,
                                height=max(0, geometry.hint_row - y))
    selected_target = max(0, min(len(targets) - 1, ctx.get("selected_target_index", 0)))
    scroll_offset, hovered = _prepare_list(
        world, "GOVERNANCE_MENU", region, total=len(targets),
        selected_index=selected_target, scroll_offset=ctx.get("scroll_offset", 0),
    )

    if not targets:
        widgets.empty_state(console, region, "No valid targets.")
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("Esc", "back")])
        return

    rows = []
    for target in targets:
        profession = getattr(getattr(target, "economic", None), "profession", "Citizen") or "Citizen"
        rows.append(widgets.Row(text=f"{target.name} (ID {target.id}) - {profession}"))

    ctx["scroll_offset"] = widgets.list_view(
        console, region, rows,
        selected_index=selected_target,
        scroll_offset=scroll_offset,
        hovered_index=hovered,
        show_cursor=False,
    )
    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Up/Down", "select"), ("Enter", "issue order"), ("Esc", "back")])

def _player_display_title(player):
    """The player's social title, falling back to their career title and then
    to a meaningful profession name."""
    title = player.social.title
    if title:
        return title
    title = player.career.display_title()
    if title:
        return title
    profession = str(getattr(player.economic, "profession", "Unemployed")).strip()
    if profession and profession.lower() not in {"unemployed", "creature"}:
        return profession
    return ""


def _equipped_item_name(item_key):
    """Display name for an equipped item key, which may be defined as a tile
    or as an item."""
    if not item_key:
        return "None"
    item_def = TILE_DEFINITIONS.get(item_key) or ITEM_DEFINITIONS.get(item_key, {})
    return item_def.get("name", item_key)


def draw_info_menu(console, world):
    """Draws the player information menu (stats and equipment)."""
    geometry = widgets.centered_menu(60, 40)
    widgets.panel(console, *geometry, title="Character Information", focused=True)

    inner_x = geometry.inner_x
    inner_width = geometry.inner_width
    y = geometry.inner_y

    y = widgets.field(console, inner_x, y, "Name", getattr(world.player, "name", "You"),
                      width=inner_width, value_color=theme.HEADING)
    y = widgets.field(console, inner_x, y, "Profession", world.player.economic.profession,
                      width=inner_width, value_color=theme.INFO)
    career_level = getattr(getattr(world.player, "career", None), "level", 0)
    if career_level:
        y = widgets.field(console, inner_x, y, "Career Level", career_level,
                          width=inner_width, value_color=theme.INFO)
    y = widgets.field(console, inner_x, y, "Coin", f"{world.player.economic.money}",
                      width=inner_width, value_color=theme.SUCCESS)

    y += 1
    y = widgets.rule(console, inner_x, y, inner_width)

    y = widgets.field(console, inner_x, y, "Fame", world.player.social.fame,
                      width=inner_width, value_color=theme.HEADING)
    y = widgets.field(console, inner_x, y, "Infamy", world.player.social.infamy,
                      width=inner_width, value_color=theme.DANGER)

    title = _player_display_title(world.player)
    if title:
        y = widgets.field(console, inner_x, y, "Title", title,
                          width=inner_width, value_color=theme.SELECTION)

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
        y = widgets.field(console, inner_x, y, "Expected Wage", f"{wage} coins/day",
                          width=inner_width, value_color=theme.SUCCESS)

    y += 1
    y = widgets.rule(console, inner_x, y, inner_width)
    y = widgets.heading(console, inner_x, y, "Equipment")

    y = widgets.text_line(
        console, inner_x + 1, y,
        f"- Light Source: {_equipped_item_name(world.player.equipment.equipped_light_item_key)}",
        width=inner_width - 1,
    )
    for slot in ["head", "body", "hands", "feet"]:
        item_name = _equipped_item_name(world.player.equipment.equipped_armor.get(slot))
        y = widgets.text_line(
            console, inner_x + 1, y, f"- {slot.capitalize()}: {item_name}",
            color=theme.TEXT if item_name != "None" else theme.TEXT_MUTED,
            width=inner_width - 1,
        )

    y += 1
    y = widgets.text_line(console, inner_x, y, "Inventory now has its own menu - press U.",
                          color=theme.TEXT_MUTED, width=inner_width)

    y += 2
    y = widgets.rule(console, inner_x, y, inner_width)
    y = widgets.heading(console, inner_x, y, "Active Quests")
    if not world.player.knowledge.active_quests:
        y = widgets.text_line(console, inner_x + 1, y, "- None", color=theme.TEXT_MUTED)
    else:
        for quest_data in world.player.knowledge.active_quests.values():
            y = widgets.text_line(console, inner_x + 1, y, f"- {quest_data['title']}", width=inner_width - 1)

    y += 1
    y = widgets.rule(console, inner_x, y, inner_width)
    y = widgets.heading(console, inner_x, y, "Faction Status")
    wars_found = False
    for village in world.villages:
        if village.at_war_with:
            wars_found = True
            for enemy_id in village.at_war_with:
                y = widgets.text_line(
                    console, inner_x + 1, y,
                    f"- Village {village.id[:4]} is at WAR with Village {enemy_id[:4]}",
                    color=theme.DANGER, width=inner_width - 1,
                )
    if not wars_found:
        widgets.text_line(console, inner_x + 1, y, "- The realm is at peace.", color=theme.SUCCESS)

    widgets.hint_bar(console, inner_x, geometry.hint_row, inner_width,
                     [("U", "inventory"), ("Q", "quests"), ("Esc", "close")])

def draw_inventory_menu(console, world):
    """Draws the dedicated scrollable inventory menu, grouping items by category."""
    menu_width = 60
    menu_height = 40
    x = (MAP_WIDTH - menu_width) // 2
    y = (SCREEN_HEIGHT - menu_height) // 2

    widgets.panel(console, x, y, menu_width, menu_height, title="Inventory", focused=True)

    widgets.hint_bar(console, x + theme.PAD_X, y + menu_height - 2, menu_width - (theme.PAD_X * 2),
                     [("Up/Down", "select"), ("Enter", "use"), ("Esc", "close")])

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

    # Flatten into display rows. Category headers and the money line carry
    # their own color and no icon; item rows take the color of their quality
    # tier and are indented by the icon itself.
    rows = [
        widgets.Row(text=f"Money: {world.player.economic.money} coins", color=theme.SUCCESS),
        widgets.Row(text=""),
    ]
    # Which display rows are actually items, in order. The input handler needs
    # this to turn "the third thing down" into an item key: the list is mostly
    # headers and spacers, so a raw row index is not a selection.
    selectable_keys = []
    selectable_rows = []
    for cat_name, items in categories.items():
        if not items:
            continue
        rows.append(widgets.Row(text=f"--- {cat_name} ---", color=theme.HEADING))
        for item_text, item_key, quality in items:
            selectable_keys.append(item_key)
            selectable_rows.append(len(rows))
            rows.append(widgets.Row(
                text=item_text,
                color=_quality_text_color(quality),
                icon_key=item_key,
            ))
        rows.append(widgets.Row(text=""))

    world.interaction_context["inventory_selectable"] = selectable_keys
    selected = world.interaction_context.get("inventory_selected_index", 0)
    if selectable_keys:
        selected = max(0, min(int(selected), len(selectable_keys) - 1))
    else:
        selected = 0
    world.interaction_context["inventory_selected_index"] = selected
    selected_row = selectable_rows[selected] if selectable_rows else None

    region = widgets.ListRegion(
        x=x + theme.PAD_X,
        y=y + theme.PAD_TOP,
        width=menu_width - (theme.PAD_X * 2),
        height=menu_height - 4,
    )
    _register_hit_region(
        world, "INVENTORY_MENU", region,
        scroll_offset=world.interaction_context.get("inventory_scroll_offset", 0),
        total=len(rows),
    )

    if len(rows) <= 2:
        widgets.empty_state(console, region, "Your inventory is empty.")
        return

    world.interaction_context["inventory_scroll_offset"] = widgets.list_view(
        console,
        region,
        rows,
        selected_index=None,
        scroll_offset=world.interaction_context.get("inventory_scroll_offset", 0),
        icon_drawer=_draw_item_icon,
        show_cursor=False,
    )


TRADE_NAME_WIDTH = 26


def draw_trade_menu(console, world):
    """Draws the trade menu UI."""
    geometry = widgets.centered_menu(60, 24)
    widgets.panel(console, *geometry, title="Trade", focused=True)

    target_name = world.trade_ui_npc_target.name if world.trade_ui_npc_target else "Trader"
    mode = "Selling to" if world.trade_ui_player_selling else "Buying from"

    y = geometry.inner_y
    y = widgets.text_line(console, geometry.inner_x, y, f"{mode} {target_name}",
                          color=theme.HEADING, width=geometry.inner_width)
    y = widgets.field(console, geometry.inner_x, y, "Your Purse",
                      f"{world.player.economic.money} coins", width=geometry.inner_width)
    y += 1

    selling = world.trade_ui_player_selling
    items = (
        world.trade_ui_player_inventory_snapshot if selling
        else world.trade_ui_merchant_inventory_snapshot
    )
    selected_index = (
        world.trade_ui_player_item_index if selling
        else world.trade_ui_merchant_item_index
    )

    region = widgets.ListRegion(x=geometry.inner_x, y=y, width=geometry.inner_width,
                                height=max(0, geometry.hint_row - y - 1))
    scroll_offset, hovered = _prepare_list(
        world, "TRADE_MENU", region, total=len(items), selected_index=selected_index,
        scroll_offset=selected_index,
    )

    if not items:
        widgets.empty_state(console, region, "No items available.")
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("Tab", "switch"), ("Esc", "close")])
        return

    rows = []
    for item_key, quantity, price in items:
        item_ref = _get_trade_row_item_reference(world, item_key, selling=selling)
        if item_ref is not None:
            item_name = item_ref.name
            color = _quality_text_color(item_ref.quality)
        else:
            item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
            color = theme.TEXT
        rows.append(widgets.Row(
            text=f"{item_name[:TRADE_NAME_WIDTH]:{TRADE_NAME_WIDTH}} x{quantity:<3} {price:>4}g",
            color=color,
            icon_key=item_key,
        ))

    widgets.list_view(
        console, region, rows,
        selected_index=selected_index,
        scroll_offset=scroll_offset,
        hovered_index=hovered,
        icon_drawer=_draw_item_icon,
        show_cursor=False,
    )
    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Tab", "switch"), ("Enter", "trade"), ("Esc", "close")])


def draw_knowledge_menu(console, world):
    """Draws the player's knowledge menu (known books, etc.)."""
    geometry = widgets.centered_menu(60, 30)
    widgets.panel(console, *geometry, title="Knowledge", focused=True)

    y = widgets.heading(console, geometry.inner_x, geometry.inner_y, "Books Read")

    titles = []
    for book_id in sorted(list(world.player.knowledge.known_books)):
        book = next((b for b in world.books if b.id == book_id), None)
        if book:
            titles.append(book.title)

    if not titles:
        widgets.text_line(console, geometry.inner_x + 1, y, "- None", color=theme.TEXT_MUTED)
    else:
        region = widgets.ListRegion(x=geometry.inner_x + 1, y=y,
                                    width=geometry.inner_width - 1,
                                    height=max(0, geometry.hint_row - y))
        widgets.list_view(
            console, region,
            [widgets.Row(text=f"- {title}") for title in titles],
            selected_index=None,
            show_cursor=False,
        )

    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Esc", "close")])

def draw_dialogue_menu(console, world):
    """Draws the interactive Dialogue UI."""
    geometry = widgets.centered_menu(60, 20)

    target_npc = getattr(world, 'chat_ui_target_npc', None)
    npc_name = world.get_entity_display_name(target_npc, include_relationship=True) if target_npc else "Unknown"
    widgets.panel(console, *geometry, title=f" Conversation with {npc_name} ", focused=True)

    raw_target_name = getattr(target_npc, 'name', None)
    display_target_name = world.get_entity_display_name(target_npc) if target_npc else None

    header_rows = 0
    if target_npc is not None:
        portrait_top = geometry.y + 1
        _draw_entity_portrait(console, geometry.inner_x, portrait_top, target_npc)
        console.print(
            x=geometry.inner_x + PORTRAIT_ZOOM + 1,
            y=portrait_top + (PORTRAIT_ZOOM // 2),
            string=(display_target_name or npc_name)[: geometry.inner_width - PORTRAIT_ZOOM - 1],
            fg=theme.HEADING,
        )
        header_rows = PORTRAIT_ZOOM + 1

    history_start_y = geometry.inner_y + header_rows
    max_history_lines = max(1, geometry.height - 4 - header_rows)
    wrapped_lines = []

    for speaker, text in getattr(world, 'chat_ui_history', []):
        if raw_target_name and speaker == raw_target_name:
            speaker = display_target_name
        color = theme.INFO if speaker == "Player" else theme.HEADING
        lines = textwrap.wrap(f"{speaker}: {text}", width=geometry.inner_width)
        for line in lines:
            wrapped_lines.append((line, color))

    # Show the tail of the conversation; older lines scroll off the top.
    cur_y = history_start_y
    for line_text, color in wrapped_lines[max(0, len(wrapped_lines) - max_history_lines):]:
        console.print(x=geometry.inner_x, y=cur_y, string=line_text, fg=color)
        cur_y += 1

    console.print(
        x=geometry.inner_x, y=geometry.y + geometry.height - 2,
        string="> " + getattr(world, 'chat_ui_input_line', '') + "_",
        fg=theme.TEXT,
    )

def _quest_objective_line(quest, world):
    """The objective row for a quest, as (text, satisfied), or None if the
    quest type has no tracked counter."""
    if quest["type"] == "fetch":
        item_name = quest["item_to_fetch_key"].replace("_", " ").title()
        required = quest["item_fetch_count"]
        # inventory is an Inventory (item_key -> total count), so get()
        # already gives the aggregate quantity.
        current = world.player.economic.inventory.get(quest["item_to_fetch_key"], 0)
        return f"- Fetch {item_name}: {current}/{required}", current >= required
    if quest["type"] == "kill":
        required = quest.get("target_count", 1)
        current = quest.get("progress", 0)
        return f"- Defeat targets: {current}/{required}", current >= required
    return None


def draw_quest_menu(console, world):
    """Draws the quest log menu."""
    geometry = widgets.centered_menu(70, 40)
    widgets.panel(console, *geometry, title="Quest Log", focused=True)

    list_width = 25
    details_x = geometry.x + list_width + 1
    details_width = geometry.width - list_width - 3

    # Vertical separator between the quest list and the detail pane.
    for row in range(1, geometry.height - 1):
        console.print(x=geometry.x + list_width, y=geometry.y + row,
                      string="│", fg=theme.FRAME)

    active_quests = list(world.player.knowledge.active_quests.values())
    num_quests = len(active_quests)

    region = widgets.ListRegion(x=geometry.inner_x, y=geometry.inner_y,
                                width=list_width - theme.PAD_X,
                                height=geometry.height - 4)
    scroll_offset, hovered = _prepare_list(
        world, "QUEST_MENU", region, total=num_quests,
        selected_index=world.quest_menu_context.get("selected_quest_index", 0),
        scroll_offset=world.quest_menu_context.get("scroll_offset", 0),
    )

    if not active_quests:
        widgets.empty_state(console, region, "No active quests.")
        widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                         [("Esc", "close")])
        return

    ctx = world.quest_menu_context
    selected_index = max(0, min(num_quests - 1, ctx.get("selected_quest_index", 0)))
    ctx["selected_quest_index"] = selected_index

    rows = []
    for quest in active_quests:
        title = quest["title"]
        if len(title) > region.width - 2:
            title = title[: region.width - 5] + "..."
        rows.append(widgets.Row(text=title))

    ctx["scroll_offset"] = widgets.list_view(
        console, region, rows,
        selected_index=selected_index,
        scroll_offset=scroll_offset,
        hovered_index=hovered,
        show_scrollbar=False,
    )

    # Draw Details
    selected_quest = active_quests[selected_index]
    detail_y = geometry.inner_y
    console.print_box(x=details_x + 1, y=detail_y, width=details_width, height=2,
                      string=selected_quest["title"], fg=theme.HEADING)
    detail_y += 2

    desc = selected_quest["description"]
    desc_height = console.get_height_rect(x=details_x + 1, y=detail_y, width=details_width,
                                          height=10, string=desc)
    console.print_box(x=details_x + 1, y=detail_y, width=details_width, height=desc_height,
                      string=desc, fg=theme.TEXT_DIM)
    detail_y += desc_height + 1

    detail_y = widgets.heading(console, details_x + 1, detail_y, "Objectives")
    objective = _quest_objective_line(selected_quest, world)
    if objective is not None:
        text, satisfied = objective
        widgets.text_line(console, details_x + 2, detail_y, text,
                          color=theme.SUCCESS if satisfied else theme.TEXT,
                          width=details_width - 1)

    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Up/Down", "select"), ("Esc", "close")])


HELP_CONTROLS = [
    ("Move", "Arrows / Left Click"),
    ("Interact", "E / Right Click"),
    ("Pause / Resume", "Space / P"),
    ("Sim Speed (1-4x)", "1 / 2 / 3"),
    ("Single Step", "."),
    ("Look Around", "L"),
    ("Talk", "T"),
    ("Character Info", "I"),
    ("Inventory", "U"),
    ("Crafting", "C"),
    ("Building", "B"),
    ("Quest Log", "Q"),
    ("Zoom", "Mouse Wheel"),
    ("Help", "?"),
    ("Save & Menu", "Esc"),
]


def draw_help_menu(console):
    """Draws the help menu with controls."""
    # Two rows per entry, plus the frame, the top padding and a blank row above
    # the hint footer - so the panel grows with the list instead of the last
    # entry creeping onto the footer as controls are added.
    geometry = widgets.centered_menu(50, len(HELP_CONTROLS) * 2 + 5)
    widgets.panel(console, *geometry, title="Help / Controls", focused=True)

    y = geometry.inner_y + 1
    for action, key in HELP_CONTROLS:
        console.print(x=geometry.inner_x + 2, y=y, string=f"{action:<16}", fg=theme.TEXT_DIM)
        console.print(x=geometry.inner_x + 18, y=y, string=key, fg=theme.HEADING)
        y += 2

    widgets.hint_bar(console, geometry.inner_x, geometry.hint_row, geometry.inner_width,
                     [("Esc", "close")])


def draw_book_reading_ui(console, world):
    """Draws the UI for reading a book."""
    ctx = world.book_reading_context
    book_id = ctx.get("book_id")
    if not book_id:
        return

    book = next((b for b in world.books if b.id == book_id), None)
    if not book:
        return

    geometry = widgets.centered_menu(80, 50)
    widgets.panel(console, *geometry, title=f"Reading: {book.title}", focused=True)

    # Byline, then the body text, wrapped to the page width. Blank source
    # lines are preserved so paragraph breaks survive wrapping.
    full_text = f"by {book.author_name} ({book.year_written})\n\n" + book.content
    wrapped_lines = []
    for line in full_text.splitlines():
        if line:
            wrapped_lines.extend(textwrap.wrap(line, width=geometry.inner_width))
        else:
            wrapped_lines.append("")

    region = widgets.ListRegion(
        x=geometry.inner_x, y=geometry.inner_y,
        width=geometry.inner_width, height=geometry.height - 4,
    )
    ctx["scroll_offset"] = widgets.list_view(
        console, region,
        [widgets.Row(text=line, color=theme.TEXT_DIM if index == 0 else theme.TEXT)
         for index, line in enumerate(wrapped_lines)],
        selected_index=None,
        scroll_offset=ctx.get("scroll_offset", 0),
        show_cursor=False,
    )
