"""Native occupied-furniture review, using disposable worlds and real action handlers.

The sheet and NPC bed capture are explicitly staged test states, not emergent
events. The tavern capture invokes the normal player's sit action. No save I/O.
"""

from pathlib import Path
import argparse
import copy
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine
import main as game
from data.decorations import DECORATION_ITEM_DEFINITIONS as DECOR
from data.tiles import TILE_DEFINITIONS
from rendering import console_renderer as cr, interior_art, pixel_scene as pixels, room_scene
from rendering import furniture_occupancy as occupancy
from runtime_compat import np
from simulation.systems.interaction import ActionIntent, InteractionResolver
from tools.capture_ui_font_check import _save
from tools.interior_review import stand_inside
from tools.street_review import activity_actor


def fixture_sheet(console, tiles, out):
    _, sample = activity_actor("idle")
    world = NS(
        player=NS(x=0, y=0, render_disabled=True),
        npcs=[],
        village_npcs=[],
        zoom_levels=(4,),
        zoom_index=0,
        game_time=0,
        current_light_level_name="DAY",
        player_fov_map=np.ones((40, 40), dtype=bool),
        items_on_map={},
        active_ambient_speech=[],
    )
    fixtures = {}
    floor = NS(**TILE_DEFINITIONS["wood_floor"])
    world.get_tile_at = lambda x, y: fixtures.get((x, y), floor)
    resolver = InteractionResolver()
    console.clear(bg=(23, 32, 28))
    pixels.begin_frame()
    for column, (key, gender) in enumerate(
        (
            ("wooden_chair", "male"),
            ("wooden_chair", "female"),
            ("wooden_bed", "male"),
            ("bed_simple", "female"),
        )
    ):
        for row, profession in enumerate(("Blacksmith", "Baker", "Healer")):
            x, y = 2 + column * 5, 3 + row * 3
            actor = copy.deepcopy(sample)
            actor.id = f"review-{column}-{row}"
            actor.gender = gender
            actor.economic.profession = profession
            actor.x, actor.y = x - 1, y
            actor.render_x, actor.render_y = actor.x, actor.y
            fixtures[(x, y)] = NS(**copy.deepcopy(DECOR[key]))
            world.npcs.append(actor)
            for fy in (y - 1, y):
                for fx in (x - 1, x, x + 1):
                    interior_art.draw_floor(console, world, 0, 0, fx, fy, floor, "wood_floor")
            action = "sit_on_chair" if key == "wooden_chair" else "sleep_in_bed"
            result = resolver._resolve_sit_or_sleep(
                ActionIntent(actor.id, action, target_pos=(x, y)), world, actor
            )
            assert result.success and occupancy.attachment_for(world, actor)
    room_scene.draw(console, world, 0, 0)
    console.print(3, 1, "OCCUPIED ROOMS / NATIVE RENDER FIXTURES", fg=(230, 211, 160))
    console.print(
        3, 2, "Explicit action test states, not recorded village events.", fg=(157, 172, 160)
    )
    for column, label in enumerate(("SEATED / M", "SEATED / F", "BED / M", "PALLET / F")):
        console.print(5 + column * 20, 5, label, fg=(215, 188, 125))
    for row, profession in enumerate(("BLACKSMITH", "BAKER", "HEALER")):
        for column in range(4):
            console.print(5 + column * 20, 17 + row * 12, profession, fg=(160, 171, 151))
    console.print(
        3,
        47,
        "Real chair anchor / original blankets layered over sleeping bodies",
        fg=(174, 184, 159),
    )
    _save(console, tiles, str(out / "occupied-furniture-sheet.png"))


def find_fixture(world, building, keys):
    actors = [*world.npcs, *world.village_npcs]
    occupied = {(actor.x, actor.y) for actor in actors}
    claimed = set()
    for actor in actors:
        for state in (actor, getattr(actor, "state", None)):
            anchor = getattr(state, "sitting_on_object_at", None)
            if getattr(state, "is_sitting", False) and anchor:
                claimed.add(tuple(anchor))
    for y in range(building.global_origin_y + 1, building.global_origin_y + building.height - 1):
        for x in range(building.global_origin_x + 1, building.global_origin_x + building.width - 1):
            if (x, y) not in occupied | claimed and interior_art.furniture_key(
                world.get_tile_at(x, y)
            ) in keys:
                for dx, dy in ((0, 1), (-1, 0), (1, 0), (0, -1)):
                    tile = world.get_tile_at(x + dx, y + dy)
                    if (
                        tile
                        and tile.passable
                        and "Floor" in tile.name
                        and (x + dx, y + dy) not in occupied
                    ):
                        return (x, y), (x + dx, y + dy)
    raise RuntimeError(f"No reachable {keys} in {building.building_type}")


