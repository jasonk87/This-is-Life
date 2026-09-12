"""Capture actual streets and explicit activity fixtures without touching saves.

Run `python tools/street_review.py`. Street images use the seeded world's real
entrances and normal FOV. Activity sheets are labeled stand-in states, not a
claim that these events happened during the paused village capture.
"""

from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import engine
import main as game
from config import DAY_LENGTH_TICKS
from rendering import people_art, pixel_scene
from rendering.console_renderer import draw
from tools.capture_ui_font_check import _save


def stand_outside(world, building):
    bx, by = building.global_origin_x, building.global_origin_y
    ex, ey = building.interaction_points["entrance"]
    dx = -1 if ex == bx else 1 if ex == bx + building.width - 1 else 0
    dy = -1 if ey == by else 1 if ey == by + building.height - 1 else 0
    occupied = {(a.x, a.y) for a in world.village_npcs}
    candidates = [(ex + dx, ey + dy)]
    candidates += [(ex + x, ey + y) for y in range(-3, 4) for x in range(-3, 4)]
    for x, y in candidates:
        tile = world.get_tile_at(x, y)
        if (
            tile is not None
            and tile.passable
            and (x, y) not in occupied
            and not building.contains_global_coords(x, y)
        ):
            world._update_entity_position(world.player, x, y)
            world.player.render_x, world.player.render_y = x, y
            world._update_light_level_and_fov()
            world._update_player_fov()
            return x, y
    raise RuntimeError(f"No unoccupied exterior tile near {building.id}")


def activity_actor(kind):
    actor = NS(
        id="fixture",
        gender="male",
        age=32,
        x=0,
        y=0,
        physical=NS(is_dead=False),
        economic=NS(profession="Blacksmith", npc_inventory={}),
        equipment=None,
        schedule=NS(current_path=[], current_task="idle"),
        task_context_data={},
        task_timer=0,
    )
    world = NS(
        player=actor,
        zoom_levels=(3,),
        zoom_index=0,
        game_time=0,
        active_ambient_speech=[],
        current_light_level_name="DAY",
    )
    if kind in {"chop", "hammer"}:
        actor.schedule.active_interaction_id = "work"
        world.interaction_resolver = NS(
            active_interactions={
                "work": NS(
                    actor_id=actor.id,
                    remaining_work=10,
                    target_pos=(1, 0),
                    animation_cue="chop_tree" if kind == "chop" else "forge_hammer",
                )
            }
        )
    elif kind == "prepare":
        actor.economic.profession = "Baker"
        actor.task_timer = 10
        actor.current_sub_task = "bake_bread"
    elif kind == "carry":
        actor.schedule.current_task = "hauling_to_stockpile"
        actor.task_context_data = {"item_key": "raw_log"}
        actor.economic.npc_inventory = {"raw_log": 2}
    elif kind == "eat":
        actor.schedule.current_task = "eating"
        actor.task_timer = 10
    elif kind == "sleep":
        actor.is_sleeping = True
    elif kind == "talk":
        world.active_ambient_speech = [NS(speaker_id=actor.id, created_tick=0, expires_tick=20)]
    return world, actor


def capture_activity_sheet(console, tileset, out, name, kinds):
    console.clear(bg=(24, 33, 29))
    pixel_scene.begin_frame()
    console.print(2, 1, "ACTIVITY CUES / CONTROLLED RENDER FIXTURES", fg=(230, 211, 160))
    console.print(
        2, 2, "Explicit test states; these are not recorded village events.", fg=(151, 170, 160)
    )
    for row, kind in enumerate(kinds):
        for phase in range(4):
            world, actor = activity_actor(kind)
            world.game_time = phase * 2
            col, top = 10 + phase * 17, 5 + row * 11
            console.print(col - 3, top, f"{kind.upper()} {phase+1}", fg=(199, 185, 141))
            people_art.draw_person(console, world, actor, 0, 0, col / 3, top / 3 + 2)
    _save(console, tileset, str(out / f"activity-{name}.png"))


def main():
    engine.ENABLE_LLM_CONNECTION = False
    engine.ENABLE_OLLAMA_CONNECTION = False
    world = engine.World(seed=123, player_first_name="Mara")
    world._pre_simulate_world()
    world.is_paused = True
    world.mouse_x = world.mouse_y = -1
    game._ensure_zoom_state(world)
    console, tileset = game.create_console(), game.load_custom_tileset()
    out = Path("artifacts/world32-streets")
    out.mkdir(parents=True, exist_ok=True)
    world.game_state = "PLAYING"
    for kind in ("bakery", "blacksmith_shop", "tavern", "house"):
        building = next(b for b in world.buildings_by_id.values() if b.building_type == kind)
        position = stand_outside(world, building)
        world.zoom_index = 2
        for style in ("legacy", "village32"):
            world.world_art_style = style
            draw(console, world, *game._get_camera_origin(world))
            _save(console, tileset, str(out / f"{kind}-{style}.png"))
        print(
            f"{kind}: real entrance {building.interaction_points['entrance']}, player {position}",
            flush=True,
        )
    # Lighting-only presentation fixture: real daylight geometry, normal
    # recomputed night FOV, and the existing time/season lighting systems.
    world.game_time = int(DAY_LENGTH_TICKS * 23 / 24)
    world.current_season_index = world.seasons.index("Winter")
    world._update_light_level_and_fov()
    world._update_player_fov()
    draw(console, world, *game._get_camera_origin(world))
    _save(console, tileset, str(out / "winter-night.png"))
    for name, kinds in (
        ("work", ("idle", "chop", "hammer", "prepare")),
        ("life", ("carry", "eat", "sleep", "talk")),
    ):
        capture_activity_sheet(console, tileset, out, name, kinds)
    print(f"Captured to {out.resolve()}", flush=True)


if __name__ == "__main__":
    main()
