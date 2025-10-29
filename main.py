"""
This module contains the main game loop and handles player input.
"""
import argparse
import tcod
import tcod.console
import tcod.event
import tcod.tileset
from engine import World
from config import SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES
from data.items import ITEM_DEFINITIONS
from rendering.console_renderer import draw

def handle_playing_input(event: tcod.event.KeyDown, world: World, context_handler):
    """Handles input when the player is in the 'PLAYING' state."""
    move_keys = {
        tcod.event.KeySym.UP: (0, -1), tcod.event.KeySym.DOWN: (0, 1),
        tcod.event.KeySym.LEFT: (-1, 0), tcod.event.KeySym.RIGHT: (1, 0),
    }

    if event.sym in move_keys:
        dx, dy = move_keys[event.sym]
        action_cost = world.handle_player_movement(dx, dy)
        if action_cost > 0:
            world.game_time += action_cost - 1
    elif event.sym == tcod.event.KeySym.C:
        world.game_state = "CRAFTING_MENU"
        world.crafting_menu_context["all_recipes"] = [
            key for key, definition in ITEM_DEFINITIONS.items() if "crafting_recipe" in definition
        ]
        world.crafting_menu_context["all_recipes"].sort(key=lambda k: ITEM_DEFINITIONS[k].get("name", k))
    elif event.sym == tcod.event.KeySym.E:
        target_x, target_y = world.player.x + world.player.last_dx, world.player.y + world.player.last_dy
        open_interaction_menu(world, target_x, target_y)
    elif event.sym == tcod.event.KeySym.T:
        # Find nearest NPC to talk to
        import math
        closest_npc = None
        min_dist = float('inf')
        for npc in world.village_npcs + world.npcs:
            if not npc.is_dead:
                dist = math.sqrt((world.player.x - npc.x)**2 + (world.player.y - npc.y)**2)
                if dist < min_dist and dist <= 5: # Max talk distance
                    min_dist = dist
                    closest_npc = npc

        if closest_npc:
            start_dialogue(world, closest_npc, context_handler)
        else:
            world.add_message_to_chat_log("There's no one nearby to talk to.")

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

def handle_interaction_input(event: tcod.event.KeyDown, world: World, context_handler):
    """Handles input when the interaction menu is active."""
    ctx = world.interaction_context
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
        execute_interaction(world, context_handler)
    elif event.sym == tcod.event.KeySym.ESCAPE:
        ctx["active"] = False

def open_interaction_menu(world: World, x: int, y: int):
    """Opens the interaction menu for a specific tile."""
    entities = world._get_interactables_at(x, y)
    if not entities:
        world.add_message_to_chat_log("There is nothing to interact with here.")
        return

    world.interaction_context["active"] = True
    world.interaction_context["x"], world.interaction_context["y"] = x, y
    world.interaction_context["target_entities"] = entities
    world.interaction_context["selected_entity_index"] = 0
    world.interaction_context["available_actions"] = world._get_actions_for_entity(entities[0])
    world.interaction_context["selected_action_index"] = 0

def execute_interaction(world: World, context_handler):
    """Executes the selected action from the interaction context."""
    ctx = world.interaction_context
    if not ctx["active"]:
        return

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
        "Dismount": lambda: world.player_attempt_dismount(entity_data),
        "Shear": lambda: world.player_attempt_shear(entity_data),
        "Fish": lambda: world.player_attempt_fish(target_x, target_y),
        "Trade": lambda: start_trade(world, entity_data),
        "Pick up": lambda: pick_up_item(world, entity_data, target_x, target_y),
        "Claim House": lambda: claim_house(world, entity_data),
        "Examine": lambda: world.add_message_to_chat_log(f"You see a {selected_entity['name']}.")
    }

    if selected_action in action_map:
        action_map[selected_action]()

    if not world.chat_ui_active and not world.trade_ui_active:
        ctx["active"] = False