def overlap_sheet(console, tiles, out):
    """Three static positions around real fixture art; no claimed simulation event."""
    world, sample = activity_actor("idle")
    world.player = NS(x=0, y=0, render_disabled=True)
    world.npcs, world.village_npcs, world.items_on_map = [], [], {}
    world.zoom_levels, world.zoom_index = (4,), 0
    world.player_fov_map = np.ones((40, 40), dtype=bool)
    fixtures = {}
    floor = NS(**TILE_DEFINITIONS["wood_floor"])
    world.get_tile_at = lambda x, y: fixtures.get((x, y), floor)
    console.clear(bg=(23, 32, 28))
    pixels.begin_frame()
    for row, key in enumerate(("bookshelf", "forge", "wooden_bed")):
        for column, (dx, dy) in enumerate(((0, -1), (1, 0), (0, 1))):
            x, y = 3 + column * 6, 4 + row * 3
            actor = copy.deepcopy(sample)
            actor.id = f"depth-{row}-{column}"
            actor.x, actor.y = x + dx, y + dy
            actor.render_x, actor.render_y = actor.x, actor.y
            world.npcs.append(actor)
            fixtures[(x, y)] = NS(**copy.deepcopy(DECOR[key]))
            for fy in (y - 1, y, y + 1):
                for fx in (x - 1, x, x + 1):
                    interior_art.draw_floor(console, world, 0, 0, fx, fy, floor, "wood_floor")
    room_scene.draw(console, world, 0, 0)
    console.print(3, 1, "ROOM DEPTH / NATIVE RENDER FIXTURES", fg=(230, 211, 160))
    console.print(
        3, 2, "Static test positions. Same fixtures, one shared painter order.", fg=(157, 172, 160)
    )
    for column, label in enumerate(("BEHIND", "BESIDE", "IN FRONT")):
        console.print(10 + column * 24, 5, label, fg=(215, 188, 125))
    _save(console, tiles, str(out / "furniture-depth-sheet.png"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/occupancy-final")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    console, tiles = game.create_console(), game.load_custom_tileset()
    fixture_sheet(console, tiles, out)
    overlap_sheet(console, tiles, out)
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    world = engine.World(seed=123, player_first_name="Mara")
    world._pre_simulate_world()
    world.is_paused, world.game_state = True, "PLAYING"
    world.mouse_x = world.mouse_y = -1
    game._ensure_zoom_state(world)
    world.zoom_index = 3
    tavern = next(b for b in world.buildings_by_id.values() if b.building_type == "tavern")
    chair, adjacent = find_fixture(world, tavern, {"wooden_chair"})
    world._update_entity_position(world.player, *adjacent)
    world.player.render_x, world.player.render_y = adjacent
    world._update_light_level_and_fov()
    world._update_player_fov()
    cr.draw(console, world, *game._get_camera_origin(world))
    _save(console, tiles, str(out / "tavern-before-sitting.png"))
    assert world.player_attempt_sit(*chair)
    assert occupancy.attachment_for(world, world.player)
    cr.draw(console, world, *game._get_camera_origin(world))
    _save(console, tiles, str(out / "tavern-player-seated.png"))
    world.player_attempt_stand_up()
    house = next(b for b in world.buildings_by_id.values() if b.building_type == "house")
    stand_inside(world, house)
    bed, adjacent = find_fixture(world, house, {"wooden_bed", "bed_simple"})
    actor = next(
        a
        for a in world.village_npcs
        if not getattr(a, "animal_type", None) and not a.physical.is_dead
    )
    if getattr(actor, "render_disabled", False):
        world.wake_entity(actor)
    world._update_entity_position(actor, *adjacent)
    actor.render_x, actor.render_y = adjacent
    actor.schedule.current_path = []
    result = InteractionResolver()._resolve_sit_or_sleep(
        ActionIntent(actor.id, "sleep_in_bed", target_pos=bed), world, actor
    )
    assert result.success and occupancy.attachment_for(world, actor)
    world.add_message_to_chat_log(
        "VISUAL REVIEW: NPC bed pose is an explicitly staged action test."
    )
    cr.draw(console, world, *game._get_camera_origin(world))
    _save(console, tiles, str(out / "house-bed-action-fixture.png"))
    print(f"Native action captures + fixture sheet: {out.resolve()}")


if __name__ == "__main__":
    main()
