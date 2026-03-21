# rendering/console_renderer.py

from tcod_compat import tcod
import textwrap
import itertools
import math
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, STATUS_PANEL_WIDTH,
    MINIMAP_WIDTH, MINIMAP_HEIGHT, MINIMAP_X, MINIMAP_Y,
    COLOR_PLAYER_STATUS_WET, COLOR_PLAYER_STATUS_FREEZING, COLOR_CURSOR_INFO_TEXT,
    WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE
)
from data.tiles import TILE_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from entities.animal import Animal
from engine import Player

TRADE_CAPABLE_PROFESSIONS = {"Merchant", "Miller", "Scribe", "Traveling Merchant"}

TERRAIN_BACKGROUNDS = {
    "plains": (22, 36, 20),
    "forest": (12, 28, 14),
    "road": (54, 48, 40),
    "wood_wall": (55, 34, 18),
    "stone_wall": (48, 48, 52),
    "door": (72, 48, 24),
    "wood_floor": (64, 42, 22),
    "window": (30, 48, 60),
    "water": (10, 30, 72),
    "deep_water": (4, 16, 48),
    "mountain": (42, 42, 46),
    "snow": (110, 118, 128),
    "tall_grass": (22, 44, 20),
    "flower": (60, 28, 44),
    "well": (46, 52, 64),
    "tilled_soil": (70, 42, 26),
    "wheat_plant_growing": (38, 60, 22),
    "wheat_plant_mature": (90, 82, 26),
    "fire_trap_active": (88, 18, 12),
}

DISPLAY_CHARS = {
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
    "wheat_plant_mature": "I",
    "fire_trap_active": "x",
}

def _clamp_color(color):
    return tuple(max(0, min(255, int(channel))) for channel in color)

def _dim_color(color, ratio=0.55):
    return _clamp_color((color[0] * ratio, color[1] * ratio, color[2] * ratio))

def _get_tile_key(tile):
    if tile is None:
        return None

    for key, definition in TILE_DEFINITIONS.items():
        if definition.get("name") == tile.name and ord(definition.get("char", " ")) == tile.char:
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
    tile_key = _get_tile_key(tile)
    if tile_key in DISPLAY_CHARS:
        return DISPLAY_CHARS[tile_key]
    if tile is None:
        return " "
    return chr(tile.char)

def _get_entity_style(entity):
    if getattr(getattr(entity, "physical", None), "is_dead", False):
        return (130, 130, 130), (46, 20, 20)
    if isinstance(entity, Player):
        return (255, 245, 140), (96, 44, 16)
    if isinstance(entity, Animal):
        return getattr(entity, "color", (180, 220, 140)), (24, 44, 18)
    return getattr(entity, "color", (255, 255, 255)), (36, 36, 72)

def _get_entity_marker(entity):
    if getattr(getattr(entity, "physical", None), "is_dead", False):
        return None
    if getattr(getattr(entity, "combat", None), "is_hostile_to_player", False):
        return "!", (255, 120, 120)
    if hasattr(entity, "active_quest") and getattr(entity, "active_quest", None):
        return "?", (255, 215, 120)
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
        if getattr(getattr(entity, "physical", None), "is_dead", False):
            continue
        if not is_visible(world, entity.x, entity.y):
            continue
        distance = abs(world.player.x - entity.x) + abs(world.player.y - entity.y)
        nearby.append((distance, entity))
    nearby.sort(key=lambda item: item[0])
    return nearby[:limit]

def _get_focus_summary(world):
    standing_tile = world.get_tile_at(world.player.x, world.player.y)
    standing_on = standing_tile.name if standing_tile else "Unknown"
    nearby = _get_visible_nearby_entities(world, limit=1)
    if nearby:
        distance, entity = nearby[0]
        return standing_on, f"{entity.name} ({distance}t)"
    return standing_on, "No one nearby"

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
    if tile_key in {"road", "wood_floor"}:
        return _lighten(fg_color, 0.04 if time_band == 0 else 0.0), bg_color
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
    mouse_world_x = camera_x + world.mouse_x
    mouse_world_y = camera_y + world.mouse_y
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

    screen_x = focus["x"] - camera_x
    screen_y = focus["y"] - camera_y
    if not (0 <= screen_x < MAP_WIDTH and 0 <= screen_y < MAP_HEIGHT):
        return

    pulse = _pulse(world, speed=18.0, low=0.15, high=0.4, phase=1.2)
    console.bg[screen_y, screen_x] = _lighten(tuple(console.bg[screen_y, screen_x]), pulse)

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
    console.print(x=badge_x, y=badge_y, string=info, fg=(255, 250, 210), bg=(24, 24, 36))

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

