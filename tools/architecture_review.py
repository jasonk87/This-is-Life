"""Compare real seeded streets, plus explicitly labeled closed-roof fixtures."""

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine
import main as game
from rendering import console_renderer as cr, pixel_scene as pixels, village_art as village
from tools.capture_ui_font_check import _save
from tools.street_review import stand_outside

KINDS = (
    "house",
    "tavern",
    "bakery",
    "blacksmith_shop",
    "general_store",
    "library",
    "clinic",
    "sheriff_office",
    "capital_hall",
    "lumber_mill",
    "mill",
    "jail",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/architecture-final")
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
    console, tiles = game.create_console(), game.load_custom_tileset()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        building = next(b for b in world.buildings_by_id.values() if b.building_type == kind)
        position = stand_outside(world, building)
        world.zoom_index = 2
        cr.draw(console, world, *game._get_camera_origin(world))
        _save(console, tiles, str(out / f"street-{kind}.png"))
        if kind == "house":
            from rendering.building_frontage import sign_mount

            camera_x, camera_y = game._get_camera_origin(world)
            mount = sign_mount(building)
            if mount is not None:
                world.mouse_x = (mount[0] - camera_x) * 3 + 1
                world.mouse_y = (mount[1] - camera_y) * 3 + 1
                cr.draw(console, world, camera_x, camera_y)
                _save(console, tiles, str(out / "property-inspection.png"))
                world.mouse_x = world.mouse_y = -1
                world._ui_field_observation = (None, [])
        print(
            f"{kind}: real entrance {building.interaction_points['entrance']}; player {position}",
            flush=True,
        )
    # Direct roof-surface review, not a claim to see through closed doors.
    for page in range(3):
        console.clear(bg=(24, 33, 29))
        pixels.begin_frame()
        console.print(2, 1, "BUILDING SILHOUETTES / CONTROLLED ROOF REVIEW", fg=(230, 211, 160))
        console.print(2, 2, "Source geometry, not a recorded village scene.", fg=(151, 170, 160))
        for index, kind in enumerate(KINDS[page * 4 : page * 4 + 4]):
            bx = 3 + (index % 2) * 38
            by = 6 + (index // 2) * 21
            console.print(bx, by, kind.replace("_", " ").upper(), fg=(220, 192, 127))
            source = village.roof_surface(kind, 7, 6, (3, 5))
            source = pixels.scaled(source, 336, 288, token=("roof-review-zoom3", kind))
            pixels.stamp(console, source, bx * 16, (by + 2) * 16, token=("roof-review", kind))
        _save(console, tiles, str(out / f"roof-sheet-{page+1}.png"))
    if args.smoke:
        import tcod
        from time import perf_counter

        with tcod.context.new(
            columns=console.width,
            rows=console.height,
            tileset=tiles,
            title="This is Life - architecture review",
            vsync=True,
        ) as context:
            start = perf_counter()
            for _ in range(60):
                for event in tcod.event.get():
                    if isinstance(event, tcod.event.Quit):
                        return
                cr.draw(console, world, *game._get_camera_origin(world))
                context.present(console)
            print(
                f"Native architecture smoke: 60 frames in {perf_counter()-start:.2f}s", flush=True
            )
    print(out.resolve())


if __name__ == "__main__":
    main()
