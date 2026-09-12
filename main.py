"""
This module contains the main game loop and handles player input.
"""
import argparse
import math
from types import SimpleNamespace
from tcod_compat import tcod, libtcodpy, TCOD_AVAILABLE
import os
import sys
import time
from engine import World
from config import (
    SCREEN_WIDTH_TILES,
    SCREEN_HEIGHT_TILES,
    MAP_WIDTH,
    MAP_HEIGHT,
    WORLD_WIDTH,
    WORLD_HEIGHT,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    TILESET_PATH,
    ZOOM_LEVELS,
    DEFAULT_ZOOM_INDEX,
    SECONDS_PER_GAME_TICK,
)
from data.items import ITEM_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from rendering import console_renderer
from rendering import title_art
from rendering import ui_theme as theme
from rendering import widgets
from rendering.console_renderer import draw
from rendering.sprite_atlas import register_zoomed_dawnlike_tiles
from presentation.sensory_observation import (
    describe_focus_target,
    list_tile_focus_targets,
    observe_focus_target,
)
from save_manager import save_game, load_game, load_save_metadata
from ui_requests import apply_ui_requests

TRADE_CAPABLE_PROFESSIONS = {"Merchant", "Miller", "Scribe", "Traveling Merchant"}
DEFAULT_PLAYER_FIRST_NAME = "Player"


def normalize_player_first_name(raw_name: str | None) -> str:
    """Return a safe player first name for new-game creation."""
    if raw_name is None:
        return DEFAULT_PLAYER_FIRST_NAME
    cleaned = "".join(ch for ch in str(raw_name) if ch.isalpha() or ch in {" ", "-", "'"}).strip()
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return DEFAULT_PLAYER_FIRST_NAME
    return cleaned[:20]


def _ensure_zoom_state(world: World) -> None:
    if not hasattr(world, "zoom_levels") or not getattr(world, "zoom_levels", None):
        world.zoom_levels = tuple(ZOOM_LEVELS)
    if not hasattr(world, "zoom_index"):
        world.zoom_index = min(max(0, DEFAULT_ZOOM_INDEX), len(world.zoom_levels) - 1)


def _get_zoom(world: World) -> float:
    _ensure_zoom_state(world)
    return float(world.zoom_levels[max(0, min(world.zoom_index, len(world.zoom_levels) - 1))])


def _get_world_view_size(world: World) -> tuple[int, int]:
    zoom = _get_zoom(world)
    view_width = max(1, int(math.ceil(MAP_WIDTH / zoom)))
    view_height = max(1, int(math.ceil(MAP_HEIGHT / zoom)))
    return min(WORLD_WIDTH, view_width), min(WORLD_HEIGHT, view_height)


def _get_camera_origin(world: World) -> tuple[int, int]:
    view_width, view_height = _get_world_view_size(world)
    camera_x = int(world.player.x) - view_width // 2
    camera_y = int(world.player.y) - view_height // 2
    camera_x = max(0, min(camera_x, max(0, WORLD_WIDTH - view_width)))
    camera_y = max(0, min(camera_y, max(0, WORLD_HEIGHT - view_height)))
    return camera_x, camera_y


def _screen_to_world_position(world: World, camera_x: int, camera_y: int, screen_x: int, screen_y: int) -> tuple[int, int]:
    zoom = _get_zoom(world)
    return camera_x + int(screen_x // zoom), camera_y + int(screen_y // zoom)


def _is_inside_map_view(world: World) -> bool:
    """Whether the cursor is over the world view rather than the surrounding UI.

    The console is wider and taller than the map, so the status panel down the
    right and the message log along the bottom are outside it. Converting a
    click there to a world position walks off the edge of the map, which is a
    meaningless place to inspect or path to. Mirrors the same check the renderer
    makes before it will hover-focus a tile.
    """
    return 0 <= world.mouse_x < MAP_WIDTH and 0 <= world.mouse_y < MAP_HEIGHT


def prompt_for_new_player_name(console, context) -> str | None:
    """Prompt for a player first name before generating a new world."""
    input_value = ""
    if hasattr(context, "start_text_input"):
        context.start_text_input()

    try:
        while True:
            console.clear()
            draw_character_create(console,input_value)
            context.present(console)

            for event in tcod.event.wait():
                context.convert_event(event)
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(event, tcod.event.TextInput):
                    if len(input_value) < 20:
                        input_value += event.text
                elif isinstance(event, tcod.event.KeyDown):
                    if event.sym == tcod.event.KeySym.ESCAPE:
                        return None
                    if event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912)):
                        return normalize_player_first_name(input_value)
                    if event.sym == tcod.event.KeySym.BACKSPACE:
                        input_value = input_value[:-1]
                    elif event.sym == tcod.event.KeySym.SPACE and len(input_value) < 20:
                        input_value += " "
                    elif 33 <= event.sym <= 126 and len(input_value) < 20:
                        char = chr(event.sym)
                        if char.isalpha() or char in {"-", "'"}:
                            try:
                                mod = getattr(event, 'mod', 0)
                                shifted = bool(mod & 3)
                            except Exception:
                                shifted = False
                            if shifted and char.islower():
                                char = char.upper()
                            input_value += char
                break
    finally:
        if hasattr(context, "stop_text_input"):
            context.stop_text_input()


def draw_character_create(console, input_value=""):
    _draw_menu_backdrop(console)
    center = console.width//2
    widgets.panel(console,center-28,17,56,21,title="A New Life",focused=True)
    console.print(center,21,"Enter your first name",alignment=libtcodpy.CENTER,fg=theme.TEXT)
    console.print(center-20,25," "*40,bg=theme.PANEL_BG_RAISED)
    console.print(center,25,(input_value[-20:] if input_value else "")+"_",
                  alignment=libtcodpy.CENTER,fg=theme.SELECTION,bg=theme.PANEL_BG_RAISED)
    console.print(center,29,"Your family gives you your last name.",alignment=libtcodpy.CENTER,fg=theme.TEXT_MUTED)
    console.print(center,35,"Enter  begin     Esc  return",alignment=libtcodpy.CENTER,fg=theme.HEADING)

def _get_player_facing_position(world: World) -> tuple[int, int]:
    """Return the coordinates directly in front of the player."""
    return (
        world.player.x + world.player.state.last_dx,
        world.player.y + world.player.state.last_dy,
    )


def _find_nearest_npc_to_talk_to(world: World, max_distance: int = 5):
    """Return the closest living NPC within talk range."""
    closest_npc = None
    max_distance_sq = max_distance * max_distance
    min_distance_sq = max_distance_sq + 1

    for npc in world.all_npcs:
        if npc.is_dead:
            continue

        distance_sq = (world.player.x - npc.x) ** 2 + (world.player.y - npc.y) ** 2
        if distance_sq <= max_distance_sq and distance_sq < min_distance_sq:
            min_distance_sq = distance_sq
            closest_npc = npc

    return closest_npc


def _get_actionable_entities(world: World, entities: list[dict]) -> list[tuple[dict, list[str]]]:
    """Return interactable entities paired with their available actions."""
    actionable_entities = []
    for entity in entities:
        actions = world._get_actions_for_entity(entity)
        if actions:
            actionable_entities.append((entity, actions))
    return actionable_entities


def _menu_mouse_binding(world):
    """Describe the currently open menu's clickable list, if it has one.

    Returns (region_key, select_fn, confirm_handler). `select_fn(index)`
    moves that menu's selection - which field that is depends on the menu
    and, for the menus with sub-modes, on which mode is showing.
    `confirm_handler` is the menu's existing keyboard handler, replayed
    with a synthetic Enter so a click confirms through exactly the same
    code path the keyboard does, rather than a parallel copy of it.
    """
    state = getattr(world, "game_state", None)

    if getattr(world, "interaction_context", {}).get("active"):
        def select(index):
            world.interaction_context["selected_action_index"] = index
        return "INTERACTION_MENU", select, handle_interaction_input

    if state == "CRAFTING_MENU":
        def select(index):
            world.crafting_menu_context["selected_recipe_index"] = index
        return "CRAFTING_MENU", select, handle_crafting_input

    if state == "BUILDING_MENU":
        def select(index):
            world.building_menu_context["selected_recipe_index"] = index
        return "BUILDING_MENU", select, handle_building_input

    if state == "QUEST_MENU":
        def select(index):
            world.quest_menu_context["selected_quest_index"] = index
        # The quest log has nothing to confirm - clicking just previews.
        return "QUEST_MENU", select, None

    if state == "NOTICEBOARD_MENU":
        if world.noticeboard_menu_context.get("mode") == "post_job":
            def select(index):
                world.noticeboard_menu_context["selected_role_index"] = index
            return "NOTICEBOARD_ROLES", select, handle_noticeboard_menu_input

        def select(index):
            world.noticeboard_menu_context["selected_task_index"] = index
        return "NOTICEBOARD_MENU", select, handle_noticeboard_menu_input

    if state == "COMPANY_LEDGER_MENU":
        def select(index):
            world.company_ledger_menu_context["selected_action_index"] = index
        return "COMPANY_LEDGER_MENU", select, handle_company_ledger_menu_input

    if state == "SOCIAL_MENU":
        if world.social_menu_context.get("mode", "root") == "root":
            def select(index):
                world.social_menu_context["selected_action_index"] = index
        else:
            def select(index):
                world.social_menu_context["selected_option_index"] = index
        return "SOCIAL_MENU", select, handle_social_menu_input

    if state == "GOVERNANCE_MENU":
        if world.governance_menu_context.get("mode", "root") == "root":
            def select(index):
                world.governance_menu_context["selected_action_index"] = index
        else:
            def select(index):
                world.governance_menu_context["selected_target_index"] = index
        return "GOVERNANCE_MENU", select, handle_governance_menu_input

    if state == "TRADE_MENU":
        def select(index):
            if world.trade_ui_player_selling:
                world.trade_ui_player_item_index = index
            else:
                world.trade_ui_merchant_item_index = index
        return "TRADE_MENU", select, handle_trade_menu_input

    if state == "INVENTORY_MENU":
        def select(index):
            rows = world.interaction_context.get("inventory_selectable_rows", [])
            if index not in rows:
                return False
            world.interaction_context["inventory_selected_index"] = rows.index(index)
        return "INVENTORY_MENU", select, handle_inventory_menu_input

    return None


