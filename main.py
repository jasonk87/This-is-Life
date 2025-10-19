# main.py
import tcod
import tcod.console
import tcod.event
import tcod.tileset
import os
from engine import World
from config import (
    SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, WORLD_WIDTH, WORLD_HEIGHT,
    REP_CRIMINAL, REP_HERO # Import reputation keys
)
from data.items import ITEM_DEFINITIONS
from rendering.console_renderer import draw


def open_interaction_menu(world: World, x: int, y: int):
    """Opens the interaction menu for a specific tile."""
    entities = world._get_interactables_at(x, y)
    if not entities:
        world.add_message_to_chat_log("There is nothing to interact with here.")
        return

    world.interaction_context["active"] = True
    world.interaction_context["x"] = x
    world.interaction_context["y"] = y
    world.interaction_context["target_entities"] = entities
    world.interaction_context["selected_entity_index"] = 0

    # Get actions for the first entity
    first_entity = entities[0]
    world.interaction_context["available_actions"] = world._get_actions_for_entity(first_entity)
    world.interaction_context["selected_action_index"] = 0


def main():
    """Sets up the game and runs the main loop."""
    move_keys = {
        tcod.event.KeySym.UP: (0, -1),
        tcod.event.KeySym.DOWN: (0, 1),
        tcod.event.KeySym.LEFT: (-1, 0),
        tcod.event.KeySym.RIGHT: (1, 0),
    }

    # --- tcod Tileset Setup (NEW) ---
    # You must download a font file like "dejavu10x10_gs_tc.png"
    # and place it in your project folder for this to work.
    try:
        tileset = tcod.tileset.load_tilesheet(
            "dejavu10x10_gs_tc.png", 32, 8, tcod.tileset.CHARMAP_TCOD
        )
    except FileNotFoundError:
        print("Error: Font file not found: 'dejavu10x10_gs_tc.png'")
        print("Please download this file and place it in the same directory as main.py")
        return # Exit if the font is missing

    console = tcod.console.Console(SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, order="F")

    # --- Game Initialization ---
    world = World()

    # --- Main Game Loop (using tcod's context manager) ---
    with tcod.context.new(
        columns=console.width,
        rows=console.height,
        tileset=tileset,  # <-- Pass the loaded tileset here
        title="This is Life",
        vsync=True,
    ) as context:
        while True:
            # --- Game Logic Updates ---
            # Player actions are handled in event loop below
            # NPC Updates
            world.game_time += 1 # Increment game time

            # --- Jail Time Update ---
            if world.player.is_jailed and world.player.jail_time_remaining > 0:
                world.player.jail_time_remaining -= 1
                if world.player.jail_time_remaining == 0:
                    world.add_message_to_chat_log("Your sentence is over. The guard unlocks the door.")
                    world.player.is_jailed = False
                    door_x, door_y = world.player.jail_cell_coords
                    open_door_def = world.DECORATION_ITEM_DEFINITIONS["iron_door_open"]
                    world._change_map_tile((door_x, door_y), open_door_def)
                    world.player.jail_cell_coords = None


            world._update_player_hunger_thirst() # Update hunger/thirst and apply effects
            world._update_light_level_and_fov() # Update light level and FOV radius
            world._update_world_environment()
            world.update_fov() # Update FOV maps for player and NPCs
            world._update_npc_schedules() # New: Update NPC schedules (includes combat AI decisions)
            world._update_npc_movement() # Update NPC movement (includes combat movement/action execution)
            world._handle_npc_speech()   # Existing: Handle NPC speech (might need timing adjustments)
            if world.game_time % 100 == 0: # Update economy every 100 ticks
                world._update_economy()

            # --- Drawing ---
            if world.game_state == "PLAYER_DEAD":
                console.clear()
                tcod.console_print_box(
                    console,
                    x=console.width // 2 - 10,
                    y=console.height // 2 - 2,
                    width=20,
                    height=4,
                    string="GAME OVER",
                    fg=tcod.white,
                    bg=tcod.black,
                    alignment=tcod.CENTER
                )
                context.present(console)
                # Wait for a key press or quit event before exiting
                for event_deep_loop in tcod.event.wait(): # Inner loop for game over
                    context.convert_event(event_deep_loop)
                    if isinstance(event_deep_loop, tcod.event.Quit):
                        return
                    if isinstance(event_deep_loop, tcod.event.KeyDown):
                        return # Exit on any key press
            else:
                # --- Camera Calculation ---
                camera_x = world.player.x - SCREEN_WIDTH_TILES // 2
                camera_y = world.player.y - SCREEN_HEIGHT_TILES // 2

                draw(console, world, camera_x, camera_y)
                # Update the screen
                context.present(console)

            # --- Event Handling ---
            # tcod.event.wait() will block until an event, which is fine for turn-based.
            # If we want real-time, this structure needs to change.
            for event in tcod.event.wait():
                context.convert_event(event)
                if isinstance(event, tcod.event.Quit):
                    return
                if isinstance(event, tcod.event.MouseMotion):
                    world.mouse_x = int(event.tile.x)
                    world.mouse_y = int(event.tile.y)

                if isinstance(event, tcod.event.MouseButtonDown):
                    if event.button == tcod.event.BUTTON_RIGHT:
                        camera_x = world.player.x - SCREEN_WIDTH_TILES // 2
                        camera_y = world.player.y - SCREEN_HEIGHT_TILES // 2
                        mouse_world_x = camera_x + world.mouse_x
                        mouse_world_y = camera_y + world.mouse_y
                        open_interaction_menu(world, mouse_world_x, mouse_world_y)

                if isinstance(event, tcod.event.TextInput):
                    if world.chat_ui_active: # Only process text input if chat UI is active
                        world.chat_ui_input_line += event.text

                elif isinstance(event, tcod.event.KeyDown):
                    # --- UI Mode: Trade UI Active ---
                    if world.trade_ui_active:
                        if event.sym == tcod.event.KeySym.ESCAPE:
                            world.trade_ui_active = False
                            world.add_message_to_chat_log("Trade cancelled.")
                            world.trade_ui_npc_target = None
                        elif event.sym == tcod.event.KeySym.TAB:
                            world.trade_ui_player_selling = not world.trade_ui_player_selling
                            if world.trade_ui_player_selling: world.trade_ui_player_item_index = 0
                            else: world.trade_ui_merchant_item_index = 0
                        elif event.sym == tcod.event.KeySym.UP:
                            if world.trade_ui_player_selling:
                                if world.trade_ui_player_inventory_snapshot:
                                    world.trade_ui_player_item_index = (world.trade_ui_player_item_index - 1) % len(world.trade_ui_player_inventory_snapshot)
                            else: # Merchant view
                                if world.trade_ui_merchant_inventory_snapshot:
                                    world.trade_ui_merchant_item_index = (world.trade_ui_merchant_item_index - 1) % len(world.trade_ui_merchant_inventory_snapshot)
                        elif event.sym == tcod.event.KeySym.DOWN:
                            if world.trade_ui_player_selling:
                                if world.trade_ui_player_inventory_snapshot:
                                    world.trade_ui_player_item_index = (world.trade_ui_player_item_index + 1) % len(world.trade_ui_player_inventory_snapshot)
                            else: # Merchant view
                                if world.trade_ui_merchant_inventory_snapshot:
                                    world.trade_ui_merchant_item_index = (world.trade_ui_merchant_item_index + 1) % len(world.trade_ui_merchant_inventory_snapshot)
                        elif event.sym == tcod.event.KeySym.RETURN or event.sym == tcod.event.KeySym.E: # Buy/Sell selected item
                            world.handle_trade_action() # New method in engine.py to process the transaction
                            # After action, re-initialize to refresh snapshots and indices
                            if world.trade_ui_active: # If trade didn't auto-close
                                world.initialize_trade_session()

                    # --- UI Mode: Chat UI Active ---
                    elif world.chat_ui_active:
                        if event.sym == tcod.event.KeySym.ESCAPE:
                            context.stop_text_input()
                            world.chat_ui_active = False
                            world.add_message_to_chat_log(f"Ended interaction with {world.chat_ui_target_npc.name if world.chat_ui_target_npc else 'someone'}.")
                            world.chat_ui_target_npc = None
                            world.chat_ui_input_line = ""
                        elif event.sym == tcod.event.KeySym.BACKSPACE:
                            if world.chat_ui_input_line:
                                world.chat_ui_input_line = world.chat_ui_input_line[:-1]
                        elif event.sym == tcod.event.KeySym.RETURN:
                            if world.chat_ui_input_line:
                                player_input = world.chat_ui_input_line
                                world.chat_ui_history.append(("Player", player_input))
                                world.chat_ui_input_line = ""

                                if world.chat_ui_mode == "talk":
                                    # Check if player is accepting a pending job offer
                                    if world.player.pending_contract_offer and \
                                       world.chat_ui_target_npc and \
                                       world.player.pending_contract_offer["npc_offerer_id"] == world.chat_ui_target_npc.id and \
                                       player_input.lower() in ["yes", "accept", "ok", "sure", "y"]:

                                        contract = world.player.pending_contract_offer
                                        world.player.active_contracts[contract["contract_id"]] = {
                                            "npc_id": contract["npc_id"], "item_key": contract["item_key"],
                                            "quantity_needed": contract["quantity_needed"], "reward": contract["reward"],
                                            "progress_text": f"Deliver {contract['quantity_needed']} {contract['item_key']}(s) to {world.chat_ui_target_npc.name}.",
                                            "turn_in_npc_id": contract["npc_id"]
                                        }
                                        world.chat_ui_history.append(("System", f"Job accepted: {contract['progress_text']}"))
                                        world.player.pending_contract_offer = None

                                    # Check if player is accepting a pending quest offer
                                    elif world.pending_quest_offer and \
                                         world.chat_ui_target_npc and \
                                         world.pending_quest_offer["npc_offerer_id"] == world.chat_ui_target_npc.id and \
                                         player_input.lower() in world.QUEST_DEFINITIONS.get(world.pending_quest_offer["quest_id"], {}).get("dialogue_accept_player", ["yes", "accept", "ok", "sure", "y"]):

                                        quest_id_to_accept = world.pending_quest_offer["quest_id"]
                                        quest_def = world.QUEST_DEFINITIONS.get(quest_id_to_accept)
                                        if quest_def:
                                            world.player.active_quests[quest_id_to_accept] = {
                                                "id": quest_id_to_accept,
                                                "title": quest_def["title"],
                                                "type": quest_def["type"],
                                                "target_npc_name_prefix": quest_def.get("target_npc_name_prefix"),
                                                "target_count": quest_def.get("target_count", 0),
                                                "item_to_fetch_key": quest_def.get("item_to_fetch_key"),
                                                "item_fetch_count": quest_def.get("item_fetch_count", 0),
                                                "progress": 0,
                                                "quest_giver_id_or_role": quest_def["quest_giver_id_or_role"], # Store for turn-in
                                                "npc_offerer_id": world.chat_ui_target_npc.id # Store who gave it
                                            }
                                            accept_response = quest_def.get("dialogue_accept_npc_response", "Good luck.")
                                            world.chat_ui_history.append((world.chat_ui_target_npc.name, accept_response))
                                            world.chat_ui_history.append(("System", f"Quest accepted: {quest_def['title']}"))
                                            world.pending_quest_offer = None
                                        else:
                                            world.add_message_to_chat_log(f"Error: Tried to accept unknown quest '{quest_id_to_accept}'.")
                                            world.pending_quest_offer = None

                                    elif world.chat_ui_target_npc: # Regular talk
                                        world.continue_npc_dialogue(world.chat_ui_target_npc, player_input)
                                    else:
                                        world.add_message_to_chat_log("Error: No target NPC for dialogue continuation.")

                                elif world.chat_ui_mode == "persuade_goal_input":
                                    world.attempt_persuasion(world.chat_ui_target_npc, player_input)
                                    context.stop_text_input()
                                    world.chat_ui_active = False
                                    world.add_message_to_chat_log(f"Persuasion attempt made with {world.chat_ui_target_npc.name}.")
                                    world.chat_ui_target_npc = None

                                if len(world.chat_ui_history) > world.chat_ui_max_history:
                                    world.chat_ui_history = world.chat_ui_history[-world.chat_ui_max_history:]
                                world.chat_ui_scroll_offset = 0
                    
                    # --- UI Mode: Interaction Menu Active ---
                    elif world.interaction_context["active"]:
                        ctx = world.interaction_context
                        if event.sym == tcod.event.KeySym.UP:
                            ctx["selected_action_index"] = (ctx["selected_action_index"] - 1) % len(ctx["available_actions"])
                        elif event.sym == tcod.event.KeySym.DOWN:
                            ctx["selected_action_index"] = (ctx["selected_action_index"] + 1) % len(ctx["available_actions"])
                        elif event.sym == tcod.event.KeySym.LCTRL or event.sym == tcod.event.KeySym.RCTRL:
                            ctx["selected_entity_index"] = (ctx["selected_entity_index"] + 1) % len(ctx["target_entities"])
                            # Update actions for the new entity
                            selected_entity = ctx["target_entities"][ctx["selected_entity_index"]]
                            ctx["available_actions"] = world._get_actions_for_entity(selected_entity)
                            ctx["selected_action_index"] = 0
                        elif event.sym == tcod.event.KeySym.RETURN or event.sym == tcod.event.KeySym.E:
                            # Execute action
                            # This part will be complex, mapping action strings to methods
                            world.add_message_to_chat_log("Action execution not fully implemented yet.")
                            ctx["active"] = False # Close menu for now
                        elif event.sym == tcod.event.KeySym.ESCAPE:
                            ctx["active"] = False

                    # --- UI Mode: Info Menu Active (or toggling it) ---
                    elif event.sym == tcod.event.KeySym.I:
                        # This check ensures info menu doesn't open if other modal UIs are active
                        if not world.chat_ui_active and not world.trade_ui_active and not world.interaction_menu_active: # Added trade_ui_active check
                             world.game_state = "INFO_MENU" if world.game_state == "PLAYING" else "PLAYING"

                    # --- Game State: Playing (No other UI is active) ---
                    elif world.game_state == "PLAYING":
                        if event.sym in move_keys:
                            dx, dy = move_keys[event.sym]
                            world.handle_player_movement(dx, dy)
                        elif event.sym == tcod.event.KeySym.C: # Craft healing salve
                            world.craft_item("healing_salve")
                        elif event.sym == tcod.event.KeySym.S: # Craft crude spear
                            world.craft_item("crude_spear")
                        elif event.sym == tcod.event.KeySym.X: # Craft wooden shield
                            world.craft_item("wooden_shield")
                        # M for Meat (Cooked) - conceptual, might require fire nearby later
                        # For now, let's assume 'M' crafts it if ingredients are present.
                        elif event.sym == tcod.event.KeySym.M:
                            world.craft_item("cooked_meat_scrap")
                        elif event.sym == tcod.event.KeySym.H: # Use healing salve (example)
                            world.use_item("healing_salve")
                        # Keybind for using cooked meat scrap - let's use 'U' for "Use food"
                        elif event.sym == tcod.event.KeySym.U:
                            world.use_item("cooked_meat_scrap")
                        elif event.sym == tcod.event.KeySym.D: # Debug damage
                            world.player.take_damage(5)
                            world.add_message_to_chat_log(f"You took 5 damage! Current HP: {world.player.hp}")
                        elif event.sym == tcod.event.KeySym.K: # Debug criminal rep
                            world.player.adjust_reputation(REP_CRIMINAL, 10)
                            world.add_message_to_chat_log(f"Criminal points +10. Total: {world.player.reputation[REP_CRIMINAL]}")
                        elif event.sym == tcod.event.KeySym.J: # Debug hero rep
                            world.player.adjust_reputation(REP_HERO, 10)
                            world.add_message_to_chat_log(f"Hero points +10. Total: {world.player.reputation[REP_HERO]}")
                        elif event.sym == tcod.event.KeySym.B: # Toggle Build Mode
                            current_building_at_player = world.get_building_by_tile_coords(world.player.x, world.player.y)
                            if current_building_at_player and current_building_at_player.player_owned:
                                if world.game_state == "PLAYING":
                                    world.game_state = "BUILD_MODE"
                                    world.add_message_to_chat_log("Entered build mode. B/ESC to exit. UP/DOWN to select item. ENTER to place.")
                                    # Initialize ghost tile for selected item
                                    if world.placeable_furniture_keys: # Check if list is not empty
                                        selected_item_key = world.placeable_furniture_keys[world.build_mode_selected_item_index]
                                        item_def = ALL_DECORATION_DEFS.get(selected_item_key) # Use aliased import
                                        if item_def:
                                            world.ghost_furniture_tile = BaseTileType(item_def["char"], item_def["color"], True, item_def["name"], item_def.get("properties", {})) # Use aliased import
                                    else:
                                        world.ghost_furniture_tile = None
                                elif world.game_state == "BUILD_MODE":
                                    world.game_state = "PLAYING"
                                    world.add_message_to_chat_log("Exited build mode.")
                                    world.ghost_furniture_tile = None
                            else:
                                world.add_message_to_chat_log("You can only build inside a house you own.")
                        elif event.sym == tcod.event.KeySym.E:
                            target_x = world.player.x + world.player.last_dx
                            target_y = world.player.y + world.player.last_dy
                            open_interaction_menu(world, target_x, target_y)

                    # --- Game State: Build Mode ---
                    elif world.game_state == "BUILD_MODE":
                        if event.sym == tcod.event.KeySym.ESCAPE or event.sym == tcod.event.KeySym.B:
                            world.game_state = "PLAYING"
                            world.add_message_to_chat_log("Exited build mode.")
                            world.ghost_furniture_tile = None
                        elif event.sym in move_keys: # Player movement still works to position for placement
                            dx, dy = move_keys[event.sym]
                            # Store original char before potential sitting from handle_player_movement
                            original_char = world.player.char
                            world.handle_player_movement(dx, dy)
                            world.player.char = original_char # Ensure player char remains '@' or original in build mode
                            world.player.is_sitting = False # Prevent sitting in build mode from movement
                             # Update ghost tile position (implicitly handled by renderer based on player facing)
                        elif event.sym == tcod.event.KeySym.UP:
                            if world.placeable_furniture_keys:
                                world.build_mode_selected_item_index = (world.build_mode_selected_item_index - 1) % len(world.placeable_furniture_keys)
                                selected_item_key = world.placeable_furniture_keys[world.build_mode_selected_item_index]
                                item_def = ALL_DECORATION_DEFS.get(selected_item_key)
                                if item_def:
                                    world.ghost_furniture_tile = BaseTileType(item_def["char"], item_def["color"], True, item_def["name"], item_def.get("properties", {}))
                        elif event.sym == tcod.event.KeySym.DOWN:
                            if world.placeable_furniture_keys:
                                world.build_mode_selected_item_index = (world.build_mode_selected_item_index + 1) % len(world.placeable_furniture_keys)
                                selected_item_key = world.placeable_furniture_keys[world.build_mode_selected_item_index]
                                item_def = ALL_DECORATION_DEFS.get(selected_item_key)
                                if item_def:
                                    world.ghost_furniture_tile = BaseTileType(item_def["char"], item_def["color"], True, item_def["name"], item_def.get("properties", {}))
                        elif event.sym == tcod.event.KeySym.RETURN or event.sym == tcod.event.KeySym.E: # Place item
                            if world.placeable_furniture_keys and world.ghost_furniture_tile:
                                selected_item_key = world.placeable_furniture_keys[world.build_mode_selected_item_index]
                                item_def_to_place = ALL_DECORATION_DEFS.get(selected_item_key)

                                if item_def_to_place:
                                    target_x = world.player.x + world.player.last_dx
                                    target_y = world.player.y + world.player.last_dy

                                    # Validate placement
                                    current_building = world.get_building_by_tile_coords(world.player.x, world.player.y) # Building player is in
                                    target_tile_current_obj = world.get_tile_at(target_x, target_y)

                                    can_place = True
                                    # 1. Is player in their owned building?
                                    if not (current_building and current_building.player_owned):
                                        world.add_message_to_chat_log("You must be inside your own building to place furniture.")
                                        can_place = False
                                    # 2. Is target tile within that same building?
                                    elif not current_building.contains_global_coords(target_x, target_y):
                                        world.add_message_to_chat_log("You can only place furniture inside this building.")
                                        can_place = False
                                    # 3. Is the target tile a passable floor?
                                    elif not (target_tile_current_obj and target_tile_current_obj.passable and "floor" in target_tile_current_obj.name.lower()):
                                        world.add_message_to_chat_log(f"Cannot place furniture on '{target_tile_current_obj.name if target_tile_current_obj else 'solid ground'}'. Must be clear floor.")
                                        can_place = False

                                    # 4. Check resources
                                    cost = item_def_to_place.get("placement_cost", {})
                                    if not cost: # No cost defined, allow free placement for now
                                        pass
                                    else:
                                        for resource_key, required_qty in cost.items():
                                            if world.player.inventory.get(resource_key, 0) < required_qty:
                                                item_name_for_msg = ITEM_DEFINITIONS.get(resource_key, {}).get("name", resource_key)
                                                world.add_message_to_chat_log(f"Not enough resources. Need {required_qty}x {item_name_for_msg}.")
                                                can_place = False
                                                break

                                    if can_place:
                                        # Deduct resources
                                        for resource_key, required_qty in cost.items():
                                            world.player.inventory[resource_key] -= required_qty
                                            if world.player.inventory[resource_key] <= 0:
                                                del world.player.inventory[resource_key]

                                        # Place the item
                                        new_furniture_tile = BaseTileType(
                                            item_def_to_place["char"],
                                            item_def_to_place["color"],
                                            item_def_to_place["passable"],
                                            item_def_to_place["name"],
                                            item_def_to_place.get("properties", {})
                                        )
                                        chunk_x, chunk_y = target_x // CHUNK_SIZE, target_y // CHUNK_SIZE
                                        local_x, local_y = target_x % CHUNK_SIZE, target_y % CHUNK_SIZE
                                        world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = new_furniture_tile

                                        # Update transparency map if it blocks FOV
                                        if new_furniture_tile.properties.get("blocks_fov", False): # Default to False if not specified
                                            world.transparency_map[target_x, target_y] = False
                                        else: # Ensure it's True if it doesn't block (e.g. replacing a floor tile)
                                            world.transparency_map[target_x, target_y] = True

                                        world.add_message_to_chat_log(f"Placed {item_def_to_place['name']}.")
                                        # Recalculate player FOV as transparency might have changed
                                        world.update_fov()


                    # --- Interaction Menu Option Handling ---
                    elif world.interaction_menu_active:
                        if event.sym == tcod.event.KeySym.UP:
                            if world.interaction_menu_options:
                                world.interaction_menu_selected_index = \
                                    (world.interaction_menu_selected_index - 1) % len(world.interaction_menu_options)
                        elif event.sym == tcod.event.KeySym.DOWN:
                            if world.interaction_menu_options:
                                world.interaction_menu_selected_index = \
                                    (world.interaction_menu_selected_index + 1) % len(world.interaction_menu_options)
                        elif event.sym == tcod.event.KeySym.RETURN or event.sym == tcod.event.KeySym.E:
                            if world.interaction_menu_options:
                                selected_option_text = world.interaction_menu_options[world.interaction_menu_selected_index]
                                target_npc = world.interaction_menu_target_npc
                                target_building = world.interaction_menu_target_building

                                world.interaction_menu_active = False # Close menu

                                if selected_option_text.startswith("Claim this"):
                                    if target_building and target_building.building_type == "house" and \
                                       not target_building.player_owned and not target_building.residents:
                                        target_building.player_owned = True
                                        world.add_message_to_chat_log(f"You have claimed this {target_building.building_type} as your own!")
                                    else:
                                        world.add_message_to_chat_log("You cannot claim this structure.")
                                elif selected_option_text == "Open door" or selected_option_text == "Close door":
                                    # This assumes the player is still facing the door they initiated interaction with
                                    facing_x = world.player.x + world.player.last_dx
                                    facing_y = world.player.y + world.player.last_dy
                                    world.player_attempt_toggle_door(facing_x, facing_y)
                                elif selected_option_text == "Talk": # ... (Talk, Persuade, Trade, Attack, Complete Contract as before)
                                    if target_npc:
                                        world.chat_ui_target_npc = target_npc
                                        world.chat_ui_mode = "talk"
                                        world.start_npc_dialogue(target_npc)
                                        world.chat_ui_active = True
                                        context.start_text_input()
                                elif selected_option_text == "Persuade":
                                    if target_npc:
                                        world.chat_ui_target_npc = target_npc
                                        world.chat_ui_mode = "persuade_goal_input" # ... setup persuade UI ...
                                        world.chat_ui_history.clear()
                                        world.chat_ui_scroll_offset = 0
                                        world.chat_ui_input_line = ""
                                        world.chat_ui_history.append(("System", f"Persuade {target_npc.name}: What is your goal?"))
                                        world.chat_ui_active = True
                                        context.start_text_input()
                                elif selected_option_text == "Trade":
                                    if target_npc and target_npc.profession == "Merchant":
                                        world.trade_ui_npc_target = target_npc
                                        world.initialize_trade_session()
                                        world.trade_ui_active = True
                                    else:
                                        world.add_message_to_chat_log(f"{target_npc.name if target_npc else 'They'} are not a merchant.")
                                elif selected_option_text == "Attack":
                                    if target_npc and not target_npc.is_dead:
                                        world.player_attempt_attack(target_npc)
                                elif selected_option_text.startswith("Complete Contract:"):
                                    if target_npc:
                                        # Simplified: assumes contract key is part of the option text or derivable
                                        # This part needs robust parsing if there are multiple contract types.
                                        # For "lumber_delivery_{target_npc.id}"
                                        contract_id_to_complete = f"lumber_delivery_{target_npc.id}"
                                        if contract_id_to_complete in world.player.active_contracts:
                                            world.complete_contract_delivery(contract_id_to_complete, target_npc)
                                            # Decide if chat UI should open
                                            if not world.chat_ui_active: # Open chat if not already, to show dialogue
                                                world.chat_ui_target_npc = target_npc
                                                world.chat_ui_mode = "talk"
                                                world.chat_ui_active = True
                                                context.start_text_input()
                                        else:
                                            world.add_message_to_chat_log("Could not find that specific contract to complete.")
                                    else:
                                        world.add_message_to_chat_log("Error: No target NPC for contract completion.")
                                elif selected_option_text.startswith("Quest - "):
                                    if target_npc:
                                        # Extract quest title from menu option to find quest_id
                                        # Example: "Quest - Wolf Extermination (Complete)" -> "Wolf Extermination"
                                        try:
                                            quest_title_in_menu = selected_option_text.split(" - ")[1].split(" (")[0]
                                            found_quest_id = None
                                            for q_id, q_data in world.player.active_quests.items():
                                                if q_data["title"] == quest_title_in_menu:
                                                    found_quest_id = q_id
                                                    break

                                            if found_quest_id:
                                                world.complete_quest(found_quest_id, target_npc)
                                                # Potentially open chat UI to show NPC dialogue from complete_quest
                                                if not world.chat_ui_active:
                                                    world.chat_ui_target_npc = target_npc
                                                    world.chat_ui_mode = "talk"
                                                    world.chat_ui_active = True
                                                    context.start_text_input()
                                            else:
                                                world.add_message_to_chat_log(f"Could not find active quest: {quest_title_in_menu}")
                                        except IndexError:
                                            world.add_message_to_chat_log("Error parsing quest option.")
                                    else:
                                        world.add_message_to_chat_log("Error: No target NPC for quest interaction.")
                                elif selected_option_text == "Cancel":
                                    world.add_message_to_chat_log("Interaction cancelled.")
                                world.interaction_menu_target_npc = None
                                world.interaction_menu_target_building = None
                        elif event.sym == tcod.event.KeySym.ESCAPE:
                            world.interaction_menu_active = False
                            world.interaction_menu_target_npc = None
                            world.interaction_menu_target_building = None
                            world.add_message_to_chat_log("Interaction cancelled.")

                    if event.sym == tcod.event.KeySym.Q: # Global quit, checked after UI specific escapes
                        return

if __name__ == "__main__":
    main()