"""Real seeded interior captures; no loaded saves, remote dialogue or saved changes."""

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine
import main as game
from rendering.console_renderer import draw
from tools.capture_ui_font_check import _save


def stand_inside(world, building):
    occupied = {(a.x, a.y) for a in world.village_npcs}
    candidates = []
    for y in range(building.global_origin_y + 1, building.global_origin_y + building.height - 1):
        for x in range(building.global_origin_x + 1, building.global_origin_x + building.width - 1):
            tile = world.get_tile_at(x, y)
            if tile and tile.passable and "Floor" in tile.name and (x, y) not in occupied:
                distance = abs(x - building.global_center_x) + abs(y - building.global_center_y)
                candidates.append((distance, x, y))
    if not candidates:
        raise RuntimeError(f"No free floor in {building.building_type}")
    _, x, y = min(candidates)
    world._update_entity_position(world.player, x, y)
    world.player.render_x, world.player.render_y = x, y
    world._update_light_level_and_fov()
    world._update_player_fov()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/interiors-final")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    engine.ENABLE_LLM_CONNECTION = False
    engine.ENABLE_OLLAMA_CONNECTION = False
    world = engine.World(seed=123, player_first_name="Mara")
    world._pre_simulate_world()
    world.is_paused = True
    world.mouse_x = world.mouse_y = -1
    world.game_state = "PLAYING"
    game._ensure_zoom_state(world)
    console, tileset = game.create_console(), game.load_custom_tileset()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for kind in ("house", "tavern", "blacksmith_shop", "bakery", "library", "general_store"):
        building = next(b for b in world.buildings_by_id.values() if b.building_type == kind)
        stand_inside(world, building)
        for zoom in (2, 3):
            world.zoom_index = zoom
            draw(console, world, *game._get_camera_origin(world))
            _save(console, tileset, str(out / f"{kind}-zoom{zoom+1}.png"))
        print(f"{kind}: player at {world.player.x}, {world.player.y}; normal FOV", flush=True)
    if args.smoke:
        import tcod
        from time import perf_counter

        with tcod.context.new(
            columns=console.width,
            rows=console.height,
            tileset=tileset,
            title="This is Life - Interior smoke",
            vsync=True,
        ) as context:
            start = perf_counter()
            for _ in range(60):
                for event in tcod.event.get():
                    if isinstance(event, tcod.event.Quit):
                        return
                draw(console, world, *game._get_camera_origin(world))
                context.present(console)
            print(f"Native interior smoke: 60 frames in {perf_counter()-start:.2f}s", flush=True)
    print(f"Captured to {out.resolve()}", flush=True)


if __name__ == "__main__":
    main()