def _light_radius_for_world(world):
    light_name = getattr(world, "current_light_level_name", "DAY")
    if light_name == "PITCH BLACK":
        return 5
    if light_name == "NIGHT":
        return 7
    if light_name in {"DAWN", "DUSK"}:
        return 10
    return 15

def _apply_lighting_and_depth(console, world, camera_x, camera_y):
    light_radius = _light_radius_for_world(world)
    for y in range(MAP_HEIGHT):
        map_y = camera_y + y
        if not (0 <= map_y < WORLD_HEIGHT):
            continue
        for x in range(MAP_WIDTH):
            map_x = camera_x + x
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
            console.fg[y, x] = _dim_color(tuple(console.fg[y, x]), 0.65 + (0.45 * light_strength))
            console.bg[y, x] = _dim_color(tuple(console.bg[y, x]), 0.55 + (0.5 * light_strength))

            if getattr(tile, "blocks_fov", False):
                for shadow_dx, shadow_dy in ((1, 0), (0, 1), (1, 1)):
                    sx = x + shadow_dx
                    sy = y + shadow_dy
                    if 0 <= sx < MAP_WIDTH and 0 <= sy < MAP_HEIGHT:
                        console.bg[sy, sx] = _dim_color(tuple(console.bg[sy, sx]), 0.75)

def _draw_entity_markers(console, world, camera_x, camera_y):
    for entity in itertools.chain(world.npcs, world.village_npcs):
        marker = _get_entity_marker(entity)
        if marker is None or not is_visible(world, entity.x, entity.y):
            continue

        marker_char, marker_color = marker
        screen_x = entity.x - camera_x
        screen_y = entity.y - camera_y - 1
        if 0 <= screen_x < MAP_WIDTH and 0 <= screen_y < MAP_HEIGHT:
            console.print(x=screen_x, y=screen_y, string=marker_char, fg=marker_color, bg=(0, 0, 0))

def _draw_world_markers(console, world, camera_x, camera_y):
    marked = 0
    max_markers = 18

    for (item_x, item_y), items in world.items_on_map.items():
        if marked >= max_markers:
            break
        if not items or not is_visible(world, item_x, item_y):
            continue
        if max(abs(world.player.x - item_x), abs(world.player.y - item_y)) > 10:
            continue
        screen_x = item_x - camera_x
        screen_y = item_y - camera_y - 1
        if 0 <= screen_x < MAP_WIDTH and 0 <= screen_y < MAP_HEIGHT:
            console.print(x=screen_x, y=screen_y, string="*", fg=(255, 245, 160), bg=(24, 24, 24))
            marked += 1

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

            screen_x = world_x - camera_x
            screen_y = world_y - camera_y - 1
            if 0 <= screen_x < MAP_WIDTH and 0 <= screen_y < MAP_HEIGHT:
                console.print(x=screen_x, y=screen_y, string=marker_char, fg=marker_color, bg=(0, 0, 0))
                marked += 1

