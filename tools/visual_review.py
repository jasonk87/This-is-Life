"""Reproducible captures and an isolated playable preview of the real renderer.

Run from the project root. Output is ignored by git; the preview never loads or
writes a save and disables remote dialogue. Close its window to finish.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine
import main as game
import tcod
from rendering.console_renderer import draw
from tools.capture_ui_font_check import _save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/visual-review")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Present 60 native frames, then close without saving")
    args = parser.parse_args()
    engine.ENABLE_LLM_CONNECTION = False
    engine.ENABLE_OLLAMA_CONNECTION = False
    world = engine.World(seed=123, player_first_name="Mara")
    world._pre_simulate_world()
    world.is_paused = True
    game._ensure_zoom_state(world)
    world.mouse_x = world.mouse_y = -1
    console = game.create_console()
    tileset = game.load_custom_tileset()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    console.clear()
    game.draw_main_menu(console, ["New Game", "Load Game", "Exit"], 0)
    _save(console, tileset, str(out / "title.png"))
    for state, key in (("PLAYING",None),("INVENTORY_MENU","U"),("INFO_MENU","I"),
                       ("CRAFTING_MENU","C"),("BUILDING_MENU","B"),("HELP_MENU","SLASH")):
        world.game_state = "PLAYING"
        if key:
            game.handle_playing_input(SimpleNamespace(sym=getattr(tcod.event.KeySym,key)),world,None)
        draw(console, world, *game._get_camera_origin(world))
        _save(console, tileset, str(out / f"{state.lower()}.png"))
    world.game_state = "PLAYING"
    for zoom in (0, 1, 2, 3):
        world.zoom_index = zoom
        draw(console, world, *game._get_camera_origin(world))
        _save(console, tileset, str(out / f"zoom-{zoom+1}.png"))
    world.zoom_index = 2
    console.clear()
    game.draw_character_create(console,"Mara")
    _save(console,tileset,str(out/"character-create.png"))
    # Explicit visual fixtures exercise populated menus without touching saves.
    inventory = world.player.economic.inventory
    for key,count in (("bread",3),("raw_log",12),("stone_chunk",8),("medicinal_herb",4),("torch",2)):
        inventory[key] = count
    world.game_state = "INVENTORY_MENU"
    draw(console,world,*game._get_camera_origin(world))
    _save(console,tileset,str(out/"inventory-populated.png"))
    world.game_state = "DIALOGUE"
    world.chat_ui_target_npc = next(iter(world.village_npcs),None)
    world.chat_ui_history = [("Player","How are things in the village?"),
                             (getattr(world.chat_ui_target_npc,"name","Someone"),
                              "The fields need tending and there is timber waiting by the workshop.")]
    world.chat_ui_input_line = "Tell me about your work, and where the village needs help. " * 3
    draw(console,world,*game._get_camera_origin(world))
    _save(console,tileset,str(out/"dialogue.png"))
    world.chat_ui_active = False
    world.game_state = "PLAYING"
    origin = (world.player.x,world.player.y)
    roads = []
    for dy in range(-24,25):
        for dx in range(-24,25):
            tile = world.get_tile_at(origin[0]+dx,origin[1]+dy)
            if tile and tile.name == "Road":
                roads.append((abs(dx)+abs(dy),origin[0]+dx,origin[1]+dy))
    if roads:
        _,wx,wy = min(roads)
        world._update_entity_position(world.player,wx,wy)
        world.player.render_x,world.player.render_y=wx,wy
        world._update_light_level_and_fov()
        world._update_player_fov()
        world.zoom_index = 1
        draw(console,world,*game._get_camera_origin(world))
        _save(console,tileset,str(out/"village.png"))
        world.weather = "rain"
        draw(console,world,*game._get_camera_origin(world))
        _save(console,tileset,str(out/"rain.png"))
        world.weather = "clear"
    print(f"Captured to {out.resolve()}", flush=True)
    if args.live or args.smoke:
        with tcod.context.new(columns=console.width, rows=console.height,
                              tileset=tileset, title="This is Life - Visual Preview",
                              vsync=True) as context:
            if args.smoke:
                from time import perf_counter
                started = perf_counter()
                for frame in range(60):
                    for event in tcod.event.get():
                        if isinstance(event, tcod.event.Quit):
                            return
                    draw(console,world,*game._get_camera_origin(world))
                    context.present(console)
                print(f"Native smoke: 60 frames in {perf_counter()-started:.2f}s",flush=True)
                return
            with patch.object(game,"save_game",lambda *_:None):
                game.start_game(context, console, world)


if __name__ == "__main__":
    main()