def handle_menu_mouse_click(event, world, context) -> bool:
    """Route a click inside an open menu to that menu's list.

    A left click selects the row under the cursor and confirms it; a right
    click selects without confirming, so the player can inspect a recipe's
    requirements without committing to building it. Returns True if the
    click was consumed by a menu.
    """
    binding = _menu_mouse_binding(world)
    if binding is None:
        return False

    region_key, select, confirm_handler = binding
    record = (getattr(world, "menu_hit_regions", None) or {}).get(region_key)
    if record is None:
        return False

    index = record.index_at(getattr(world, "mouse_x", None), getattr(world, "mouse_y", None))
    if index is None:
        return False

    if select(index) is False:
        return True
    if event.button == tcod.event.MouseButton.LEFT and confirm_handler is not None:
        confirm_event = SimpleNamespace(sym=tcod.event.KeySym.RETURN)
        if confirm_handler is handle_interaction_input:
            return bool(confirm_handler(confirm_event, world, context))
        confirm_handler(confirm_event, world)
    return True


def _scroll_message_log(world, lines):
    """Scroll the message log back (positive) or forward (negative).

    Offset 0 means "pinned to the newest message", which is also where new
    messages push the view back to, so scrolling back to read something and
    then walking on doesn't leave the player stuck in the past.
    """
    entries = console_renderer._get_log_entries(world)
    max_scroll = max(0, len(entries) - console_renderer.LOG_VISIBLE_LINES)
    current = int(getattr(world, "chat_log_scroll", 0))
    world.chat_log_scroll = max(0, min(max_scroll, current + int(lines)))


def _neighbour_offsets_by_facing(facing_dx: int, facing_dy: int) -> list[tuple[int, int]]:
    """The eight neighbouring offsets, ordered from straight ahead round to behind.

    Interaction used to consider only the single tile the player last stepped
    towards, so walking north up to a door on your left left you pressing E at a
    blank wall with no clue why nothing happened. Ordering the whole ring by how
    closely it lines up with the way you are facing keeps the old behaviour when
    something is in front of you, and reaches the door when there isn't.
    """
    if (facing_dx, facing_dy) == (0, 0):
        facing_dx, facing_dy = 0, 1  # a player who has not moved yet faces south

    offsets = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dx, dy) != (0, 0)]

    def sort_key(offset):
        dx, dy = offset
        alignment = dx * facing_dx + dy * facing_dy  # positive ahead, negative behind
        return (-alignment, 1 if dx and dy else 0, dx, dy)

    return sorted(offsets, key=sort_key)


def _smart_interaction_candidates(world: World) -> list[tuple[int, int]]:
    """Tiles E will consider, best first: straight ahead, then around, then underfoot."""
    player = world.player
    offsets = _neighbour_offsets_by_facing(player.state.last_dx, player.state.last_dy)
    candidates = [(player.x + dx, player.y + dy) for dx, dy in offsets]
    candidates.append((player.x, player.y))
    return candidates


def _classify_smart_action(world: World, target_x: int, target_y: int, context_handler):
    """What E would do on one tile, as a callable, or None if there is nothing to do.

    Split out of execute_smart_interaction so the same rules decide both which
    of the surrounding tiles to act on and what to do once one is chosen.
    """
    if not hasattr(world, "get_tile_at"):
        return None
    tile = world.get_tile_at(target_x, target_y)
    if not tile:
        return None

    properties = getattr(tile, "properties", {})
    tile_name = getattr(tile, "name", "")

    # 1. Door Toggle
    if properties.get("is_door"):
        return lambda: world.player_attempt_toggle_door(target_x, target_y)

    # 2. Workstations
    ws_type = properties.get("workstation_type", "")
    if ws_type == "grinding_stone" or "Mill" in tile_name or "Grinding" in tile_name:
        return lambda: world.player_attempt_mill_flour(target_x, target_y)
    if ws_type in ["oven", "fire"] or "Oven" in tile_name:
        if world.player.has_item("flour"):
            return lambda: world.player_attempt_bake_bread(target_x, target_y)
        if ws_type == "fire":
            return lambda: world.player_attempt_cook(target_x, target_y)

    # 3. Crops & Soil
    if tile_name == "Wheat" or properties.get("is_harvestable"):
        return lambda: world.player_attempt_harvest(target_x, target_y)
    if tile_name == "Tilled Soil" and (world.player.has_item("wheat_seeds") or world.player.has_item("herb_generic")):
        return lambda: world.player_attempt_plant_seeds(target_x, target_y)
    if tile_name == "Plains" and (world.player.has_item("stone_hoe") or world.player.has_item("knife_stone")):
        return lambda: world.player_attempt_till_soil(target_x, target_y)

    # 4. Containers
    if properties.get("is_container") or "Chest" in tile_name:
        return lambda: world.player_attempt_loot_chest(target_x, target_y)

    # 5. Someone standing there
    occupants = [
        npc for npc in world.all_npcs
        if npc.x == target_x and npc.y == target_y and not getattr(npc, "is_dead", False)
    ]
    if occupants:
        return lambda: start_dialogue(world, occupants[0], context_handler)

    # 6. Tree
    if getattr(tile, "is_choppable", False):
        return lambda: world.player_attempt_chop_tree(target_x, target_y)

    return None


def execute_smart_interaction(world: World, context_handler) -> bool:
    """Performs the most natural in-world action within the player's reach."""
    candidates = _smart_interaction_candidates(world)

    for target_x, target_y in candidates:
        action = _classify_smart_action(world, target_x, target_y, context_handler)
        if action is not None:
            action()
            return True

    # Nothing has an obvious action, so offer a menu instead - on the first tile
    # that holds anything at all, which is usually what the player was reaching
    # for. Standing on a dropped item counts, hence the player's own tile.
    # Guarded like the get_tile_at check above, because callers pass in
    # stand-in world objects that implement only what they need.
    if hasattr(world, "_get_interactables_at"):
        for target_x, target_y in candidates:
            if world._get_interactables_at(target_x, target_y):
                open_interaction_menu(world, target_x, target_y)
                return False

    open_interaction_menu(world, *_get_player_facing_position(world))
    return False


def enter_look_mode(world: World) -> None:
    """Start Look Mode with the cursor on the player."""
    world.game_state = "LOOK_MODE"
    world.look_cursor_x = world.player.x
    world.look_cursor_y = world.player.y
    world.look_focus_index = 0
    world.add_message_to_chat_log(
        "Look Mode active. Arrows move the cursor, [Tab] cycles what is on the tile, "
        "[Enter] examines it, [Esc] exits."
    )


def _clamp_look_cursor(world: World) -> None:
    """Keep the look cursor inside the world and inside the visible map view.

    The camera stays on the player, so a cursor free to roam the whole world
    spends most of its time off screen with nothing to show the player where it
    went. Bounding it to the view means the highlight is always somewhere they
    can see.
    """
    view_width, view_height = _get_world_view_size(world)
    camera_x, camera_y = _get_camera_origin(world)
    world.look_cursor_x = max(camera_x, min(camera_x + view_width - 1, int(world.look_cursor_x)))
    world.look_cursor_y = max(camera_y, min(camera_y + view_height - 1, int(world.look_cursor_y)))
    world.look_cursor_x = max(0, min(WORLD_WIDTH - 1, world.look_cursor_x))
    world.look_cursor_y = max(0, min(WORLD_HEIGHT - 1, world.look_cursor_y))


def get_look_focus_targets(world: World) -> list[dict]:
    """Everything on the looked-at tile, in the order Look Mode steps through."""
    if not hasattr(world, "look_cursor_x"):
        return []
    return list_tile_focus_targets(world, world.look_cursor_x, world.look_cursor_y)


def get_look_focus_target(world: World) -> dict | None:
    """The one thing on the tile Look Mode is currently focused on."""
    targets = get_look_focus_targets(world)
    if not targets:
        return None
    index = int(getattr(world, "look_focus_index", 0)) % len(targets)
    return targets[index]


def handle_look_mode_input(event: tcod.event.KeyDown, world: World) -> bool:
    """Handles cursor movement, focus cycling and inspection in Look Mode."""
    if not hasattr(world, "look_cursor_x"):
        world.look_cursor_x, world.look_cursor_y = world.player.x, world.player.y

    move_keys = {
        tcod.event.KeySym.UP: (0, -1), tcod.event.KeySym.DOWN: (0, 1),
        tcod.event.KeySym.LEFT: (-1, 0), tcod.event.KeySym.RIGHT: (1, 0),
    }

    if event.sym in move_keys:
        dx, dy = move_keys[event.sym]
        world.look_cursor_x += dx
        world.look_cursor_y += dy
        _clamp_look_cursor(world)
        # A new tile holds different things, so start from the top of its list.
        world.look_focus_index = 0
        summary = world.get_sensory_summary(world.look_cursor_x, world.look_cursor_y)
        if summary:
            world.add_message_to_chat_log(summary)
        return False
    elif event.sym == tcod.event.KeySym.TAB:
        targets = get_look_focus_targets(world)
        if len(targets) <= 1:
            world.add_message_to_chat_log("Nothing else on this tile.")
            return False
        world.look_focus_index = (int(getattr(world, "look_focus_index", 0)) + 1) % len(targets)
        world.add_message_to_chat_log(
            f"{world.look_focus_index + 1}/{len(targets)} {describe_focus_target(world, targets[world.look_focus_index])}"
        )
        return False
    elif event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912), tcod.event.KeySym.E):
        target = get_look_focus_target(world)
        if target is None:
            world.add_message_to_chat_log(world.inspect_tile(world.look_cursor_x, world.look_cursor_y))
        else:
            world.add_message_to_chat_log(observe_focus_target(world, target))
        return False
    elif event.sym in (tcod.event.KeySym.ESCAPE, getattr(tcod.event.KeySym, 'l', tcod.event.KeySym.ESCAPE)):
        world.game_state = "PLAYING"
        world.add_message_to_chat_log("Exited Look Mode.")
        return False

    return False


