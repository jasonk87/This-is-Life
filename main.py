# main.py
import tcod
import tcod.console
import tcod.event
import tcod.tileset
import os
from engine import World
from config import SCREEN_WIDTH_TILES, SCREEN_HEIGHT_TILES, WORLD_WIDTH, WORLD_HEIGHT
from data.items import ITEM_DEFINITIONS
from rendering.console_renderer import draw, draw_info_menu
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
            # --- Drawing ---
            draw(console, world)
            # Handle NPC speech
            world._handle_npc_speech()
            # Update the screen
            context.present(console)
            # --- Event Handling ---
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
                            print(f"You took 5 damage! Current HP: {world.player.hp}")
                        elif event.sym == tcod.event.KeySym.T:
                            world.talk_to_npc()
                    
                    if event.sym == tcod.event.KeySym.Q:
                        return

if __name__ == "__main__":
    main()