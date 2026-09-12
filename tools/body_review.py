"""Scripted human/wolf integration fixture, captured by the native renderer.

Positions and attack aims are staged. Damage, gear, death, medicine and clocks
use production handlers. This is not evidence of spontaneous NPC behavior.
"""
from pathlib import Path
import pickle
import random

import engine
import main
from config import DAY_LENGTH_TICKS
from data.tiles import TILE_DEFINITIONS
from entities.animal import Animal
from rendering.console_renderer import draw
from simulation.systems import body_combat as combat
from tools.capture_ui_font_check import _save


def run():
    out = Path("artifacts/body-combat")
    out.mkdir(parents=True, exist_ok=True)
    world = engine.World(seed=451, player_first_name="Mara")
    world._pre_simulate_world()
    world.game_time = DAY_LENGTH_TICKS // 3
    ox, oy = next((x, y) for y in range(20, 300, 20) for x in range(20, 300, 20)
                  if all(world.get_building_at(x+dx, y+dy) is None for dx in range(8) for dy in range(8)))
    for x in range(ox, ox+8):
        for y in range(oy, oy+8):
            world.get_tile_at(x, y)
            world._change_map_tile((x, y), TILE_DEFINITIONS["plains"])
    player = world.player
    world._update_entity_position(player, ox+3, oy+4)
    player.render_x, player.render_y = player.x, player.y
    wolf = Animal(player.x+1, player.y, name="Grey Wolf", animal_type="wolf")
    world.npcs = [wolf]
    world.village_npcs = []
    world._mark_entity_positions_dirty()
    for key in ("wool_shirt", "wool_trousers", "leather_boots", "axe_stone"):
        player.add_item(key)
        world.use_item(key)
    combat.advance_bodies(world)
    random.seed(32)
    bites = 0
    while bites < 3:
        result = combat.attack(world, wolf, player, target_part="left_lower_leg")
        bites += bool(result.wound_id)
        world.game_time += 6
    swings = 0
    while not wolf.physical.is_dead and swings < 60 and combat.can_act(player):
        world.player_attempt_attack(wolf, target_part="head")
        world.game_time += 5
        swings += 1
    assert wolf.physical.is_dead, ("wolf survived", swings)
    assert not player.physical.is_dead
    identity = player.appearance.__dict__.copy()
    tiles, console = main.load_custom_tileset(), main.create_console()
    main._ensure_zoom_state(world)
    world.zoom_index = 2
    world.mouse_x = world.mouse_y = -1
    world.is_paused = True

    def capture(label, body=False):
        world.game_state = "PLAYING"
        if body:
            world.examine_body()
        world._update_light_level_and_fov()
        world._update_player_fov()
        draw(console, world, *main._get_camera_origin(world))
        console.print(2, 4, f"SCRIPTED INTEGRATION: {label}", fg=(234, 209, 158))
        _save(console, tiles, str(out / f"{label}.png"))

    capture("01-after-fight")
    capture("02-wounds", body=True)
    healer = engine.NPC(player.x, player.y+1, name="Elara")
    healer.economic.profession = "Healer"
    healer.add_item("bandage", 8)
    healer.add_item("splint", 2)
    world.village_npcs.append(healer)
    from simulation.systems.medical import update_npc_medical_state
    for _ in range(180):
        world.game_time += 1
        combat.advance_bodies(world)
        update_npc_medical_state(world, healer)
    assert all(w.dressed for w in player.combat.anatomy.wounds if w.bleeding)
    saved = pickle.dumps(world)
    world = pickle.loads(saved)
    player = world.player
    world.game_time += DAY_LENGTH_TICKS
    player.state.is_sleeping = True
    combat.advance_bodies(world)
    player.state.is_sleeping = False
    assert not player.physical.is_dead
    assert player.appearance.__dict__ == identity
    assert any(w.healing < 1 for w in player.combat.anatomy.wounds)
    capture("03-treated-next-day", body=True)
    print({"bites": bites, "swings": swings, "wounds_next_day": len(player.combat.anatomy.wounds),
           "movement": combat.functions_for(player)["movement"], "artifacts": str(out.resolve())})
    # Separate visual boundary fixture; not another event in the encounter.
    player.combat.anatomy.blood = .35
    combat.sync_body(world, player)
    capture("04-unconscious-pose-fixture")


if __name__ == "__main__":
    run()