def handle_playing_input(event: tcod.event.KeyDown, world: World, context_handler) -> bool:
    """Handles input when the player is in the 'PLAYING' state. Returns True if turn taken."""
    move_keys = {
        tcod.event.KeySym.UP: (0, -1), tcod.event.KeySym.DOWN: (0, 1),
        tcod.event.KeySym.LEFT: (-1, 0), tcod.event.KeySym.RIGHT: (1, 0),
    }

    if event.sym in move_keys:
        if world.game_time < getattr(world.player.state, "move_ready_tick", 0):
            return False
        dx, dy = move_keys[event.sym]
        action_cost = world.handle_player_movement(dx, dy)
        if action_cost > 0:
            world.player.state.move_ready_tick = world.game_time + action_cost
            if getattr(world, "is_paused", False):
                advance_committed_action(world, action_cost)
            return True
    elif event.sym == tcod.event.KeySym.F:
        open_combat_menu(world)
        return False
    elif event.sym == tcod.event.KeySym.C:
        world.game_state = "CRAFTING_MENU"
        world.crafting_menu_context["all_recipes"] = [
            key for key, definition in ITEM_DEFINITIONS.items() if "crafting_recipe" in definition
        ]
        world.crafting_menu_context["all_recipes"].sort(key=lambda k: ITEM_DEFINITIONS[k].get("name", k))
    elif event.sym == tcod.event.KeySym.B:
        world.game_state = "BUILDING_MENU"
        world.building_menu_context["all_recipes"] = list(CONSTRUCTION_RECIPES.keys())
        world.building_menu_context["all_recipes"].sort(key=lambda k: CONSTRUCTION_RECIPES[k].get("name", k))
    elif event.sym == tcod.event.KeySym.I:
        world.game_state = "INFO_MENU"
    elif hasattr(tcod.event.KeySym, 'u') and event.sym == tcod.event.KeySym.u:
        world.game_state = "INVENTORY_MENU"
    elif hasattr(tcod.event.KeySym, 'U') and event.sym == tcod.event.KeySym.U:
        world.game_state = "INVENTORY_MENU"
    elif event.sym == tcod.event.KeySym.Q:
        world.game_state = "QUEST_MENU"
        world.quest_menu_context["selected_quest_index"] = 0
    elif event.sym in (tcod.event.KeySym.E, getattr(tcod.event.KeySym, 'e', tcod.event.KeySym.E)):
        if execute_smart_interaction(world, context_handler):
            return True
    elif event.sym in (tcod.event.KeySym.SPACE, getattr(tcod.event.KeySym, 'p', tcod.event.KeySym.SPACE), getattr(tcod.event.KeySym, 'P', tcod.event.KeySym.SPACE)):
        world.is_paused = not getattr(world, "is_paused", False)
        status_msg = "Simulation Paused." if world.is_paused else f"Simulation Resumed ({getattr(world, 'simulation_speed', 1.0):.0f}x)."
        world.add_message_to_chat_log(status_msg, category="system")
    elif event.sym in (getattr(tcod.event.KeySym, 'N1', None), getattr(tcod.event.KeySym, 'KP_1', None), getattr(tcod.event.KeySym, '_1', None)) or event.sym == 49:
        world.simulation_speed = 1.0
        world.is_paused = False
        world.add_message_to_chat_log("Simulation speed: 1x (Normal)", category="system")
    elif event.sym in (getattr(tcod.event.KeySym, 'N2', None), getattr(tcod.event.KeySym, 'KP_2', None), getattr(tcod.event.KeySym, '_2', None)) or event.sym == 50:
        world.simulation_speed = 2.0
        world.is_paused = False
        world.add_message_to_chat_log("Simulation speed: 2x (Fast)", category="system")
    elif event.sym in (getattr(tcod.event.KeySym, 'N3', None), getattr(tcod.event.KeySym, 'KP_3', None), getattr(tcod.event.KeySym, '_3', None)) or event.sym == 51:
        world.simulation_speed = 4.0
        world.is_paused = False
        world.add_message_to_chat_log("Simulation speed: 4x (Ultra)", category="system")
    elif event.sym in (getattr(tcod.event.KeySym, 'N0', None), getattr(tcod.event.KeySym, 'KP_0', None), getattr(tcod.event.KeySym, '_0', None)) or event.sym == 48:
        world.is_paused = True
        world.add_message_to_chat_log("Simulation Paused.", category="system")
    elif event.sym in (getattr(tcod.event.KeySym, 'PERIOD', None), getattr(tcod.event.KeySym, 'KP_PERIOD', None)) or event.sym == 46:
        # Step 1 tick while paused
        world.update()
        world.add_message_to_chat_log("Stepped 1 tick.", category="system")
        return True
    elif hasattr(tcod.event.KeySym, 'l') and event.sym in (tcod.event.KeySym.l, getattr(tcod.event.KeySym, 'L', tcod.event.KeySym.l)):
        enter_look_mode(world)
    elif event.sym == tcod.event.KeySym.T:
        closest_npc = _find_nearest_npc_to_talk_to(world)

        if closest_npc:
            start_dialogue(world, closest_npc, context_handler)
        else:
            world.add_message_to_chat_log("There's no one nearby to talk to.")
    elif event.sym in (tcod.event.KeySym.QUESTION, tcod.event.KeySym.SLASH):
        world.game_state = "HELP_MENU"
    elif event.sym == getattr(tcod.event.KeySym, "PAGEUP", "PAGEUP"):
        _scroll_message_log(world, +console_renderer.LOG_VISIBLE_LINES)
    elif event.sym == getattr(tcod.event.KeySym, "PAGEDOWN", "PAGEDOWN"):
        _scroll_message_log(world, -console_renderer.LOG_VISIBLE_LINES)
    elif event.sym == tcod.event.KeySym.F3:
        world.show_autonomy_overlay = not getattr(world, "show_autonomy_overlay", False)
    elif event.sym == tcod.event.KeySym.ESCAPE:
        # Show in-game menu or save prompt
        save_game(world)
        world.add_message_to_chat_log("Game Saved.", category="system")

def handle_crafting_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is in the 'CRAFTING_MENU' state."""
    ctx = world.crafting_menu_context
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.C):
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.UP and ctx["all_recipes"]:
        ctx["selected_recipe_index"] = (ctx["selected_recipe_index"] - 1) % len(ctx["all_recipes"])
    elif event.sym == tcod.event.KeySym.DOWN and ctx["all_recipes"]:
        ctx["selected_recipe_index"] = (ctx["selected_recipe_index"] + 1) % len(ctx["all_recipes"])
    elif event.sym == tcod.event.KeySym.RETURN and 0 <= ctx["selected_recipe_index"] < len(ctx["all_recipes"]):
        selected_key = ctx["all_recipes"][ctx["selected_recipe_index"]]
        world.craft_item(selected_key)

def handle_building_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is in the 'BUILDING_MENU' state."""
    ctx = world.building_menu_context
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.B):
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.UP and ctx["all_recipes"]:
        ctx["selected_recipe_index"] = (ctx["selected_recipe_index"] - 1) % len(ctx["all_recipes"])
    elif event.sym == tcod.event.KeySym.DOWN and ctx["all_recipes"]:
        ctx["selected_recipe_index"] = (ctx["selected_recipe_index"] + 1) % len(ctx["all_recipes"])
    elif event.sym == tcod.event.KeySym.RETURN and 0 <= ctx["selected_recipe_index"] < len(ctx["all_recipes"]):
        selected_key = ctx["all_recipes"][ctx["selected_recipe_index"]]
        # Build at the location in front of the player
        target_x, target_y = _get_player_facing_position(world)
        world.player_attempt_build(selected_key, target_x, target_y)
        # Optionally close menu after build? Or keep open for multiple builds?
        # Let's keep it open for now, maybe they want to build a wall.

