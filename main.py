"""
This module contains the main game loop and handles player input.
"""
import argparse
from tcod_compat import tcod, libtcodpy
import os
import sys
from engine import World
from config import SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, MAP_WIDTH, MAP_HEIGHT, WORLD_WIDTH, WORLD_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT, TILESET_PATH
from data.items import ITEM_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES
from rendering.console_renderer import draw
from save_manager import save_game, load_game
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


def prompt_for_new_player_name(console, context) -> str | None:
    """Prompt for a player first name before generating a new world."""
    input_value = ""
    if hasattr(context, "start_text_input"):
        context.start_text_input()

    try:
        while True:
            console.clear()
            console.print(
                console.width // 2,
                console.height // 3,
                "NEW CHARACTER",
                alignment=libtcodpy.CENTER,
                fg=(255, 255, 0),
            )
            console.print(
                console.width // 2,
                console.height // 2 - 1,
                "Enter your first name",
                alignment=libtcodpy.CENTER,
            )
            console.print(
                console.width // 2,
                console.height // 2 + 1,
                normalize_player_first_name(input_value) if input_value.strip() else "_",
                alignment=libtcodpy.CENTER,
                fg=(255, 255, 255),
            )
            console.print(
                console.width // 2,
                console.height // 2 + 4,
                "Last name is chosen by your in-game family.",
                alignment=libtcodpy.CENTER,
                fg=(160, 160, 160),
            )
            console.print(
                console.width // 2,
                console.height - 4,
                "Enter = start   Esc = cancel",
                alignment=libtcodpy.CENTER,
                fg=(160, 160, 160),
            )
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


def handle_playing_input(event: tcod.event.KeyDown, world: World, context_handler) -> bool:
    """Handles input when the player is in the 'PLAYING' state. Returns True if turn taken."""
    move_keys = {
        tcod.event.KeySym.UP: (0, -1), tcod.event.KeySym.DOWN: (0, 1),
        tcod.event.KeySym.LEFT: (-1, 0), tcod.event.KeySym.RIGHT: (1, 0),
    }

    if event.sym in move_keys:
        dx, dy = move_keys[event.sym]
        action_cost = world.handle_player_movement(dx, dy)
        if action_cost > 0:
            world.game_time += action_cost - 1
            return True
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
    elif event.sym == tcod.event.KeySym.E:
        target_x, target_y = _get_player_facing_position(world)
        open_interaction_menu(world, target_x, target_y)
    elif event.sym == tcod.event.KeySym.T:
        closest_npc = _find_nearest_npc_to_talk_to(world)

        if closest_npc:
            start_dialogue(world, closest_npc, context_handler)
        else:
            world.add_message_to_chat_log("There's no one nearby to talk to.")
    elif event.sym in (tcod.event.KeySym.QUESTION, tcod.event.KeySym.SLASH):
        world.game_state = "HELP_MENU"
    elif event.sym == tcod.event.KeySym.ESCAPE:
        # Show in-game menu or save prompt
        save_game(world)
        world.add_message_to_chat_log("Game Saved.")

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
    elif event.sym in (tcod.event.KeySym.LCTRL, tcod.event.KeySym.RCTRL):
        ctx["selected_entity_index"] = (ctx["selected_entity_index"] + 1) % len(ctx["target_entities"])
        selected_entity = ctx["target_entities"][ctx["selected_entity_index"]]
        ctx["available_actions"] = world._get_actions_for_entity(selected_entity)
        ctx["selected_action_index"] = 0
    elif event.sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.E):
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
        "Talk": lambda: start_dialogue(world, entity_data, context_handler),
        "Attack": lambda: world.player_attempt_attack(entity_data),
        "Feed": lambda: world.player_attempt_feed_animal(entity_data),
        "Ride": lambda: world.player_attempt_ride_animal(entity_data),
        "Till Soil": lambda: world.player_attempt_till_soil(target_x, target_y),
        "Plant Seeds": lambda: world.player_attempt_plant_seeds(target_x, target_y),
        "Dismount": lambda: world.player_attempt_dismount(entity_data),
        "Shear": lambda: world.player_attempt_shear(entity_data),
        "Fish": lambda: world.player_attempt_fish(target_x, target_y),
        "Harvest": lambda: world.player_attempt_harvest(target_x, target_y),
        "Trade": lambda: start_trade(world, entity_data),
        "Pick up": lambda: pick_up_item(world, entity_data, target_x, target_y),
        "Claim House": lambda: claim_house(world, entity_data),

        "Examine": lambda: world.add_message_to_chat_log(f"You see a {selected_entity['name']}."),
        "Smoke Meat": lambda: world.player_attempt_smoke(target_x, target_y),
        "Read": lambda: world.player_attempt_read_book(entity_data["item_key"]),
        "Offer Mercenary Services": lambda: world.player_attempt_mercenary_contract(entity_data),
        "Loot Chest": lambda: world.player_attempt_loot_chest(target_x, target_y)

    }

    if selected_action in action_map:
        action_map[selected_action]()

    if selected_action in ["Talk", "Trade", "Read", "Offer Mercenary Services"]:
        ctx["active"] = False

    apply_ui_requests(world, context_handler)

    if not world.chat_ui_active and not world.trade_ui_active:
        ctx["active"] = False

    # Return True for actions that consume time
    return selected_action not in ["Examine", "Talk", "Trade", "Read"]

