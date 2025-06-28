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
                if isinstance(event, tcod.event.TextInput):
                    if world.chat_ui_active: # Only process text input if chat UI is active
                        world.chat_ui_input_line += event.text
                        # print(f"TextInput: '{event.text}', current line: '{world.chat_ui_input_line}'") # Debug

                elif isinstance(event, tcod.event.KeyDown):
                    # --- UI Mode: Chat UI Active ---
                    if world.chat_ui_active:
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
                            if world.chat_ui_input_line: # Process if there's input
                                player_input = world.chat_ui_input_line
                                world.chat_ui_history.append(("Player", player_input))
                                world.chat_ui_input_line = "" # Clear input line

                                if world.chat_ui_mode == "talk":
                                    if world.chat_ui_target_npc:
                                        world.continue_npc_dialogue(world.chat_ui_target_npc, player_input)
                                    else: # Should not happen if chat_ui_active and mode is talk
                                        world.add_message_to_chat_log("Error: No target NPC for dialogue continuation.")
                                elif world.chat_ui_mode == "persuade_goal_input":
                                    world.attempt_persuasion(world.chat_ui_target_npc, player_input)
                                    # Persuasion results are added to chat_ui_history by attempt_persuasion
                                    # Transition out of persuade_goal_input mode, perhaps to 'talk' or just end.
                                    # For now, let's end the interaction after persuasion attempt.
                                    context.stop_text_input()
                                    world.chat_ui_active = False
                                    world.add_message_to_chat_log(f"Persuasion attempt made with {world.chat_ui_target_npc.name}.")
                                    world.chat_ui_target_npc = None

                                # Keep chat history within limits
                                if len(world.chat_ui_history) > world.chat_ui_max_history:
                                    world.chat_ui_history = world.chat_ui_history[-world.chat_ui_max_history:]
                                world.chat_ui_scroll_offset = 0 # Reset scroll to show latest
                        # (Optional: PageUp/PageDown for scrolling history here)
                    
                    # --- UI Mode: Interaction Menu Active ---
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
                                selected_option = world.interaction_menu_options[world.interaction_menu_selected_index]
                                target_npc = world.interaction_menu_target_npc

                                world.interaction_menu_active = False # Close menu first

                                if selected_option == "Talk":
                                    if target_npc:
                                        world.chat_ui_target_npc = target_npc
                                        world.chat_ui_mode = "talk"
                                        world.start_npc_dialogue(target_npc)
                                        world.chat_ui_active = True
                                        context.start_text_input() # Start text input when chat UI activates
                                    else:
                                        world.add_message_to_chat_log("Error: No target NPC for talk.")
                                elif selected_option == "Persuade":
                                    if target_npc:
                                        world.chat_ui_target_npc = target_npc
                                        world.chat_ui_mode = "persuade_goal_input"
                                        world.chat_ui_history.clear()
                                        world.chat_ui_scroll_offset = 0
                                        world.chat_ui_input_line = ""
                                        world.chat_ui_history.append(("System", f"Persuade {target_npc.name}: What is your goal?"))
                                        world.chat_ui_active = True
                                        context.start_text_input() # Start text input
                                    else:
                                        world.add_message_to_chat_log("Error: No target NPC for persuade.")
                                elif selected_option == "Trade (Not Implemented)":
                                    world.add_message_to_chat_log("Trade system is not yet implemented.")
                                    world.interaction_menu_target_npc = None # Clear target
                                elif selected_option == "Cancel":
                                    world.add_message_to_chat_log("Interaction cancelled.")
                                    world.interaction_menu_target_npc = None # Clear target
                        elif event.sym == tcod.event.KeySym.ESCAPE:
                            world.interaction_menu_active = False
                            world.interaction_menu_target_npc = None
                            world.add_message_to_chat_log("Interaction cancelled.")

                    # --- UI Mode: Info Menu Active (or toggling it) ---
                    elif event.sym == tcod.event.KeySym.I:
                        world.game_state = "INFO_MENU" if world.game_state == "PLAYING" else "PLAYING"

                    # --- Game State: Playing (No other UI is active) ---
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
                            all_npcs = world.npcs + world.village_npcs
                            for npc_obj in all_npcs:
                                if npc_obj.x == target_x and npc_obj.y == target_y:
                                    targeted_npc = npc_obj
                                    break

                            if targeted_npc:
                                world.interaction_menu_target_npc = targeted_npc
                                world.interaction_menu_options = ["Talk", "Persuade", "Trade (Not Implemented)", "Cancel"]
                                world.interaction_menu_selected_index = 0
                                world.interaction_menu_x = console.width // 2
                                world.interaction_menu_y = console.height // 2
                                world.interaction_menu_active = True
                            elif world.player.is_sitting:
                                if world.player.sitting_on_object_at == (target_x, target_y) or \
                                   world.player.sitting_on_object_at is None:
                                    world.player_attempt_stand_up()
                                else:
                                    world.add_message_to_chat_log("You need to stand up first to interact with that.")
                            else:
                                action_taken = world.player_attempt_sit(target_x, target_y)
                                if not action_taken:
                                    action_taken = world.player_attempt_sleep(target_x, target_y)
                                    if not action_taken:
                                        world.player_attempt_chop_tree(target_x, target_y)
                        elif event.sym == tcod.event.KeySym.Q: # Quit Game
                            return

                    # Fallback Quit, if somehow missed by other states (e.g. if in INFO_MENU)
                    if event.sym == tcod.event.KeySym.Q:
                        return

if __name__ == "__main__":
    main()