def handle_noticeboard_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is viewing the noticeboard."""
    ctx = world.noticeboard_menu_context
    key_sym = getattr(event, "sym", None)
    is_post_job_key = key_sym in (ord("p"), ord("P"))
    if hasattr(tcod.event.KeySym, "p") and key_sym == tcod.event.KeySym.p:
        is_post_job_key = True
    if hasattr(tcod.event.KeySym, "P") and key_sym == tcod.event.KeySym.P:
        is_post_job_key = True

    if ctx.get("mode") == "post_job":
        building = world._get_job_posting_building()
        role_options = world._get_job_posting_role_options(building)
        owned_buildings = world._get_player_owned_buildings()

        if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.E):
            world.open_noticeboard_menu()
        elif event.sym == tcod.event.KeySym.UP and role_options:
            ctx["selected_role_index"] = (ctx.get("selected_role_index", 0) - 1) % len(role_options)
        elif event.sym == tcod.event.KeySym.DOWN and role_options:
            ctx["selected_role_index"] = (ctx.get("selected_role_index", 0) + 1) % len(role_options)
        elif event.sym == tcod.event.KeySym.LEFT and ctx.get("wage_options"):
            ctx["selected_wage_index"] = (ctx.get("selected_wage_index", 0) - 1) % len(ctx["wage_options"])
        elif event.sym == tcod.event.KeySym.RIGHT and ctx.get("wage_options"):
            ctx["selected_wage_index"] = (ctx.get("selected_wage_index", 0) + 1) % len(ctx["wage_options"])
        elif event.sym == tcod.event.KeySym.TAB and owned_buildings:
            current_building = world._get_job_posting_building()
            current_index = owned_buildings.index(current_building) if current_building in owned_buildings else 0
            next_index = (current_index + 1) % len(owned_buildings)
            ctx["posting_building_id"] = owned_buildings[next_index].id
            ctx["selected_role_index"] = 0
        elif event.sym == tcod.event.KeySym.RETURN and building and role_options:
            selected_role = role_options[min(len(role_options) - 1, ctx.get("selected_role_index", 0))]
            world.post_employment_listing(building, selected_role, world.get_job_posting_wage())
        return

    task_ids = ctx.get("task_ids", [])
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.E):
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.UP and task_ids:
        ctx["selected_task_index"] = max(0, ctx.get("selected_task_index", 0) - 1)
    elif event.sym == tcod.event.KeySym.DOWN and task_ids:
        ctx["selected_task_index"] = min(len(task_ids) - 1, ctx.get("selected_task_index", 0) + 1)
    elif is_post_job_key:
        world.open_job_posting_menu()
    elif event.sym == tcod.event.KeySym.RETURN and 0 <= ctx.get("selected_task_index", 0) < len(task_ids):
        selected_notice = task_ids[ctx["selected_task_index"]]
        if selected_notice.startswith("haul:"):
            world.claim_noticeboard_task(selected_notice.split(":", 1)[1])
        elif selected_notice.startswith("need:"):
            world.claim_noticeboard_task(selected_notice.split(":", 1)[1])

def handle_company_ledger_menu_input(event: tcod.event.KeyDown, world: World):
    """Handle keyboard input for the company ledger menu."""
    ctx = world.company_ledger_menu_context
    actions = ["Deposit Funds", "Withdraw Funds"]
    amount_options = ctx.get("amount_options", [1, 10, 50, 100])

    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.E):
        world.game_state = "PLAYING"
        return
    if event.sym == tcod.event.KeySym.UP:
        ctx["selected_action_index"] = (ctx.get("selected_action_index", 0) - 1) % len(actions)
        return
    if event.sym == tcod.event.KeySym.DOWN:
        ctx["selected_action_index"] = (ctx.get("selected_action_index", 0) + 1) % len(actions)
        return
    if event.sym == tcod.event.KeySym.LEFT and amount_options:
        ctx["selected_amount_index"] = (ctx.get("selected_amount_index", 0) - 1) % len(amount_options)
        return
    if event.sym == tcod.event.KeySym.RIGHT and amount_options:
        ctx["selected_amount_index"] = (ctx.get("selected_amount_index", 0) + 1) % len(amount_options)
        return
    if event.sym == tcod.event.KeySym.RETURN:
        building = world.get_company_ledger_building()
        if building is None:
            world.game_state = "PLAYING"
            world.add_message_to_chat_log("This ledger is no longer available.")
            return
        amount = world.get_company_ledger_amount()
        withdraw = ctx.get("selected_action_index", 0) == 1
        world.transfer_company_funds(building, amount, withdraw=withdraw)

def handle_governance_menu_input(event: tcod.event.KeyDown, world: World):
    """Handle keyboard input for the governance menu."""
    ctx = world.governance_menu_context
    mode = ctx.get("mode", "root")

    if event.sym == tcod.event.KeySym.ESCAPE:
        if mode == "root":
            world.close_governance_menu()
        else:
            ctx["mode"] = "root"
            ctx["selected_target_index"] = 0
            ctx["scroll_offset"] = 0
        return

    if mode == "root":
        actions = world.get_governance_actions()
        if not actions:
            world.close_governance_menu()
            return
        if event.sym == tcod.event.KeySym.UP:
            ctx["selected_action_index"] = (ctx.get("selected_action_index", 0) - 1) % len(actions)
        elif event.sym == tcod.event.KeySym.DOWN:
            ctx["selected_action_index"] = (ctx.get("selected_action_index", 0) + 1) % len(actions)
        elif event.sym == tcod.event.KeySym.LEFT and actions[ctx.get("selected_action_index", 0)] == "Adjust Taxes":
            world.adjust_city_tax_rate(-0.01)
        elif event.sym == tcod.event.KeySym.RIGHT and actions[ctx.get("selected_action_index", 0)] == "Adjust Taxes":
            world.adjust_city_tax_rate(0.01)
        elif event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912)):
            selected_action = actions[ctx.get("selected_action_index", 0)]
            if selected_action == "Adjust Taxes":
                world.adjust_city_tax_rate(0.01)
            else:
                ctx["mode"] = "target_select"
                ctx["pending_action"] = selected_action
                ctx["selected_target_index"] = 0
                ctx["scroll_offset"] = 0
        return

    targets = world.get_governance_targets()
    if not targets:
        ctx["mode"] = "root"
        return
    if event.sym == tcod.event.KeySym.UP:
        ctx["selected_target_index"] = (ctx.get("selected_target_index", 0) - 1) % len(targets)
    elif event.sym == tcod.event.KeySym.DOWN:
        ctx["selected_target_index"] = (ctx.get("selected_target_index", 0) + 1) % len(targets)
    elif event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912)):
        target = targets[ctx.get("selected_target_index", 0)]
        pending_action = ctx.get("pending_action")
        if pending_action == "Issue Bounty":
            world.issue_political_warrant("bounty", target.id)
        elif pending_action == "Issue Arrest Warrant":
            world.issue_political_warrant("arrest_warrant", target.id)
        ctx["mode"] = "root"
        ctx["selected_target_index"] = 0
        ctx["scroll_offset"] = 0

def open_combat_menu(world):
    """Explicit visible target selection, reusing the existing action menu."""
    from simulation.systems.body_combat import supported, ranged_weapon
    fov = world.player_fov_map
    reach = max(10, ITEM_DEFINITIONS.get(str(world.player.equipment.weapon), {}).get("properties", {}).get("attack_range", 1))
    targets = [actor for actor in world.all_npcs if (supported(actor) or ranged_weapon(world.player)) and not actor.physical.is_dead
               and max(abs(actor.x-world.player.x), abs(actor.y-world.player.y)) <= reach
               and 0 <= actor.y < fov.shape[0] and 0 <= actor.x < fov.shape[1]
               and fov[actor.y, actor.x]]
    targets.sort(key=lambda actor: (not actor.combat.is_hostile_to_player,
                                    max(abs(actor.x-world.player.x), abs(actor.y-world.player.y))))
    if not targets:
        world.add_message_to_chat_log("No visible combat target nearby.")
        return
    remembered = getattr(world, "player_combat_target_id", None)
    index = next((i for i, actor in enumerate(targets) if actor.id == remembered), 0)
    target = targets[index]
    world.player.state.current_path = []
    world.interaction_context.update(active=True, combat_picker=True, x=target.x, y=target.y,
        target_entities=[dict(type="npc", data=actor, name=actor.name) for actor in targets],
        selected_entity_index=index, selected_action_index=0,
        available_actions=["Attack", "Punch", "Kick", "Examine Wounds"])


def advance_committed_action(world, ticks):
    """Spend time through the real world loop: opponents and bleeding act too."""
    for _ in range(max(0, int(ticks))):
        if world.player.physical.is_dead:
            break
        world.update()


def commit_player_attack(world, target, attack_type="attack"):
    result = world.player_attempt_attack(target, attack_type=attack_type)
    world.player_combat_target_id = target.id
    attempted = getattr(result, "attempted", result is None)
    if attempted:
        world.interaction_context["active"] = False
        world.player.state.current_path = []
        # Real-time already pays recovery as ticks pass. Paused combat spends
        # the same interval explicitly; a miss still gives the wolf its turn.
        if getattr(world, "is_paused", False):
            ready = world.player.combat.anatomy.attack_ready_tick
            advance_committed_action(world, max(1, ready-world.game_time))
    return attempted


def handle_interaction_input(event: tcod.event.KeyDown, world: World, context_handler) -> bool:
    """Handles input when the interaction menu is active. Returns True if action taken."""
    ctx = world.interaction_context
    if not ctx["available_actions"]:
        ctx["active"] = False
        world.add_message_to_chat_log("There is nothing here you can interact with.")
        return False

    if event.sym == tcod.event.KeySym.UP:
        ctx["selected_action_index"] = (ctx["selected_action_index"] - 1) % len(ctx["available_actions"])
    elif event.sym == tcod.event.KeySym.DOWN:
        ctx["selected_action_index"] = (ctx["selected_action_index"] + 1) % len(ctx["available_actions"])
    elif event.sym in (tcod.event.KeySym.LCTRL, tcod.event.KeySym.RCTRL, tcod.event.KeySym.TAB):
        ctx["selected_entity_index"] = (ctx["selected_entity_index"] + 1) % len(ctx["target_entities"])
        selected_entity = ctx["target_entities"][ctx["selected_entity_index"]]
        ctx["available_actions"] = (["Attack", "Punch", "Kick", "Examine Wounds"] if ctx.get("combat_picker")
                                    else world._get_actions_for_entity(selected_entity))
        if ctx.get("combat_picker"):
            ctx["x"], ctx["y"] = selected_entity["data"].x, selected_entity["data"].y
        ctx["selected_action_index"] = 0
    elif event.sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.E) or (event.sym == tcod.event.KeySym.F and ctx.get("combat_picker")):
        return execute_interaction(world, context_handler)
    elif event.sym == tcod.event.KeySym.ESCAPE:
        ctx["active"] = False
    return False

def open_interaction_menu(world: World, x: int, y: int):
    """Opens the interaction menu for a specific tile."""
    entities = world._get_interactables_at(x, y)
    if not entities:
        world.add_message_to_chat_log("There is nothing to interact with here.")
        return

    actionable_entities = _get_actionable_entities(world, entities)
    if not actionable_entities:
        world.add_message_to_chat_log("There is nothing here you can interact with.")
        return

    selected_entity, available_actions = actionable_entities[0]
    world.interaction_context["active"] = True
    world.interaction_context["combat_picker"] = False
    world.interaction_context["x"], world.interaction_context["y"] = x, y
    world.interaction_context["target_entities"] = [entity for entity, _ in actionable_entities]
    world.interaction_context["selected_entity_index"] = 0
    world.interaction_context["available_actions"] = available_actions
    world.interaction_context["selected_action_index"] = 0

def execute_interaction(world: World, context_handler) -> bool:
    """Executes the selected action from the interaction context. Returns True if turn taken."""
    ctx = world.interaction_context
    if not ctx["active"] or not ctx["available_actions"]:
        return False

    selected_entity = ctx["target_entities"][ctx["selected_entity_index"]]
    selected_action = ctx["available_actions"][ctx["selected_action_index"]]
    target_x, target_y = ctx["x"], ctx["y"]
    entity_data = selected_entity["data"]

    action_map = {
        "Chop": lambda: world.player_attempt_chop_tree(target_x, target_y),
        "Butcher": lambda: world.player_attempt_butcher(target_x, target_y),
        "Toggle Door": lambda: world.player_attempt_toggle_door(target_x, target_y),
        "Talk": lambda: start_social_menu(world, entity_data),
        "Attack": lambda: commit_player_attack(world, entity_data),
        "Punch": lambda: commit_player_attack(world, entity_data, "punch"),
        "Kick": lambda: commit_player_attack(world, entity_data, "kick"),
        "Examine Wounds": lambda: world.examine_body(entity_data),
        "Treat Wounds": lambda: world.treat_body(entity_data),
        "Feed": lambda: world.player_attempt_feed_animal(entity_data),
        "Ride": lambda: world.player_attempt_ride_animal(entity_data),
        "Till Soil": lambda: world.player_attempt_till_soil(target_x, target_y),
        "Plant Seeds": lambda: world.player_attempt_plant_seeds(target_x, target_y),
        "Dismount": lambda: world.player_attempt_dismount(entity_data),
        "Shear": lambda: world.player_attempt_shear(entity_data),
        "Fish": lambda: world.player_attempt_fish(target_x, target_y),
        "Pick Lock": lambda: world.player_attempt_pick_lock(target_x, target_y),
        "Plant Sapling": lambda: world.player_attempt_plant_sapling(target_x, target_y),
        "Harvest": lambda: world.player_attempt_harvest(target_x, target_y),
        "Trade": lambda: start_trade(world, entity_data),
        "Repair": lambda: world.player_attempt_repair_gear(entity_data),
        "Pick up": lambda: pick_up_item(world, entity_data, target_x, target_y),
        "Sit": lambda: world.player_attempt_sit(target_x, target_y),
        "Sleep": lambda: world.player_attempt_sleep(target_x, target_y),
        "Claim House": lambda: claim_house(world, entity_data),
        "Buy Property": lambda: world.buy_property(entity_data),
        "Company Ledger": lambda: world.open_company_ledger_menu(entity_data),
        "Govern": lambda: world.open_governance_menu(entity_data),
        "Post Job": lambda: world.open_job_posting_menu(entity_data),
        "Read Notices": lambda: world.open_noticeboard_menu(),

        "Examine": lambda: world.add_message_to_chat_log(world.inspect_tile(target_x, target_y)),
        "Cook": lambda: world.player_attempt_cook(target_x, target_y),
        "Smoke Meat": lambda: world.player_attempt_smoke(target_x, target_y),
        "Light Fire": lambda: world.player_attempt_light_fire(target_x, target_y),
        "Extinguish Fire": lambda: world.player_attempt_extinguish_fire(target_x, target_y),
        "Forge": lambda: world.player_attempt_forge(target_x, target_y),
        "Read": lambda: world.player_attempt_read_book(entity_data),
        "Offer Mercenary Services": lambda: world.player_attempt_mercenary_contract(entity_data),
        "Loot Chest": lambda: world.player_attempt_loot_chest(target_x, target_y)

    }

    result = action_map[selected_action]() if selected_action in action_map else None
    if selected_action in ("Attack", "Punch", "Kick") and result is False:
        return False
    if selected_action == "Treat Wounds" and result:
        advance_committed_action(world, 10)

    if selected_action in ["Talk", "Trade", "Read", "Offer Mercenary Services", "Repair", "Read Notices", "Company Ledger", "Govern", "Post Job"]:
        ctx["active"] = False

    apply_ui_requests(world, context_handler)

    if not world.chat_ui_active and not world.trade_ui_active:
        ctx["active"] = False

    # Return True for actions that consume time
    return selected_action not in ["Examine", "Examine Wounds", "Talk", "Trade", "Read", "Company Ledger", "Govern", "Post Job"]

def handle_help_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is in the 'HELP_MENU' state."""
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.QUESTION, tcod.event.KeySym.SLASH):
        world.game_state = "PLAYING"