def handle_help_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input when the player is in the 'HELP_MENU' state."""
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.QUESTION, tcod.event.KeySym.SLASH):
        world.game_state = "PLAYING"

def handle_info_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input for the info menu."""
    if event.sym in (tcod.event.KeySym.ESCAPE, tcod.event.KeySym.I):
        world.game_state = "PLAYING"
    elif hasattr(tcod.event.KeySym, 'u') and event.sym == tcod.event.KeySym.u:
        world.game_state = "INVENTORY_MENU"
    elif hasattr(tcod.event.KeySym, 'U') and event.sym == tcod.event.KeySym.U:
        world.game_state = "INVENTORY_MENU"

def handle_inventory_menu_input(event: tcod.event.KeyDown, world: World):
    """Handles input for the dedicated inventory menu."""
    if "inventory_scroll_offset" not in world.interaction_context:
        world.interaction_context["inventory_scroll_offset"] = 0

    if event.sym == tcod.event.KeySym.ESCAPE or (hasattr(tcod.event.KeySym, 'u') and event.sym == tcod.event.KeySym.u) or (hasattr(tcod.event.KeySym, 'U') and event.sym == tcod.event.KeySym.U):
        world.game_state = "PLAYING"
    elif event.sym == tcod.event.KeySym.UP:
        world.interaction_context["inventory_scroll_offset"] = max(0, world.interaction_context["inventory_scroll_offset"] - 1)
    elif event.sym == tcod.event.KeySym.DOWN:
        world.interaction_context["inventory_scroll_offset"] += 1

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
            except:
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
    if world.remove_item_from_map(item_key, quantity, x, y):
        world.player.add_item(item_key, quantity)
        item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
        world.add_message_to_chat_log(f"You pick up {quantity}x {item_name}.")

def claim_house(world, building):
    """Claims a house for the player."""
    if building.building_type == "house" and not building.player_owned and not building.residents:
        building.player_owned = True
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
        world = World()
        run_headless(world, args.ticks)
        return

    tileset = load_custom_tileset()
    if not tileset:
        return

    console = tcod.console.Console(SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, order="F")

    # Main Menu State
    main_menu_loop(console, tileset)

