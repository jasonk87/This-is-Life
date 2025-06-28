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
                    if event.sym == tcod.event.KeySym.I:
                        world.game_state = "INFO_MENU" if world.game_state == "PLAYING" else "PLAYING"
                    
                    if world.game_state == "PLAYING":
                        if event.sym in move_keys:
                            dx, dy = move_keys[event.sym]
                            world.handle_player_movement(dx, dy)
                        elif event.sym == tcod.event.KeySym.C:
                            world.craft_item("healing_salve")
                        elif event.sym == tcod.event.KeySym.H:
                            world.use_item("healing_salve")
                        elif event.sym == tcod.event.KeySym.D:
                            world.player.take_damage(5)
                            # world.add_message_to_chat_log(f"You took 5 damage! Current HP: {world.player.hp}") # Better to use chat log
                            print(f"You took 5 damage! Current HP: {world.player.hp}")
                        elif event.sym == tcod.event.KeySym.T:
                            world.talk_to_npc()
                        # --- Reputation Debug Keys ---
                        elif event.sym == tcod.event.KeySym.K: # 'K' for Kriminal
                            world.player.adjust_reputation(REP_CRIMINAL, 10)
                            world.add_message_to_chat_log(f"Criminal points +10. Total: {world.player.reputation[REP_CRIMINAL]}")
                        elif event.sym == tcod.event.KeySym.J: # 'J' for Justice/Hero
                            world.player.adjust_reputation(REP_HERO, 10)
                            world.add_message_to_chat_log(f"Hero points +10. Total: {world.player.reputation[REP_HERO]}")
                        elif event.sym == tcod.event.KeySym.E: # 'E' to interact / use / chop
                            # Target tile player is facing
                            target_x = world.player.x + world.player.last_dx
                            target_x = world.player.x + world.player.last_dx
                            target_y = world.player.y + world.player.last_dy

                            if world.player.is_sitting:
                                # If sitting, 'E' on the same spot (or any 'E') makes you stand.
                                # More precisely, if trying to interact with the chair player is on, stand up.
                                # Or, any 'E' press while sitting could mean stand. For now, let's make it specific.
                                if world.player.sitting_on_object_at == (target_x, target_y) or \
                                   world.player.sitting_on_object_at is None: # Failsafe if sitting but not on specific spot
                                    world.player_attempt_stand_up()
                                else: # Trying to interact with something else while sitting
                                    world.add_message_to_chat_log("You need to stand up first.")
                            else:
                                # Attempt to sit first
                                # player_attempt_sit returns True if it handled the action (sat or stood from same spot)
                                # or False if no sittable object was there.
                                action_taken = world.player_attempt_sit(target_x, target_y)
                                if not action_taken:
                                    # If not sitting and sit action failed, try sleeping
                                    action_taken = world.player_attempt_sleep(target_x, target_y)
                                    if not action_taken:
                                        # If sleep action failed, try chopping
                                        world.player_attempt_chop_tree(target_x, target_y)
                                        # Future: Add other 'E' interactions here
                                        # else: world.add_message_to_chat_log("Nothing to interact with there.")
                    
                    if event.sym == tcod.event.KeySym.Q: # Quit
                        return

if __name__ == "__main__":
    main()