def handle_info_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input for the info menu."""
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.I):
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.B:
        world.examine_body()
    elif hasattr(tcod.event.KeySym, 'u') and event.sym == tcod.event.KeySym.u:
        world.game_state = "INVENTORY_MENU"
    elif hasattr(tcod.event.KeySym, 'U') and event.sym == tcod.event.KeySym.U:
        world.game_state = "INVENTORY_MENU"

def handle_body_menu_input(event: tcod.event.KeyDown, world: World):
    if event.sym == tcod.event.KeySym.ESCAPE:
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.DOWN:
        world.body_menu_scroll = min(getattr(world, "body_menu_max_scroll", 0), getattr(world, "body_menu_scroll", 0)+1)
    elif event.sym == tcod.event.KeySym.UP:
        world.body_menu_scroll = max(0, getattr(world, "body_menu_scroll", 0)-1)
    elif event.sym == tcod.event.KeySym.T:
        target = world.get_entity_by_id(getattr(world, "body_menu_target_id", world.player.id))
        if target and world.treat_body(target):
            advance_committed_action(world, 10)


def handle_inventory_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input for the dedicated inventory menu.

    The menu used to only scroll: there was no way to eat, drink, equip or light
    anything from it, and World.use_item - which does all of that - had no caller
    anywhere in the game. A player could carry food and still starve.
    """
    context = world.interaction_context
    context.setdefault("inventory_scroll_offset", 0)
    context.setdefault("inventory_selected_index", 0)
    # Populated by draw_inventory_menu, which is the thing that knows which
    # display rows are items rather than headers or spacers.
    selectable = context.get("inventory_selectable") or []

    if event.sym == tcod.event.KeySym.ESCAPE or (hasattr(tcod.event.KeySym, 'u') and event.sym == tcod.event.KeySym.u) or (hasattr(tcod.event.KeySym, 'U') and event.sym == tcod.event.KeySym.U):
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.UP:
        if selectable:
            context["inventory_selected_index"] = (context["inventory_selected_index"] - 1) % len(selectable)
        context["inventory_scroll_offset"] = max(0, context["inventory_scroll_offset"] - 1)
    elif event.sym == tcod.event.KeySym.DOWN:
        if selectable:
            context["inventory_selected_index"] = (context["inventory_selected_index"] + 1) % len(selectable)
        context["inventory_scroll_offset"] += 1
    elif event.sym in (getattr(tcod.event.KeySym, "s", ord("s")), getattr(tcod.event.KeySym, "S", ord("S")),
                       getattr(tcod.event.KeySym, "t", ord("t")), getattr(tcod.event.KeySym, "T", ord("T"))):
        from simulation.systems.appearance import groom

        shave = event.sym in (getattr(tcod.event.KeySym, "s", ord("s")), getattr(tcod.event.KeySym, "S", ord("S")))
        _, message = groom(world.player, world, "none" if shave else "short_beard")
        world.add_message_to_chat_log(message)
    elif event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, "KP_ENTER", tcod.event.KeySym.RETURN)):
        if not selectable:
            world.add_message_to_chat_log("You are carrying nothing to use.")
            return
        index = max(0, min(context["inventory_selected_index"], len(selectable) - 1))
        key = selectable[index]
        used = world.use_item(key)
        if used and key in ("bandage", "splint", "healing_salve"):
            advance_committed_action(world, 10)

def handle_book_reading_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is reading a book."""
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.RETURN):
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.UP:
        world.book_reading_context["scroll_offset"] = max(0, world.book_reading_context["scroll_offset"] - 1)
    elif event.sym == tcod.event.KeySym.DOWN:
        world.book_reading_context["scroll_offset"] += 1

def handle_trade_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is in the trade menu."""
    if event.sym == tcod.event.KeySym.ESCAPE:
        world.request_close_trade()
        apply_ui_requests(world)
    elif event.sym == tcod.event.KeySym.TAB:
        world.trade_ui_player_selling = not world.trade_ui_player_selling
    elif event.sym == tcod.event.KeySym.UP:
        if world.trade_ui_player_selling and world.trade_ui_player_inventory_snapshot:
            world.trade_ui_player_item_index = (world.trade_ui_player_item_index - 1) % len(world.trade_ui_player_inventory_snapshot)
        elif not world.trade_ui_player_selling and world.trade_ui_merchant_inventory_snapshot:
            world.trade_ui_merchant_item_index = (world.trade_ui_merchant_item_index - 1) % len(world.trade_ui_merchant_inventory_snapshot)
    elif event.sym == tcod.event.KeySym.DOWN:
        if world.trade_ui_player_selling and world.trade_ui_player_inventory_snapshot:
            world.trade_ui_player_item_index = (world.trade_ui_player_item_index + 1) % len(world.trade_ui_player_inventory_snapshot)
        elif not world.trade_ui_player_selling and world.trade_ui_merchant_inventory_snapshot:
            world.trade_ui_merchant_item_index = (world.trade_ui_merchant_item_index + 1) % len(world.trade_ui_merchant_inventory_snapshot)
    elif event.sym == tcod.event.KeySym.RETURN:
        world.handle_trade_action()

def handle_social_menu_input(event: tcod.event.KeyDown, world: World):
    """Handle input for the player social interaction menu."""
    ctx = world.social_menu_context
    mode = ctx.get("mode", "root")
    npc = world.get_social_menu_target()
    if npc is None:
        world.close_social_menu()
        return

    if event.sym == tcod.event.KeySym.ESCAPE:
        if mode == "root":
            world.close_social_menu()
        else:
            ctx["mode"] = "root"
            ctx["selected_option_index"] = 0
            ctx["scroll_offset"] = 0
        return

    if mode == "root":
        actions = world.get_social_menu_actions()
        if event.sym == tcod.event.KeySym.UP:
            ctx["selected_action_index"] = (ctx.get("selected_action_index", 0) - 1) % len(actions)
        elif event.sym == tcod.event.KeySym.DOWN:
            ctx["selected_action_index"] = (ctx.get("selected_action_index", 0) + 1) % len(actions)
        elif event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912)):
            selected_action = actions[ctx.get("selected_action_index", 0)]
            if selected_action == "Propose":
                world.player_propose_to_npc(npc)
                if world.player.social.family_ties.get("partner_id") == npc.id:
                    world.close_social_menu()
            else:
                ctx["mode"] = "gift" if selected_action == "Give Gift" else "gossip"
                ctx["selected_option_index"] = 0
                ctx["scroll_offset"] = 0
        return

    options = world.get_social_gift_options() if mode == "gift" else world.get_player_gossip_options()
    if not options:
        if event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912)):
            world.add_message_to_chat_log("There is nothing available for that action.")
        return

    if event.sym == tcod.event.KeySym.UP:
        ctx["selected_option_index"] = (ctx.get("selected_option_index", 0) - 1) % len(options)
    elif event.sym == tcod.event.KeySym.DOWN:
        ctx["selected_option_index"] = (ctx.get("selected_option_index", 0) + 1) % len(options)
    elif event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912)):
        selected_index = max(0, min(len(options) - 1, ctx.get("selected_option_index", 0)))
        selected_option = options[selected_index]
        if mode == "gift":
            world.give_gift_to_npc(npc, selected_option)
        else:
            world.share_player_memory_with_npc(npc, selected_option)
        ctx["selected_option_index"] = 0
        ctx["scroll_offset"] = 0