def handle_dialogue_input(event: tcod.event.KeyDown, world: World, context_handler):
    """Handles input when the player is in the 'DIALOGUE' state."""
    if event.sym == tcod.event.KeySym.ESCAPE:
        world.game_state = "PLAYING"
        world.chat_ui_active = False
        context_handler.stop_text_input()
    elif event.sym == tcod.event.KeySym.RETURN:
        if world.chat_ui_input_line:
            # Add player's line to history and process NPC response
            world.chat_ui_history.append(("Player", world.chat_ui_input_line))
            world.continue_npc_dialogue(world.chat_ui_target_npc, world.chat_ui_input_line)
            world.chat_ui_input_line = "" # Clear input line
    elif event.sym == tcod.event.KeySym.BACKSPACE:
        if world.chat_ui_input_line:
            world.chat_ui_input_line = world.chat_ui_input_line[:-1]

def start_dialogue(world, npc, context_handler):
    """Starts a dialogue with an NPC."""
    world.game_state = "DIALOGUE"
    world.chat_ui_target_npc = npc
    world.chat_ui_mode = "talk"
    world.start_npc_dialogue(npc)
    world.chat_ui_active = True
    context_handler.start_text_input()

def start_trade(world, npc):
    """Starts a trade session with an NPC."""
    if npc.profession == "Merchant":
        world.trade_ui_npc_target = npc
        world.initialize_trade_session()
        world.trade_ui_active = True
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
    args = parser.parse_args()

    world = World()
    if args.headless:
        run_headless(world)
        return

    try:
        tileset = tcod.tileset.load_tilesheet("dejavu10x10_gs_tc.png", 32, 8, tcod.tileset.CHARMAP_TCOD)
    except FileNotFoundError:
        print("Error: Font file not found: 'dejavu10x10_gs_tc.png'")
        return

    console = tcod.console.Console(SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, order="F")
    with tcod.context.new(columns=console.width, rows=console.height, tileset=tileset,
                          title="This is Life", vsync=True) as context:
        while True:
            world.update()

            if world.needs_text_input:
                context.start_text_input()
                world.needs_text_input = False

            if world.game_state == "PLAYER_DEAD":
                render_game_over(console, context)
                break
            camera_x, camera_y = world.player.x - SCREEN_WIDTH_TILES // 2, world.player.y - SCREEN_HEIGHT_TILES // 2
            draw(console, world, camera_x, camera_y)
            context.present(console)
            handle_events(world, context)

def run_headless(world):
    """Runs the game for a fixed number of ticks in headless mode."""
    print("Running in headless mode...")
    for _ in range(1000):
        world.update()
    print("Headless mode run complete.")

def render_game_over(console, context):
    """Renders the game over screen."""
    console.clear()
    console.print_box(x=console.width // 2 - 10, y=console.height // 2 - 2,
                      width=20, height=4, string="GAME OVER", alignment=tcod.CENTER)
    context.present(console)
    for event in tcod.event.wait():
        context.convert_event(event)
        if isinstance(event, (tcod.event.Quit, tcod.event.KeyDown)):
            return

def handle_events(world, context):
    """Handles all player input and game events."""
    for event in tcod.event.get():
        if isinstance(event, tcod.event.Quit):
            raise SystemExit()
        if isinstance(event, tcod.event.MouseMotion):
            world.mouse_x, world.mouse_y = event.tile
        if isinstance(event, tcod.event.MouseButtonDown) and event.button == tcod.event.MouseButton.RIGHT:
            camera_x, camera_y = world.player.x - SCREEN_WIDTH_TILES // 2, world.player.y - SCREEN_HEIGHT_TILES // 2
            mouse_world_x, mouse_world_y = camera_x + world.mouse_x, camera_y + world.mouse_y
            open_interaction_menu(world, mouse_world_x, mouse_world_y)
        if isinstance(event, tcod.event.TextInput) and world.chat_ui_active:
            world.chat_ui_input_line += event.text
        elif isinstance(event, tcod.event.KeyDown):
            if world.interaction_context["active"]:
                handle_interaction_input(event, world, context)
            elif world.game_state == "CRAFTING_MENU":
                handle_crafting_input(event, world)
            elif world.game_state == "DIALOGUE":
                handle_dialogue_input(event, world, context)
            elif world.game_state == "PLAYING":
                handle_playing_input(event, world, context)

if __name__ == "__main__":
    main()