def _draw_status_panel_legacy(console, world):
    """Draws the status panel on the right side of the screen."""
    panel_x = MAP_WIDTH
    console.draw_frame(x=panel_x, y=0, width=STATUS_PANEL_WIDTH, height=SCREEN_HEIGHT,
                       title="Status", clear=True, fg=(255, 255, 255), bg=(0, 0, 0))

    y = 2

    # --- Time & Season ---
    day = world.game_time // (24 * 60)
    hour = (world.game_time // 60) % 24
    minute = world.game_time % 60
    time_str = f"Day {day}, {hour:02d}:{minute:02d}"
    season = world.seasons[world.current_season_index]
    weather = world.weather.replace('_', ' ').title()

    console.print(x=panel_x + 1, y=y, string=time_str, fg=(200, 200, 200))
    y += 1
    console.print(x=panel_x + 1, y=y, string=f"{season} - {weather}", fg=(150, 150, 255))
    y += 2

    # --- Vitals ---
    # HP Bar
    hp_pct = world.player.combat.hp / world.player.combat.max_hp if world.player.combat.max_hp > 0 else 0
    bar_width = STATUS_PANEL_WIDTH - 4
    filled_width = int(bar_width * hp_pct)

    console.print(x=panel_x + 1, y=y, string="Overall Health:", fg=(255, 100, 100))
    y += 1
    console.draw_rect(x=panel_x + 1, y=y, width=bar_width, height=1, ch=ord('░'), fg=(100, 0, 0)) # Empty
    if filled_width > 0:
        console.draw_rect(x=panel_x + 1, y=y, width=filled_width, height=1, ch=ord('█'), fg=(255, 0, 0)) # Filled
    console.print(x=panel_x + 2, y=y, string=f"{world.player.combat.hp}/{world.player.combat.max_hp}", fg=(255, 255, 255))
    y += 2

    # Draw small body part indicators if injured
    injured_parts = []
    for part, hp in world.player.combat.body_parts_hp.items():
        max_hp = world.player.combat.body_parts_max_hp.get(part, 1)
        if hp < max_hp:
            injured_parts.append((part, hp, max_hp))

    if injured_parts:
        console.print(x=panel_x + 1, y=y, string="Injuries:", fg=(255, 100, 0))
        y += 1
        for part, hp, max_hp in injured_parts[:4]: # Show top 4 injuries to save space
            hp_pct = hp / max_hp if max_hp > 0 else 0
            if hp_pct > 0.5: color = (255, 255, 0)
            elif hp_pct > 0: color = (255, 100, 0)
            else: color = (255, 0, 0)

            p_name = part.replace("_", " ").title()[:12]
            console.print(x=panel_x + 2, y=y, string=f"{p_name}: {hp}/{max_hp}", fg=color)
            y += 1
        if len(injured_parts) > 4:
            console.print(x=panel_x + 2, y=y, string=f"+{len(injured_parts) - 4} more...", fg=(100, 100, 100))
            y += 1

    # Hunger
    hunger_pct = min(1.0, world.player.physical.hunger / world.player.physical.max_hunger)
    filled_hunger = int(bar_width * hunger_pct)
    hunger_color = (0, 255, 0)
    if hunger_pct > 0.5: hunger_color = (255, 255, 0)
    if hunger_pct > 0.8: hunger_color = (255, 0, 0)

    console.print(x=panel_x + 1, y=y, string="Hunger:", fg=(255, 255, 0))
    y += 1
    console.draw_rect(x=panel_x + 1, y=y, width=bar_width, height=1, ch=ord('░'), fg=(50, 50, 0))
    if filled_hunger > 0:
        console.draw_rect(x=panel_x + 1, y=y, width=filled_hunger, height=1, ch=ord('█'), fg=hunger_color)
    y += 2

    # Thirst
    thirst_pct = min(1.0, world.player.physical.thirst / world.player.physical.max_thirst)
    filled_thirst = int(bar_width * thirst_pct)
    thirst_color = (0, 255, 255)
    if thirst_pct > 0.5: thirst_color = (0, 150, 255)
    if thirst_pct > 0.8: thirst_color = (0, 0, 255)

    console.print(x=panel_x + 1, y=y, string="Thirst:", fg=(0, 200, 255))
    y += 1
    console.draw_rect(x=panel_x + 1, y=y, width=bar_width, height=1, ch=ord('░'), fg=(0, 0, 50))
    if filled_thirst > 0:
        console.draw_rect(x=panel_x + 1, y=y, width=filled_thirst, height=1, ch=ord('█'), fg=thirst_color)
    y += 2

    # Status Effects
    if world.player.physical.status_effects:
        console.print(x=panel_x + 1, y=y, string="Conditions:", fg=(200, 200, 200))
        y += 1
        for effect in world.player.physical.status_effects:
            color = (255, 255, 255)
            if effect == "Wet": color = COLOR_PLAYER_STATUS_WET
            elif effect == "Freezing": color = COLOR_PLAYER_STATUS_FREEZING
            elif effect == "Overheating": color = (255, 100, 0)
            console.print(x=panel_x + 2, y=y, string=f"! {effect}", fg=color)
            y += 1
        y += 1

    # Active Quest (Top Priority)
    active_quests = list(world.player.knowledge.active_quests.values())
    if active_quests:
        console.print(x=panel_x + 1, y=y, string="Current Objective:", fg=(255, 215, 0))
        y += 1
        quest = active_quests[0]
        # Wrap title if too long
        title_lines = textwrap.wrap(quest["title"], width=STATUS_PANEL_WIDTH - 2)
        for line in title_lines:
            console.print(x=panel_x + 1, y=y, string=line, fg=(255, 255, 255))
            y += 1

        # Simple progress
        if quest["type"] == "fetch":
            item_key = quest["item_to_fetch_key"]
            req = quest["item_fetch_count"]
            curr = 0
            for item in world.player.economic.inventory:
                if item["key"] == item_key:
                    curr += item.get("quantity", 1)
            console.print(x=panel_x + 2, y=y, string=f"({curr}/{req})", fg=(200, 200, 200))
            y += 1
        elif quest["type"] == "kill":
            req = quest.get("target_count", 1)
            curr = quest.get("progress", 0)
            console.print(x=panel_x + 2, y=y, string=f"({curr}/{req})", fg=(200, 200, 200))
            y += 1

        if len(active_quests) > 1:
            console.print(x=panel_x + 1, y=y, string=f"+ {len(active_quests)-1} more (Press Q)", fg=(100, 100, 100))
            y += 1

    y += 1

    # Faction Reputations (Condensed)
    console.print(x=panel_x + 1, y=y, string="Reputation:", fg=(150, 150, 150))
    y += 1
    for faction, rep in world.player.social.reputation.items():
        if rep != 0:
            console.print(x=panel_x + 2, y=y, string=f"{faction[:3].upper()}: {rep}", fg=(200, 200, 200))
            y += 1

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
    day = world.game_time // (24 * 60)
    hour = (world.game_time // 60) % 24
    minute = world.game_time % 60
    time_str = f"Day {day}, {hour:02d}:{minute:02d}"
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
    y += 2

    y = _draw_minimap_panel(console, world, panel_x, y, panel_width, 12) + 1

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
            curr = 0
            for item in world.player.economic.inventory:
                if item["key"] == item_key:
                    curr += item.get("quantity", 1)

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
            console.print(x=panel_x + 2, y=y, string=f"{distance}t {label}: {entity.name}"[:panel_width - 3], fg=(200, 200, 200))
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
    """Draws information about the tile under the mouse cursor."""
    mouse_x, mouse_y = world.mouse_x, world.mouse_y
    if not (0 <= mouse_x < MAP_WIDTH and 0 <= mouse_y < MAP_HEIGHT):
        return

    world_x, world_y = camera_x + mouse_x, camera_y + mouse_y

    info_str = ""
    tile = world.get_tile_at(world_x, world_y)
    if tile:
        info_str = f"Tile: {tile.name} ({world_x}, {world_y})"

        # Add weather info to the cursor
        info_str += f" | Weather: {world.weather}"

        if tile.name == "Animal Corpse" and "animal_type" in tile.properties:
            info_str += f" ({tile.properties['animal_type'].replace('_', ' ')})"

    if info_str:
        # Print info at the bottom of the map view
        console.print(x=1, y=MAP_HEIGHT - 1, string=info_str, fg=COLOR_CURSOR_INFO_TEXT)

def is_visible(world, x, y):
    """Checks if a world coordinate is within the player's local FOV map."""
    fov_map = getattr(world, 'player_fov_map', None)
    if fov_map is None:
        # Fallback if FOV system isn't fully initialized
        return True

    if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
        return fov_map[y, x]
    return False

def _draw_visual_effect(console, effect, camera_x, camera_y):
    effect_type = getattr(effect, "effect_type", None)
    draw_x = int(round(getattr(effect, "x", 0))) - camera_x
    draw_y = int(round(getattr(effect, "y", 0))) - camera_y
    if not (0 <= draw_x < console.width and 0 <= draw_y < console.height):
        return

    if effect_type == "floating_text":
        console.print(x=draw_x, y=draw_y, string=getattr(effect, "text", ""), fg=getattr(effect, "color", (255, 255, 255)))
    elif effect_type == "projectile":
        console.print(x=draw_x, y=draw_y, string=getattr(effect, "char", "*"), fg=getattr(effect, "color", (255, 255, 0)))

def draw(console, world, camera_x, camera_y):
    """Draws the main game screen."""
    console.clear()

    # Draw the map
    fov_map = getattr(world, 'player_fov_map', None)
    exp_map = world.explored_map
    
    for y in range(MAP_HEIGHT):
        map_y = camera_y + y
        if not (0 <= map_y < WORLD_HEIGHT):
            continue
            
        chunk_y = map_y // CHUNK_SIZE
        local_y = map_y % CHUNK_SIZE
        chunk_row = world.chunks[chunk_y]

        for x in range(MAP_WIDTH):
            map_x = camera_x + x
            if not (0 <= map_x < WORLD_WIDTH):
                continue

            chunk_x = map_x // CHUNK_SIZE
            chunk = chunk_row[chunk_x]

            if not chunk.is_terrain_generated:
                world._generate_chunk_detail(chunk, chunk_x, chunk_y)

            tile = chunk.tiles[local_y][map_x % CHUNK_SIZE]

            if tile:
                is_in_fov = fov_map[map_y, map_x] if fov_map is not None else True
                bg_color = _get_tile_background(tile)
                fg_color = tile.color
                fg_color, bg_color = _animate_tile_colors(world, tile, fg_color, bg_color, map_x, map_y)
                if is_in_fov:
                    console.print(x=x, y=y, string=_get_tile_char(tile), fg=fg_color, bg=bg_color)
                    exp_map[map_y, map_x] = True
                elif exp_map[map_y, map_x]:
                    console.print(
                        x=x, y=y, string=_get_tile_char(tile),
                        fg=_dim_color(fg_color, 0.45),
                        bg=_dim_color(bg_color, 0.5)
                    )

    # Draw path visualizer
    if hasattr(world.player.state, 'current_path') and world.player.state.current_path:
        for px, py in world.player.state.current_path:
            screen_x = px - camera_x
            screen_y = py - camera_y
            if 0 <= screen_x < MAP_WIDTH and 0 <= screen_y < MAP_HEIGHT:
                # Draw path markers (e.g., small dots)
                # Only if visible in player FOV
                if is_visible(world, px, py):
                    console.print(x=screen_x, y=screen_y, string="•", fg=(0, 255, 0))

    # Draw Visual Effects
    for effect in world.visual_effects:
        _draw_visual_effect(console, effect, camera_x, camera_y)

    # Draw entities
    all_entities = itertools.chain(world.npcs, world.village_npcs, [world.player])
    for entity in sorted(all_entities, key=lambda e: e.render_order.value if hasattr(e, 'render_order') else 0):
        if isinstance(entity, Player) and entity.state.is_riding:
            continue

        # Use render coordinates if available (for smooth movement), else fall back to logic coordinates
        r_x = getattr(entity, 'render_x', entity.x)
        r_y = getattr(entity, 'render_y', entity.y)

        # Cast to int for grid rendering
        draw_x = int(round(r_x))
        draw_y = int(round(r_y))

        # Check visibility based on the *logical* position (so they don't disappear while moving into FOV)
        # Or check draw_x/y? Checking logical x/y is safer for consistency with FOV map.
        if is_visible(world, entity.x, entity.y) or is_visible(world, draw_x, draw_y):
            if 0 <= draw_x - camera_x < MAP_WIDTH and 0 <= draw_y - camera_y < MAP_HEIGHT:
                fg_color, bg_color = _get_entity_style(entity)
                console.print(x=draw_x - camera_x, y=draw_y - camera_y,
                              string=chr(entity.char), fg=fg_color, bg=bg_color)

    player_screen_x = world.player.x - camera_x
    player_screen_y = world.player.y - camera_y
    if 0 <= player_screen_x < MAP_WIDTH and 0 <= player_screen_y < MAP_HEIGHT:
        console.print(x=player_screen_x, y=player_screen_y, string="@", fg=(255, 248, 160), bg=(120, 55, 20))

    _apply_lighting_and_depth(console, world, camera_x, camera_y)
    if 0 <= player_screen_x < MAP_WIDTH and 0 <= player_screen_y < MAP_HEIGHT:
        console.print(x=player_screen_x, y=player_screen_y, string="@", fg=(255, 248, 160), bg=(120, 55, 20))
    _draw_entity_markers(console, world, camera_x, camera_y)
    _draw_world_markers(console, world, camera_x, camera_y)

    for distance, entity in _get_visible_nearby_entities(world, limit=3):
        screen_x = entity.x - camera_x
        screen_y = entity.y - camera_y - 1
        if 0 <= screen_x < MAP_WIDTH and 0 <= screen_y < MAP_HEIGHT:
            label = entity.name[:12]
            label_x = max(0, min(MAP_WIDTH - len(label), screen_x - (len(label) // 2)))
            console.print(x=label_x, y=screen_y, string=label, fg=(240, 240, 240), bg=(0, 0, 0))

    current_tile = world.get_tile_at(world.player.x, world.player.y)
    area_label = current_tile.name if current_tile else "Unknown"
    hud_text = f"@ {area_label}  [{world.player.x},{world.player.y}]  {world.weather.replace('_', ' ').title()}"
    console.print(x=1, y=1, string=hud_text[:MAP_WIDTH - 2], fg=(255, 255, 255), bg=(0, 0, 0))

    focus = _get_focus_target(world, camera_x, camera_y)
    _draw_focus_badge(console, world, focus, camera_x, camera_y)

    draw_status_panel(console, world, camera_x, camera_y)
    draw_cursor_info(console, world, camera_x, camera_y)

    # Draw chat/interaction UI if active
    if world.interaction_context["active"]:
        draw_interaction_menu(console, world)

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

    if world.game_state == "BOOK_READING":
        draw_book_reading_ui(console, world)

    if world.game_state == "TRADE_MENU" or world.trade_ui_active:
        draw_trade_menu(console, world)

    if world.game_state == "HELP_MENU":
        draw_help_menu(console)

    # Draw weather overlay
    draw_weather_overlay(console, world, camera_x, camera_y)

    # Draw Mouse Tooltip/Examine
    if 0 <= world.mouse_x < MAP_WIDTH and 0 <= world.mouse_y < MAP_HEIGHT:
        mouse_world_x = camera_x + world.mouse_x
        mouse_world_y = camera_y + world.mouse_y

        # Check if visible
        if is_visible(world, mouse_world_x, mouse_world_y):
            tile = world.get_tile_at(mouse_world_x, mouse_world_y)
            if tile:
                info_text = tile.name

                # Check for entities
                entities_here = []
                for entity in itertools.chain([world.player], world.all_npcs):
                    if entity.x == mouse_world_x and entity.y == mouse_world_y:
                        if hasattr(entity, "physical") and entity.physical.is_dead:
                            entities_here.append(f"Dead {entity.name}")
                        else:
                            entities_here.append(entity.name)

                if (mouse_world_x, mouse_world_y) in world.items_on_map:
                    items = world.items_on_map[(mouse_world_x, mouse_world_y)]
                    if items:
                        entities_here.append(f"Items ({len(items)})")

                if entities_here:
                    info_text += f" | {', '.join(entities_here)}"

                # Draw tooltip string near bottom right of map
                console.print(x=1, y=MAP_HEIGHT - 1, string=info_text[:MAP_WIDTH - 2], fg=COLOR_CURSOR_INFO_TEXT, bg=(0,0,0))

    # Draw chat log at the bottom
    y = SCREEN_HEIGHT - 6
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
    if world.weather == "rain" or world.weather == "storm":
        char = "'"
        color = (100, 150, 255) if world.weather == "rain" else (150, 150, 200)
        density = 0.1 if world.weather == "rain" else 0.3
    elif world.weather == "snow":
        char = "*"
        color = (255, 255, 255)
        density = 0.05
    else:
        return

    # Offset by time to create movement
    time_offset = world.game_time % 100

    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            # Using coordinate hash to generate deterministic pseudo-random layout that changes with time
            h = hash((x + camera_x + time_offset, y + camera_y + time_offset)) % 1000
            if h < density * 1000:
                if is_visible(world, camera_x + x, camera_y + y):
                    console.print(x=x, y=y, string=char, fg=color)

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
            console.print(x=x + 2, y=y + 1 + i, string=item_name, fg=color)

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
    if world.player.social.title:
        console.print(x=x + 2, y=stat_y, string=f"Title: {world.player.social.title}", fg=(0, 255, 255))
    stat_y += 2

    # Body Parts Health
    console.print(x=x + 2, y=stat_y, string="Body Status:", fg=(255, 100, 100))
    stat_y += 1
    for part, hp in world.player.combat.body_parts_hp.items():
        max_hp = world.player.combat.body_parts_max_hp.get(part, 1)
        part_name = part.replace("_", " ").title()

        # Color based on health
        hp_pct = hp / max_hp if max_hp > 0 else 0
        if hp_pct > 0.75: color = (0, 255, 0)
        elif hp_pct > 0.25: color = (255, 255, 0)
        elif hp_pct > 0: color = (255, 100, 0)
        else: color = (255, 0, 0)

        console.print(x=x + 3, y=stat_y, string=f"- {part_name}: {hp}/{max_hp}", fg=color)
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

    display_inventory = {}
    for item in world.player.economic.inventory:
        key = item["key"]
        qty = item.get("quantity", 1)
        display_inventory[key] = display_inventory.get(key, 0) + qty

    for item_key, quantity in sorted(display_inventory.items()):
        item_def = TILE_DEFINITIONS.get(item_key) or ITEM_DEFINITIONS.get(item_key, {})
        item_name = item_def.get("name", item_key)
        tags = item_def.get("item_type_tags", [])

        entry = f"{item_name} x{quantity}"

        if "armor" in tags or "weapon" in tags:
            categories["Weapons/Armor"].append(entry)
        elif "food" in tags or "drink" in tags or "consumable" in tags:
            categories["Food/Drink"].append(entry)
        elif "resource" in tags or "material" in tags:
            categories["Materials"].append(entry)
        else:
            categories["Miscellaneous"].append(entry)

    # Build the flattened list of lines to draw
    lines = []
    lines.append(f"Money: {world.player.economic.money} coins")
    lines.append("")

    for cat_name, items in categories.items():
        if items:
            lines.append(f"--- {cat_name} ---")
            for item_line in items:
                lines.append(f"  {item_line}")
            lines.append("")

    if not lines:
        lines.append("Your inventory is empty.")

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
            line_text = lines[list_index]
            fg_color = (255, 255, 255)
            if line_text.startswith("--- "):
                fg_color = (255, 215, 0)
            elif line_text.startswith("Money:"):
                fg_color = (150, 255, 150)
            console.print(x=x + 2, y=y + 2 + i, string=line_text[:menu_width-4], fg=fg_color)

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
        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
        color = (0, 255, 255) if item_index == selected_index else (255, 255, 255)
        console.print(
            x=x + 2,
            y=y + 5 + row,
            string=f"{item_name[:28]:28} x{quantity:<3} {price:>4}g",
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

            # Check player inventory for progress display
            current_count = 0
            for item in world.player.economic.inventory:
                if item["key"] == selected_quest["item_to_fetch_key"]:
                    current_count += item.get("quantity", 1)

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