def handle_quest_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is in the 'QUEST_MENU' state."""
    ctx = world.quest_menu_context
    num_quests = len(world.player.knowledge.active_quests)
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.Q):
        world.game_state = "PLAYING"
    elif num_quests == 0:
        ctx["selected_quest_index"] = 0
    elif event.sym == tcod.event.KeySym.UP:
        ctx["selected_quest_index"] = max(0, ctx.get("selected_quest_index", 0) - 1)
    elif event.sym == tcod.event.KeySym.DOWN:
        ctx["selected_quest_index"] = min(num_quests - 1, ctx.get("selected_quest_index", 0) + 1)

def handle_dialogue_input(event: tcod.event.KeyDown, world: World, context_handler):
    """Handles input when the player is in the 'DIALOGUE' state."""
    if event.sym == tcod.event.KeySym.ESCAPE:
        world.request_close_dialogue()
        apply_ui_requests(world, context_handler)
    elif event.sym in (tcod.event.KeySym.RETURN, getattr(tcod.event.KeySym, 'KP_ENTER', 1073741912)):
        if getattr(world, 'chat_ui_input_line', '').strip():
            world.dialogue_scroll = 0
            world.chat_ui_history.append(("Player", world.chat_ui_input_line))
            world.continue_npc_dialogue(world.chat_ui_target_npc, world.chat_ui_input_line)
            world.chat_ui_input_line = "" # Clear input line
            apply_ui_requests(world, context_handler)
    elif event.sym == tcod.event.KeySym.BACKSPACE:
        if getattr(world, 'chat_ui_input_line', ''):
            world.chat_ui_input_line = world.chat_ui_input_line[:-1]
    elif event.sym == tcod.event.KeySym.SPACE:
        world.chat_ui_input_line += " "
    else:
        # Fallback character typing if TextInput event lacks SDL bindings
        if 33 <= event.sym <= 126:
            char = chr(event.sym)
            try:
                mod = getattr(event, 'mod', 0)
                # KMOD_LSHIFT is 1, KMOD_RSHIFT is 2. Fallbacks for either.
                shifted = bool(mod & 3)
            except (TypeError, AttributeError):
                shifted = False
            
            if shifted:
                if char.islower(): char = char.upper()
                elif char == '1': char = '!'
                elif char == '2': char = '@'
                elif char == '3': char = '#'
                elif char == '4': char = '$'
                elif char == '5': char = '%'
                elif char == '6': char = '^'
                elif char == '7': char = '&'
                elif char == '8': char = '*'
                elif char == '9': char = '('
                elif char == '0': char = ')'
                elif char == '-': char = '_'
                elif char == '=': char = '+'
                elif char == '[': char = '{'
                elif char == ']': char = '}'
                elif char == ';': char = ':'
                elif char == "'": char = '"'
                elif char == ',': char = '<'
                elif char == '.': char = '>'
                elif char == '/': char = '?'
            
            world.chat_ui_input_line += char

def start_dialogue(world, npc, context_handler):
    """Starts a dialogue with an NPC."""
    world.start_npc_dialogue(npc)
    world.request_open_dialogue(npc)
    apply_ui_requests(world, context_handler)

def start_social_menu(world, npc):
    """Open the social interaction menu for an NPC."""
    world.open_social_menu(npc)

def start_trade(world, npc):
    """Starts a trade session with an NPC."""
    if npc.economic.profession in TRADE_CAPABLE_PROFESSIONS:
        world.request_open_trade(npc)
        apply_ui_requests(world)
    else:
        world.add_message_to_chat_log("This person has nothing to trade.")

def pick_up_item(world, item_data, x, y):
    """Picks up an item from the map."""
    item_key, quantity = item_data["item_key"], item_data["quantity"]
    item_reference = item_data.get("item_reference")
    if item_reference is not None:
        picked_item = world.pop_item_reference_from_map(item_key, x, y)
        if picked_item is not None:
            world.player.add_item_reference(picked_item)
            item_name = getattr(picked_item, "name", ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key))
            world.add_message_to_chat_log(f"You pick up 1x {item_name}.")
            return
    if world.remove_item_from_map(item_key, quantity, x, y):
        world.player.add_item(item_key, quantity)
        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
        world.add_message_to_chat_log(f"You pick up {quantity}x {item_name}.")

def claim_house(world, building):
    """Claims a house for the player."""
    if building.building_type == "house" and not building.player_owned and not building.residents:
        building.player_owned = True
        if hasattr(building, "owner_id"):
            building.owner_id = world.player.id
        world.add_message_to_chat_log(f"You have claimed this {building.building_type} as your own!")
    else:
        world.add_message_to_chat_log("You cannot claim this structure.")

def main():
    """Sets up the game and runs the main loop."""
    parser = argparse.ArgumentParser(description="This is Life - A Roguelike Simulation")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode.")
    parser.add_argument("--ticks", type=int, help="Number of ticks to run in headless mode.")
    args = parser.parse_args()

    if args.headless:
        if not TCOD_AVAILABLE:
            print(
                "Warning: tcod is not installed, so this headless run uses the\n"
                "         compatibility shim. Its noise stub returns a constant,\n"
                "         which produces flat, featureless terrain. Install tcod\n"
                "         (pip install tcod) for a representative simulation."
            )
        world = World()
        run_headless(world, args.ticks)
        return

    if not require_render_backend():
        return 1

    tileset = load_custom_tileset()
    if not tileset:
        return 1

    console = create_console()

    # Main Menu State
    main_menu_loop(console, tileset)


def require_render_backend() -> bool:
    """Verify a real tcod is present before we try to open a window.

    Without it, tcod_compat substitutes a shim whose Console discards every
    draw call and whose event queue is permanently empty. The game does not
    fail in any obvious way: it runs, shows nothing, and spins at full speed
    forever. Previously the only clue was a stray warning from the tileset
    loader ("'object' object has no attribute 'set_tile'"), which reads like
    a cosmetic problem with the sprite sheet rather than "there is no
    renderer". Say so plainly and stop.
    """
    if TCOD_AVAILABLE:
        return True
    print(
        "Error: tcod is not installed, so there is no renderer available.\n"
        "\n"
        "  This is a required dependency for playing the game - without it\n"
        "  the window cannot be created and nothing would be drawn.\n"
        "\n"
        "  Install it with:\n"
        "      pip install tcod\n"
        "\n"
        "  (Simulation-only runs still work without it: use --headless.)",
        file=sys.stderr,
    )
    return False

def create_console():
    """Build the root console the whole renderer draws into.

    The `order` argument matters more than it looks. On a tcod Console it
    selects the *indexing convention* of the `fg`/`bg` buffers: "C" exposes
    them as (height, width, 3) indexed [y, x], while "F" exposes them as
    (width, height, 3) indexed [x, y].

    Every buffer access in rendering/console_renderer.py is written [y, x]
    (entity background sampling, the focus badge, the lighting pass), so
    this must stay "C". It was previously "F", which silently made
    `console.bg[y, x]` mean `console.bg[x, y]`: reads in screen columns
    past the console's height landed out of bounds and crashed the game as
    soon as anything was drawn in the right-hand third of the map.

    Note this is NOT the same flag as numpy's `order` in engine.py's
    `np.full((WORLD_HEIGHT, WORLD_WIDTH), order="F")` - there it only picks
    a memory layout and the array is still shaped (H, W) and indexed [y, x].
    """
    return tcod.console.Console(SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, order="C")


def load_custom_tileset():
    """Loads the base ASCII font and appends DawnLike tiles mapped to Unicode PUA."""
    # Base font: DawnLike SDS_8x8 pixel font (same artist + CC-BY-SA 3.0 license
    # as the DawnLike tiles already in the game), rendered at 16x16 per tile to
    # preserve the existing console geometry and the 2-4x zoomed-sprite pipeline.
    # SDS_8x8 is ASCII-only, so the Unicode box-drawing/arrow/block glyphs the UI
    # relies on are backfilled from the bundled dejavu tilesheet below. If the
    # TTF is missing entirely, fall back to the dejavu tilesheet for everything.
    tileset = None
    try:
        tileset = tcod.tileset.load_truetype_font("SDS_8x8.ttf", 16, 16)
    except Exception:
        tileset = None
    if tileset is None:
        try:
            tileset = tcod.tileset.load_tilesheet("dejavu16x16_gs_tc.png", 32, 8, tcod.tileset.CHARMAP_TCOD)
        except FileNotFoundError:
            print("Error: Font file not found: 'dejavu16x16_gs_tc.png'")
            return None
    else:
        _backfill_ui_glyphs(tileset)

    from rendering.ui_glyphs import register_ui_glyphs
    register_ui_glyphs(tileset)

    # Load combined DawnLike tiles
    try:
        from PIL import Image
        from runtime_compat import np
        img = Image.open(TILESET_PATH).convert("RGBA")
        arr = np.array(img)

        # Split into 16x16 tiles and map them starting at 0xE000
        tile_width = 16
        tile_height = 16
        img_width, img_height = img.size

        cols = img_width // tile_width
        rows = img_height // tile_height

        base_code = 0xE000
        for r in range(rows):
            for c in range(cols):
                tile_arr = arr[r * tile_height:(r + 1) * tile_height, c * tile_width:(c + 1) * tile_width, :]
                tileset[base_code + (r * cols) + c] = tile_arr
        register_zoomed_dawnlike_tiles(tileset, TILESET_PATH)
        from rendering.terrain_art import register_terrain_tiles
        register_terrain_tiles(tileset)
        from rendering import pixel_scene, village_art, people_art, interior_art
        pixel_scene.install(tileset)
        village_art.install()
        people_art.install()
        interior_art.install()

    except Exception as e:
        print(f"Warning: Could not load DawnLike tileset: {e}")

    return tileset


def _backfill_ui_glyphs(tileset):
    """Copy the non-ASCII UI glyphs into an SDS_8x8 base tileset.

    SDS_8x8.ttf covers only ASCII (plus a few typographic quotes), so the box
    drawing, arrows, block, shade, and bullet glyphs that the UI panels rely on
    would otherwise render blank. This copies those specific tiles from the
    bundled dejavu tilesheet (already shipped with the project) into the pixel
    font's tileset so the UI stays intact while ASCII text stays pixel-styled.
    """
    ui_codepoints = (
        0x2500,  # ─ single horizontal (RULE)
        0x2502,  # │ single vertical (console_renderer)
        0x2550,  # ═ double horizontal
        0x2551,  # ║ double vertical
        0x2554,  # ╔ double top-left
        0x2557,  # ╗ double top-right
        0x255A,  # ╚ double bottom-left
        0x255D,  # ╝ double bottom-right
        0x2588,  # █ full block (BAR_CELL / SCROLL_THUMB)
        0x2591,  # ░ light shade (SCROLL_TRACK)
        0x25B2,  # ▲ arrow up
        0x25BC,  # ▼ arrow down
        0x2022,  # • bullet
    )
    try:
        dejavu = tcod.tileset.load_tilesheet("dejavu16x16_gs_tc.png", 32, 8, tcod.tileset.CHARMAP_TCOD)
    except Exception:
        return  # No fallback available; ASCII-only font stays as-is.
    for cp in ui_codepoints:
        try:
            tile = dejavu.get_tile(cp)
            if tile is not None:
                tileset[cp] = tile
        except Exception:
            continue


MENU_TAGLINE = "A life simulated, one tick at a time."


def _draw_menu_backdrop(console):
    """Wash the empty screen with a faint vignette.

    Flat black behind a title reads as "nothing loaded yet"; a gradient
    reads as a deliberate screen. This only touches the background buffer,
    so it costs nothing in glyphs and sits behind everything drawn after.
    """
    if not hasattr(console, "bg"):
        return
    height = min(console.height, console.bg.shape[0])
    width = min(console.width, console.bg.shape[1])
    for y in range(height):
        # Darkest at the top, lifting slightly toward the bottom.
        depth = y / max(1, height - 1)
        row_color = (
            int(13 + 9 * depth),
            int(21 + 13 * depth),
            int(22 + 7 * depth),
        )
        for x in range(width):
            console.bg[y, x] = row_color


def draw_main_menu(console, options, selected_index):
    """Draw the title screen: backdrop, block-letter title, framed options."""
    _draw_menu_backdrop(console)

    center_x = console.width // 2
    title_y = max(2, console.height // 4 - title_art.GLYPH_HEIGHT // 2 - 3)
    title_art.draw(
        console, center_x, title_y, "THIS IS LIFE",
        fg=theme.HEADING, shadow_fg=(60, 42, 16),
    )

    tagline_y = title_y + title_art.GLYPH_HEIGHT + 2
    console.print(center_x, tagline_y, MENU_TAGLINE, alignment=libtcodpy.CENTER, fg=theme.TEXT_MUTED)

    panel_width = 36
    panel_height = len(options) * 2 + 3
    panel_x = center_x - (panel_width // 2)
    panel_y = tagline_y + 3
    widgets.panel(console, panel_x, panel_y, panel_width, panel_height, focused=True)

    for index, option in enumerate(options):
        selected = index == selected_index
        color = theme.SELECTION if selected else theme.TEXT_DIM
        row_y = panel_y + 2 + index * 2
        if selected:
            console.print(panel_x + 2, row_y, " " * (panel_width-4), bg=theme.SELECTION_BG)
            console.print(panel_x + 3, row_y, theme.SELECT_CURSOR, fg=color)
        console.print(center_x, row_y, option, alignment=libtcodpy.CENTER, fg=color)

    from rendering.menu_scene import draw_village_vignette
    draw_village_vignette(console)
    console.print(
        center_x, console.height - 3,
        "Click to choose    Up/Down + Enter    Esc to exit",
        alignment=libtcodpy.CENTER, fg=theme.TEXT_MUTED,
    )


def main_menu_loop(console, tileset):
    """Displays the main menu and handles selection."""
    with tcod.context.new(
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        columns=console.width,
        rows=console.height,
        tileset=tileset,
        title="This is Life",
        vsync=True,
    ) as context:
        selected_index = 0
        options = ["New Game", "Load Game", "Exit"]

        while True:
            console.clear()
            draw_main_menu(console, options, selected_index)
            context.present(console)

            for event in tcod.event.wait():
                event = context.convert_event(event)
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                if isinstance(event, (tcod.event.MouseMotion, tcod.event.MouseButtonDown)):
                    center = console.width//2
                    title_y = max(2,console.height//4-title_art.GLYPH_HEIGHT//2-3)
                    first_row = title_y + title_art.GLYPH_HEIGHT + 7
                    mx,my = event.position
                    row = int(my-first_row)//2
                    if center-16 <= mx < center+16 and first_row <= my < first_row+len(options)*2:
                        selected_index = max(0,min(len(options)-1,row))
                        if isinstance(event,tcod.event.MouseButtonDown) and event.button == tcod.event.MouseButton.LEFT:
                            event = tcod.event.KeyDown(scancode=0,sym=tcod.event.KeySym.RETURN,mod=0)
                if isinstance(event, tcod.event.KeyDown) and event.sym == tcod.event.KeySym.ESCAPE:
                    raise SystemExit()
                if isinstance(event, tcod.event.KeyDown):
                    if event.sym == tcod.event.KeySym.UP:
                        selected_index = (selected_index - 1) % len(options)
                    elif event.sym == tcod.event.KeySym.DOWN:
                        selected_index = (selected_index + 1) % len(options)
                    elif event.sym == tcod.event.KeySym.RETURN:
                        if options[selected_index] == "New Game":
                            player_first_name = prompt_for_new_player_name(console, context)
                            if player_first_name is not None:
                                start_game(context, console, None, player_first_name=player_first_name)
                        elif options[selected_index] == "Load Game":
                            loaded_world = load_game_menu(console, context)
                            if loaded_world:
                                start_game(context, console, loaded_world)
                        elif options[selected_index] == "Exit":
                            raise SystemExit()

def _describe_save(filename):
    """Two display lines for a save: who and when, plus where and how long ago.

    Falls back to the bare filename for saves written before summaries
    existed, so an old save is still listed and loadable.
    """
    metadata = load_save_metadata(filename)
    if not metadata:
        return filename, "no summary available"

    name = metadata.get("player_name") or "Unknown"
    clock = console_renderer._format_world_clock(metadata.get("game_time", 0))
    season = metadata.get("season") or ""
    weather = str(metadata.get("weather") or "").replace("_", " ").title()

    saved_at = metadata.get("saved_at")
    when = ""
    if saved_at:
        when = time.strftime("saved %Y-%m-%d %H:%M", time.localtime(saved_at))

    detail = "  ".join(part for part in (clock, f"{season} / {weather}".strip(" /"), when) if part)
    return name, detail


def draw_load_menu(console, saves, selected_index):
    """Draw the save list as cards showing character, day and save time."""
    _draw_menu_backdrop(console)
    center_x = console.width // 2

    console.print(center_x, 4, "LOAD GAME", alignment=libtcodpy.CENTER, fg=theme.HEADING)

    panel_width = 56
    panel_height = min(console.height - 12, len(saves) * 3 + 3)
    panel_x = center_x - (panel_width // 2)
    panel_y = 7
    widgets.panel(console, panel_x, panel_y, panel_width, panel_height, focused=True)

    visible_rows = max(1, (panel_height - 3) // 3)
    scroll = widgets.clamp_scroll(selected_index, 0, visible_rows)
    for row in range(visible_rows):
        index = scroll + row
        if index >= len(saves):
            break
        selected = index == selected_index
        title, detail = _describe_save(saves[index])
        row_y = panel_y + 2 + row * 3
        color = theme.SELECTION if selected else theme.TEXT
        if selected:
            console.print(panel_x + 2, row_y, theme.SELECT_CURSOR, fg=color)
        console.print(panel_x + 4, row_y, title[: panel_width - 6], fg=color)
        console.print(panel_x + 4, row_y + 1, detail[: panel_width - 6], fg=theme.TEXT_MUTED)

    console.print(
        center_x, console.height - 4,
        "Up/Down to choose    Enter to load    Esc to cancel",
        alignment=libtcodpy.CENTER, fg=theme.TEXT_MUTED,
    )


def load_game_menu(console, context):
    """Displays available save files."""
    if not os.path.exists("saves"):
        return None

    saves = [f for f in os.listdir("saves") if f.endswith(".sav")]
    if not saves:
        return None

    selected_index = 0
    while True:
        console.clear()
        draw_load_menu(console, saves, selected_index)
        context.present(console)

        for event in tcod.event.wait():
            context.convert_event(event)
            if isinstance(event, tcod.event.KeyDown):
                if event.sym == tcod.event.KeySym.UP:
                    selected_index = (selected_index - 1) % len(saves)
                elif event.sym == tcod.event.KeySym.DOWN:
                    selected_index = (selected_index + 1) % len(saves)
                elif event.sym == tcod.event.KeySym.RETURN:
                    return load_game(saves[selected_index])
                elif event.sym == tcod.event.KeySym.ESCAPE:
                    return None

def start_game(context, console, world_state=None, player_first_name: str | None = None):
    """Starts the actual gameplay loop."""
    if world_state:
        world = world_state
        # Check if the player in the loaded world is dead
        if world.player.combat.hp <= 0: # Assuming HP <= 0 means dead
            console.clear()
            console.print(console.width // 2, console.height // 2, "Previous character is dead.", alignment=libtcodpy.CENTER)
            console.print(console.width // 2, console.height // 2 + 2, "Starting as a new character in this world...", alignment=libtcodpy.CENTER)
            context.present(console)
            tcod.event.wait(1.0) # Pause briefly

            # Create a new player
            from engine import Player
            # Find a safe starting spot (e.g., a random village or the original start logic)
            # Re-using _find_starting_position logic on the existing world
            world.player = Player(0, 0) # Temp coords
            world._find_starting_position() # Re-calculate safe start
            world.player.world_ref = world # Re-link world reference
            world.game_state = "PLAYING" # Reset state

        world.ensure_player_surroundings_generated() # Ensure visuals are ready after load
    else:
        # Show loading message
        console.clear()
        console.print(console.width // 2, console.height // 2, "Generating World...", alignment=libtcodpy.CENTER)
        context.present(console)
        world = World(player_first_name=normalize_player_first_name(player_first_name))
        # Pre-simulate the world so NPCs spread to their daily routines
        world._pre_simulate_world()

    _ensure_zoom_state(world)

    last_time = time.perf_counter()
    tick_accumulator = 0.0
    MAX_ACCUMULATOR_TICKS = 5

    # Menu fade-in: tracks how long the current game_state has been active
    # so draw() can ramp a just-opened menu in from the world view over a
    # few frames instead of popping in at full opacity. MENU_FADE_DURATION
    # is in seconds, not frames, so the ramp feels consistent regardless of
    # framerate.
    MENU_FADE_DURATION = 0.18
    menu_fade_state = world.game_state
    menu_fade_start_time = last_time

    while True:
        # Calculate Delta Time
        current_time = time.perf_counter()
        dt = current_time - last_time
        last_time = current_time

        # Update Animations
        world.update_animations(dt)

        if world.game_state == "PLAYER_DEAD":
            render_game_over(console, context, world)
            break # Break to return to main menu

        if world.game_state != menu_fade_state:
            menu_fade_state = world.game_state
            menu_fade_start_time = current_time
        menu_fade_ratio = min(1.0, (current_time - menu_fade_start_time) / MENU_FADE_DURATION)

        camera_x, camera_y = _get_camera_origin(world)
        draw(console, world, camera_x, camera_y, menu_fade_ratio=menu_fade_ratio)
        context.present(console)

        # Handle Input
        player_acted = handle_events(world, context)

        # Advance real-time world simulation when active
        if (world.game_state == "PLAYING" and not getattr(world, "is_paused", False)
                and not world.interaction_context.get("active")):
            speed = getattr(world, "simulation_speed", 1.0)
            if speed > 0:
                tick_accumulator += dt * speed
                # Clamp accumulator to prevent catch-up lag
                tick_accumulator = min(tick_accumulator, SECONDS_PER_GAME_TICK * MAX_ACCUMULATOR_TICKS)

                while tick_accumulator >= SECONDS_PER_GAME_TICK:
                    world.update()
                    apply_ui_requests(world, context)
                    tick_accumulator -= SECONDS_PER_GAME_TICK
        else:
            tick_accumulator = 0.0

        if world.needs_text_input:
            if hasattr(context, "start_text_input"):
                context.start_text_input()
            world.needs_text_input = False

def run_headless(world, num_ticks):
    """Runs the game for a fixed number of ticks in headless mode."""
    print(f"Running in headless mode for {num_ticks} ticks...")
    for i in range(num_ticks):
        world.update()
        apply_ui_requests(world)
        if i % 1000 == 0:
            print(f"  ...tick {i}/{num_ticks}")
    print("Headless mode run complete.")

def draw_game_over(console, world=None):
    """Draw the death screen, including a short epitaph when we have a world.

    The old screen was the words "GAME OVER" in a box. A run that ended is
    worth a line about whose run it was and how far it got.
    """
    _draw_menu_backdrop(console)
    center_x = console.width // 2

    title_y = max(2, console.height // 3 - title_art.GLYPH_HEIGHT)
    title_art.draw(console, center_x, title_y, "LIFE", fg=theme.DANGER, shadow_fg=(48, 16, 16))

    y = title_y + title_art.GLYPH_HEIGHT + 2
    console.print(center_x, y, "has ended.", alignment=libtcodpy.CENTER, fg=theme.TEXT_DIM)

    if world is not None:
        player = getattr(world, "player", None)
        name = str(getattr(player, "name", "") or "Unknown")
        clock = console_renderer._format_world_clock(getattr(world, "game_time", 0))
        console.print(center_x, y + 2, name, alignment=libtcodpy.CENTER, fg=theme.HEADING)
        console.print(center_x, y + 3, clock, alignment=libtcodpy.CENTER, fg=theme.TEXT_MUTED)

    console.print(
        center_x, console.height - 4, "Press any key to return to the menu",
        alignment=libtcodpy.CENTER, fg=theme.TEXT_MUTED,
    )


def render_game_over(console, context, world=None):
    """Renders the game over screen."""
    console.clear()
    draw_game_over(console, world)
    context.present(console)
    # Simple wait loop for game over
    while True:
        for event in tcod.event.wait():
            context.convert_event(event)
            if isinstance(event, (tcod.event.Quit, tcod.event.KeyDown)):
                return

def handle_events(world, context) -> bool:
    """Handles all player input and game events. Returns True if a turn was taken."""
    turn_taken = False
    for event in tcod.event.get():
        converted = context.convert_event(event)
        if converted is not None:
            event = converted
        if isinstance(event, tcod.event.Quit):
            raise SystemExit()
        if isinstance(event, (tcod.event.MouseMotion, tcod.event.MouseButtonDown)):
            world.mouse_x, world.mouse_y = int(event.position[0]), int(event.position[1])
        if isinstance(event, tcod.event.MouseWheel) and handle_mouse_wheel(world, event):
            continue
        if isinstance(event, tcod.event.MouseWheel) and world.game_state == "PLAYING":
            _ensure_zoom_state(world)
            wheel_delta = getattr(event, "y", 0)
            if wheel_delta > 0 and world.zoom_index < len(world.zoom_levels) - 1:
                world.zoom_index += 1
            elif wheel_delta < 0 and world.zoom_index > 0:
                world.zoom_index -= 1
        if isinstance(event, tcod.event.MouseButtonDown):
            if world.game_state == "PLAYING" and not world.interaction_context.get("active") and world.mouse_y < 3:
                from rendering.hud import toolbar_action_at
                action = toolbar_action_at(world, world.mouse_x, world.mouse_y)
                if action and event.button == tcod.event.MouseButton.LEFT:
                    handle_playing_input(SimpleNamespace(sym=getattr(tcod.event.KeySym, action)), world, context)
                continue
            # A click inside an open menu belongs to that menu. Anything
            # else falls through to the world view underneath.
            if handle_menu_mouse_click(event, world, context):
                turn_taken = True
            elif world.game_state == "PLAYING" and _is_inside_map_view(world):
                camera_x, camera_y = _get_camera_origin(world)
                mouse_world_x, mouse_world_y = _screen_to_world_position(world, camera_x, camera_y, world.mouse_x, world.mouse_y)

                if event.button == tcod.event.MouseButton.RIGHT:
                    from rendering.people_art import hit_test
                    hit = hit_test(world,camera_x,camera_y,world.mouse_x,world.mouse_y)
                    if hit is not None:
                        mouse_world_x,mouse_world_y = hit.x,hit.y
                    else:
                        from rendering.interior_art import hit_test as furniture_hit_test
                        furniture = furniture_hit_test(
                            world, camera_x, camera_y, world.mouse_x, world.mouse_y
                        )
                        if furniture is not None:
                            mouse_world_x, mouse_world_y = furniture
                        else:
                            from rendering.building_frontage import hit_test as sign_hit_test
                            sign = sign_hit_test(
                                world, camera_x, camera_y, world.mouse_x, world.mouse_y
                            )
                            if sign is not None:
                                mouse_world_x, mouse_world_y = sign
                    world.player.state.current_path = [] # Stop moving if interaction menu opens
                    world.add_message_to_chat_log(world.inspect_tile(mouse_world_x, mouse_world_y))
                    open_interaction_menu(world, mouse_world_x, mouse_world_y)
                elif event.button == tcod.event.MouseButton.LEFT:
                    # Calculate path for left click movement
                    path = world.calculate_path(world.player.x, world.player.y, mouse_world_x, mouse_world_y)
                    if path:
                        # The path includes start position, so pop it if it's where we are
                        if path and path[0] == (world.player.x, world.player.y):
                            path.pop(0)
                        world.player.state.current_path = path

        if isinstance(event, tcod.event.TextInput) and world.chat_ui_active:
            world.chat_ui_input_line += event.text
        elif isinstance(event, tcod.event.KeyDown):
            # Stop auto-movement on manual input
            if event.sym in [tcod.event.KeySym.UP, tcod.event.KeySym.DOWN, tcod.event.KeySym.LEFT, tcod.event.KeySym.RIGHT]:
                world.player.state.current_path = []

            if world.game_state == "DIALOGUE":
                handle_dialogue_input(event, world, context)
            elif world.game_state == "BOOK_READING":
                handle_book_reading_input(event, world)
            elif world.game_state == "TRADE_MENU":
                handle_trade_menu_input(event, world)
            elif world.game_state == "SOCIAL_MENU":
                handle_social_menu_input(event, world)
            elif world.game_state == "GOVERNANCE_MENU":
                handle_governance_menu_input(event, world)
            elif world.game_state == "QUEST_MENU":
                handle_quest_menu_input(event, world)
            elif world.game_state == "NOTICEBOARD_MENU":
                handle_noticeboard_menu_input(event, world)
            elif world.game_state == "COMPANY_LEDGER_MENU":
                handle_company_ledger_menu_input(event, world)
            elif world.game_state == "HELP_MENU":
                handle_help_menu_input(event, world)
            elif world.game_state == "INFO_MENU":
                handle_info_menu_input(event, world)
            elif world.game_state == "BODY_MENU":
                handle_body_menu_input(event, world)
            elif world.game_state == "INVENTORY_MENU":
                handle_inventory_menu_input(event, world)
            elif world.interaction_context["active"]:
                if handle_interaction_input(event, world, context): turn_taken = True
            elif world.game_state == "CRAFTING_MENU":
                handle_crafting_input(event, world)
            elif world.game_state == "BUILDING_MENU":
                handle_building_input(event, world)
            elif world.game_state == "LOOK_MODE":
                handle_look_mode_input(event, world)
            elif world.game_state == "PLAYING":
                if handle_playing_input(event, world, context): turn_taken = True

    apply_ui_requests(world, context)
    return turn_taken


def handle_mouse_wheel(world, event):
    """Route wheel input to the surface under the pointer before map zoom."""
    delta = int(getattr(event, "y", 0))
    if not delta:
        return False
    mx, my = getattr(world,"mouse_x",-1), getattr(world,"mouse_y",-1)
    if mx >= MAP_WIDTH:
        world.field_guide_scroll = max(0, min(getattr(world,"field_guide_max_scroll",0),
                                            getattr(world,"field_guide_scroll",0)-delta*3))
        return True
    if world.game_state == "PLAYING" and my >= MAP_HEIGHT:
        _scroll_message_log(world, delta*3)
        return True
    if world.game_state == "INVENTORY_MENU":
        count = len(world.interaction_context.get("inventory_selectable", []))
        if count:
            world.interaction_context["inventory_selected_index"] = max(0,min(count-1,
                world.interaction_context.get("inventory_selected_index",0)-delta))
        return True
    if world.game_state == "DIALOGUE":
        world.dialogue_scroll = max(0,min(getattr(world,"dialogue_max_scroll",0),
                                          getattr(world,"dialogue_scroll",0)+delta*3))
        return True
    if world.game_state == "BOOK_READING":
        ctx = world.book_reading_context
        ctx["scroll_offset"] = max(0, ctx.get("scroll_offset",0)-delta*3)
        return True
    binding = _menu_mouse_binding(world)
    if binding:
        key, select, _ = binding
        record = getattr(world,"menu_hit_regions",{}).get(key)
        if record and record.total:
            context_name, field = {
                "CRAFTING_MENU": ("crafting_menu_context","selected_recipe_index"),
                "BUILDING_MENU": ("building_menu_context","selected_recipe_index"),
                "QUEST_MENU": ("quest_menu_context","selected_quest_index"),
                "NOTICEBOARD_MENU": ("noticeboard_menu_context","selected_task_index"),
                "NOTICEBOARD_ROLES": ("noticeboard_menu_context","selected_role_index"),
                "COMPANY_LEDGER_MENU": ("company_ledger_menu_context","selected_action_index"),
                "INTERACTION_MENU": ("interaction_context","selected_action_index"),
            }.get(key, (None,None))
            if key == "SOCIAL_MENU":
                context_name = "social_menu_context"
                field = "selected_action_index" if world.social_menu_context.get("mode","root") == "root" else "selected_option_index"
            elif key == "GOVERNANCE_MENU":
                context_name = "governance_menu_context"
                field = "selected_action_index" if world.governance_menu_context.get("mode","root") == "root" else "selected_target_index"
            elif key == "TRADE_MENU":
                field = "trade_ui_player_item_index" if world.trade_ui_player_selling else "trade_ui_merchant_item_index"
                select(max(0,min(record.total-1,getattr(world,field)-delta)))
            if context_name:
                current = getattr(world,context_name).get(field,0)
                select(max(0,min(record.total-1,current-delta)))
            return True
    return world.game_state != "PLAYING"

if __name__ == "__main__":
    # main() returns a non-zero code when it cannot start (e.g. no
    # renderer), so surface that as the process exit status rather than
    # exiting 0 after printing an error.
    sys.exit(main() or 0)