def load_custom_tileset():
    """Loads the base ASCII font and appends DawnLike tiles mapped to Unicode PUA."""
    # Base ASCII tileset (16x16 pixels per tile, 32x8 tiles)
    try:
        tileset = tcod.tileset.load_tilesheet("dejavu16x16_gs_tc.png", 32, 8, tcod.tileset.CHARMAP_TCOD)
    except FileNotFoundError:
        print("Error: Font file not found: 'dejavu16x16_gs_tc.png'")
        return None

    # Load combined DawnLike tiles
    try:
        from PIL import Image
        import numpy as np
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
                tileset.set_tile(base_code + (r * cols) + c, tile_arr)

    except Exception as e:
        print(f"Warning: Could not load DawnLike tileset: {e}")

    return tileset

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

            # Draw Menu
            title = "THIS IS LIFE"
            console.print(console.width // 2, console.height // 3, title, alignment=libtcodpy.CENTER, fg=(255, 255, 0))

            for i, option in enumerate(options):
                color = (255, 255, 255) if i == selected_index else (100, 100, 100)
                console.print(console.width // 2, console.height // 2 + i * 2, option, alignment=libtcodpy.CENTER, fg=color)

            context.present(console)

            for event in tcod.event.wait():
                context.convert_event(event)
                if isinstance(event, tcod.event.Quit):
                    raise SystemExit()
                elif isinstance(event, tcod.event.KeyDown):
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
        console.print(console.width // 2, 5, "LOAD GAME", alignment=libtcodpy.CENTER)

        for i, save in enumerate(saves):
            color = (255, 255, 255) if i == selected_index else (100, 100, 100)
            console.print(console.width // 2, 10 + i, save, alignment=libtcodpy.CENTER, fg=color)

        console.print(console.width // 2, console.height - 5, "Press ESC to cancel", alignment=libtcodpy.CENTER)

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
    import time
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

    last_time = time.perf_counter()

    while True:
        # Calculate Delta Time
        current_time = time.perf_counter()
        dt = current_time - last_time
        last_time = current_time

        # Update Animations
        world.update_animations(dt)

        if world.game_state == "PLAYER_DEAD":
            render_game_over(console, context)
            break # Break to return to main menu

        camera_x, camera_y = int(world.player.x) - MAP_WIDTH // 2, int(world.player.y) - MAP_HEIGHT // 2
        camera_x = max(0, min(camera_x, WORLD_WIDTH - MAP_WIDTH))
        camera_y = max(0, min(camera_y, WORLD_HEIGHT - MAP_HEIGHT))
        draw(console, world, camera_x, camera_y)
        context.present(console)

        # Handle Input
        player_acted = handle_events(world, context)

        # Handle turn updates
        # Update if player performed an action OR if auto-moving along a path
        if player_acted or (world.player.state.current_path and world.game_state == "PLAYING"):
            world.update()
            apply_ui_requests(world, context)

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

def render_game_over(console, context):
    """Renders the game over screen."""
    console.clear()
    console.print_box(x=console.width // 2 - 10, y=console.height // 2 - 2,
                      width=20, height=4, string="GAME OVER", alignment=libtcodpy.CENTER)
    console.print(console.width // 2, console.height // 2 + 3, "Press any key...", alignment=libtcodpy.CENTER)
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
        context.convert_event(event)
        if isinstance(event, tcod.event.Quit):
            raise SystemExit()
        if isinstance(event, tcod.event.MouseMotion):
            world.mouse_x, world.mouse_y = int(event.position[0]), int(event.position[1])
        if isinstance(event, tcod.event.MouseButtonDown) and world.game_state == "PLAYING":
            camera_x, camera_y = int(world.player.x) - MAP_WIDTH // 2, int(world.player.y) - MAP_HEIGHT // 2
            camera_x = max(0, min(camera_x, WORLD_WIDTH - MAP_WIDTH))
            camera_y = max(0, min(camera_y, WORLD_HEIGHT - MAP_HEIGHT))
            mouse_world_x, mouse_world_y = int(camera_x + world.mouse_x), int(camera_y + world.mouse_y)

            if event.button == tcod.event.MouseButton.RIGHT:
                world.player.state.current_path = [] # Stop moving if interaction menu opens
                open_interaction_menu(world, mouse_world_x, mouse_world_y)
            elif event.button == tcod.event.MouseButton.LEFT and world.game_state == "PLAYING":
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
            elif world.game_state == "QUEST_MENU":
                handle_quest_menu_input(event, world)
            elif world.game_state == "HELP_MENU":
                handle_help_menu_input(event, world)
            elif world.game_state == "INFO_MENU":
                handle_info_menu_input(event, world)
            elif world.game_state == "INVENTORY_MENU":
                handle_inventory_menu_input(event, world)
            elif world.interaction_context["active"]:
                if handle_interaction_input(event, world, context): turn_taken = True
            elif world.game_state == "CRAFTING_MENU":
                handle_crafting_input(event, world)
            elif world.game_state == "BUILDING_MENU":
                handle_building_input(event, world)
            elif world.game_state == "PLAYING":
                if handle_playing_input(event, world, context): turn_taken = True

    apply_ui_requests(world, context)
    return turn_taken

if __name__ == "__main__":
    main()
