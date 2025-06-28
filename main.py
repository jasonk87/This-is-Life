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
from rendering.console_renderer import draw, draw_info_menu


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
            world._update_npc_schedules() # New: Update NPC schedules
            world._update_npc_movement() # Update NPC movement
            world._handle_npc_speech()   # Existing: Handle NPC speech (might need timing adjustments)

            # --- Drawing ---
            draw(console, world)
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
                if isinstance(event, tcod.event.KeyDown):
                    if event.sym == tcod.event.KeySym.I: # Toggle Info Menu
                        if not world.interaction_menu_active: # Don't toggle info if interaction menu is up
                            world.game_state = "INFO_MENU" if world.game_state == "PLAYING" else "PLAYING"
                    
                    # --- Interaction Menu Active Logic ---
                    elif world.interaction_menu_active:
                        if event.sym == tcod.event.KeySym.UP:
                            world.interaction_menu_selected_index = (world.interaction_menu_selected_index - 1) % len(world.interaction_menu_options)
                        elif event.sym == tcod.event.KeySym.DOWN:
                            world.interaction_menu_selected_index = (world.interaction_menu_selected_index + 1) % len(world.interaction_menu_options)
                        elif event.sym == tcod.event.KeySym.RETURN or event.sym == tcod.event.KeySym.E:
                            selected_option = world.interaction_menu_options[world.interaction_menu_selected_index]
                            # --- Stubbed actions for now ---
                            if selected_option == "Talk":
                                # world.talk_to_npc(world.interaction_menu_target_npc) # We need to pass the NPC
                                # For now, use the existing world.talk_to_npc() which finds closest.
                                # This needs refinement: talk_to_npc should accept a target.
                                # Let's assume world.talk_to_npc() will be refactored or a new one created.
                                if world.interaction_menu_target_npc:
                                     world.add_message_to_chat_log(f"Selected [Talk] with {world.interaction_menu_target_npc.name}. (Implementation pending full chat UI)")
                                     # world.talk_to_specific_npc(world.interaction_menu_target_npc) # Ideal
                                     # For now, let's use the existing talk_to_npc and hope it targets correctly based on proximity
                                     # or that we refactor talk_to_npc to take a target.
                                     # The old talk_to_npc also set last_talked_to_npc, which is now interaction_menu_target_npc
                                     # For this step, we just log. Actual call to LLM dialogue will be when chat UI is built.
                                else:
                                    world.add_message_to_chat_log("Error: No target NPC for talk.")

                            elif selected_option == "Persuade":
                                if world.interaction_menu_target_npc:
                                    # Using console input for persuasion goal temporarily
                                    context.present(console) # Refresh screen before input
                                    print(f"\nAttempting to persuade {world.interaction_menu_target_npc.name}. What is your goal?")
                                    goal_text = input("> ")
                                    if goal_text:
                                        world.attempt_persuasion(world.interaction_menu_target_npc, goal_text)
                                    else:
                                        world.add_message_to_chat_log("Persuasion cancelled (no goal entered).")
                                else:
                                    world.add_message_to_chat_log("Error: No target NPC for persuade.")

                            elif selected_option == "Trade (Not Implemented)":
                                world.add_message_to_chat_log("Trade system not yet implemented.")

                            # For all options including "Cancel", close the menu
                            world.interaction_menu_active = False
                            world.interaction_menu_target_npc = None # Clear target
                            if selected_option != "Cancel":
                                world.add_message_to_chat_log(f"Action: {selected_option}")
                            else:
                                world.add_message_to_chat_log("Interaction cancelled.")

                        elif event.sym == tcod.event.KeySym.ESCAPE:
                            world.interaction_menu_active = False
                            world.interaction_menu_target_npc = None
                            world.add_message_to_chat_log("Interaction cancelled.")

                    # --- Playing State Logic (Menu not active) ---
                    elif world.game_state == "PLAYING":
                        if event.sym in move_keys:
                            dx, dy = move_keys[event.sym]
                            world.handle_player_movement(dx, dy)
                        elif event.sym == tcod.event.KeySym.C:
                            world.craft_item("healing_salve")
                        elif event.sym == tcod.event.KeySym.H:
                            world.use_item("healing_salve")
                        elif event.sym == tcod.event.KeySym.D: # Debug damage
                            world.player.take_damage(5)
                            print(f"You took 5 damage! Current HP: {world.player.hp}")
                        # Old 'T' key for talk is removed.
                        # --- Reputation Debug Keys ---
                        elif event.sym == tcod.event.KeySym.K:
                            world.player.adjust_reputation(REP_CRIMINAL, 10)
                            world.add_message_to_chat_log(f"Criminal points +10. Total: {world.player.reputation[REP_CRIMINAL]}")
                        elif event.sym == tcod.event.KeySym.J:
                            world.player.adjust_reputation(REP_HERO, 10)
                            world.add_message_to_chat_log(f"Hero points +10. Total: {world.player.reputation[REP_HERO]}")

                        elif event.sym == tcod.event.KeySym.E: # General Interact Key
                            target_x = world.player.x + world.player.last_dx
                            target_y = world.player.y + world.player.last_dy

                            targeted_npc = None
                            # Check for NPC at target location first
                            # Combine NPC lists for checking
                            all_npcs = world.npcs + world.village_npcs
                            for npc_obj in all_npcs:
                                if npc_obj.x == target_x and npc_obj.y == target_y:
                                    targeted_npc = npc_obj
                                    break

                            if targeted_npc: # NPC found, open interaction menu
                                world.interaction_menu_target_npc = targeted_npc
                                world.interaction_menu_options = ["Talk", "Persuade", "Trade (Not Implemented)", "Cancel"]
                                world.interaction_menu_selected_index = 0

                                # Determine menu position (e.g., relative to player on screen)
                                # This needs screen coordinates, not world. Renderer will handle final placement.
                                # For now, store relative or placeholder values.
                                world.interaction_menu_x = console.width // 2 # Example placeholder
                                world.interaction_menu_y = console.height // 2
                                world.interaction_menu_active = True
                                # world.add_message_to_chat_log(f"Interacting with {targeted_npc.name}...") # Redundant if menu opens

                            # If no NPC targeted, fall back to other 'E' interactions
                            elif world.player.is_sitting:
                                if world.player.sitting_on_object_at == (target_x, target_y) or \
                                   world.player.sitting_on_object_at is None:
                                    world.player_attempt_stand_up()
                                else:
                                    world.add_message_to_chat_log("You need to stand up first to interact with that.")
                            else: # Not sitting, no NPC targeted by 'E', try environment interactions
                                action_taken = world.player_attempt_sit(target_x, target_y)
                                if not action_taken:
                                    action_taken = world.player_attempt_sleep(target_x, target_y)
                                    if not action_taken:
                                        world.player_attempt_chop_tree(target_x, target_y)
                                        # else: world.add_message_to_chat_log("Nothing to interact with there.")
                    
                    # --- Global Keys (processed regardless of most states, unless menu is active) ---
                    if not world.interaction_menu_active and event.sym == tcod.event.KeySym.Q: # Quit Game
                        return

if __name__ == "__main__":
    main()