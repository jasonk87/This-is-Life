"""Reproducible offline travel/remote-world probes; never teleports the traveler.

Run: python -W ignore -m tools.probe_settlement_loops travel|remote
"""
import argparse
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import tcod
import engine
import main
from simulation.systems import settlements


def report(**data):
    print(json.dumps(data), flush=True)


def cardinal_path(world, start, destination, margin=30):
    x0, y0 = max(0, min(start[0], destination[0])-margin), max(0, min(start[1], destination[1])-margin)
    x1 = min(engine.WORLD_WIDTH, max(start[0], destination[0])+margin+1)
    y1 = min(engine.WORLD_HEIGHT, max(start[1], destination[1])+margin+1)
    costs = np.zeros((y1-y0, x1-x0), dtype=np.int16)
    for y in range(y0, y1):
        for x in range(x0, x1):
            tile = world.get_tile_at(x, y)
            if tile and (tile.passable or (tile.properties.get("is_door") and not tile.properties.get("is_locked"))):
                costs[y-y0, x-x0] = 1 if tile.passable else 3
    route = tcod.path.AStar(costs, diagonal=0).get_path(start[1]-y0, start[0]-x0, destination[1]-y0, destination[0]-x0)
    return [(x+x0, y+y0) for y, x in route]


def capture(world, name):
    from tools.capture_ui_font_check import _save, _new_console
    from rendering.console_renderer import draw
    out = Path("artifacts/settlement-stability")
    out.mkdir(parents=True, exist_ok=True)
    tileset = main.load_custom_tileset()
    main._ensure_zoom_state(world)
    console = _new_console()
    camera = main._get_camera_origin(world)
    draw(console, world, *camera)
    _save(console, tileset, str(out / f"{name}.png"))


def travel(seed, prepared=False):
    world = engine.World(seed=seed, player_first_name="Traveler")
    start = (world.player.x, world.player.y)
    origin = settlements.current(world)
    if prepared:
        # Explicit expedition fixture, not a claim about the starting inventory.
        for item in ("short_bow", "iron_helmet", "iron_breastplate"):
            world.player.add_item(item)
            world.use_item(item)
            assert item == world.player.equipment.weapon or item in world.player.equipment.equipped_armor.values()
        world.player.add_item("arrow", 60)
        report(probe="expedition_loadout", items=["short_bow", "iron_helmet", "iron_breastplate", "60 arrows"])
    options = sorted((v for v in settlements.villages(world) if v is not origin),
                     key=lambda v: sum(abs(a-b) for a, b in zip(world._get_village_anchor_coords(v), start)))
    for village in options:
        destination = world._get_village_anchor_coords(village)
        route = cardinal_path(world, start, destination)
        report(probe="path", seed=seed, origin=origin.name, destination=village.name, steps=len(route), coords=destination)
        if route:
            break
    assert route, "No cardinal route to another village"
    settlements.read_destination(world, village.id)
    world.is_paused = True
    world.game_state = "PLAYING"
    keys = {(0, -1): main.tcod.event.KeySym.UP, (0, 1): main.tcod.event.KeySym.DOWN,
            (-1, 0): main.tcod.event.KeySym.LEFT, (1, 0): main.tcod.event.KeySym.RIGHT}
    initial_tick = world.game_time
    for index, (x, y) in enumerate(route):
        if prepared:
            from simulation.systems.combat_response import distance, sees
            for _ in range(12):
                threats = [n for n in world.all_npcs if n.combat.is_hostile_to_player and not n.physical.is_dead
                           and distance(n,world.player) <= 12 and sees(world,world.player,n)]
                if not threats:
                    break
                target = min(threats, key=lambda n: distance(n, world.player))
                if not main.commit_player_attack(world, target):
                    break
        dx, dy = x-world.player.x, y-world.player.y
        assert (dx, dy) in keys
        tile = world.get_tile_at(x, y)
        if not tile.passable and tile.properties.get("is_door"):
            world.interaction_context.update(active=True, x=x, y=y, selected_entity_index=0,
                selected_action_index=0, target_entities=[{"type":"tile", "data":tile}], available_actions=["Toggle Door"])
            assert main.execute_interaction(world, None)
            main.advance_committed_action(world, 1)
        assert main.handle_playing_input(SimpleNamespace(sym=keys[(dx, dy)]), world, None), f"Input rejected step {index} at {(x,y)}; tile {world.get_tile_at(x,y).name}, time {world.game_time}, ready {world.player.state.move_ready_tick}; {world.chat_log[-5:]}"
        assert (world.player.x, world.player.y) == (x, y), f"Blocked at {x}, {y}: {world.chat_log[-3:]}"
        assert not world.player.physical.is_dead
        if index % 32 == 0:
            report(probe="walking", step=index+1, total=len(route), tick=world.game_time)
    assert settlements.current(world) is village
    restored = pickle.loads(pickle.dumps(world))
    assert settlements.current(restored).id == village.id
    assert village.id in restored.player.known_settlements
    report(probe="travel_complete", origin=origin.name, destination=village.name, steps=len(route),
           ticks=world.game_time-initial_tick, player_alive=True, save_load=True, prepared_loadout=prepared)
    capture(world, f"travel-arrival-{seed}")
    world.open_noticeboard_menu()
    capture(world, f"destination-notices-{seed}")


def remote(seed, days=120):
    world = engine.World(seed=seed, player_first_name="Observer")
    world._pre_simulate_world()
    villages = settlements.villages(world)
    initial_ids = {b.id for b in world.buildings_by_id.values()}
    initial = {v.id: {"name": v.name, "buildings": len(v.buildings), "people": sum(world._get_npc_settlement(n) is v for n in world.village_npcs)} for v in villages}
    declarations = set()
    negative = 0
    construction = []
    for day in range(1, days+1):
        # Advance the SAME hourly/daily entry points the real tick calls; no
        # forced relationships, buildings, staffing, inventories or outcomes.
        for hour in range(24):
            world.game_time = day*engine.DAY_LENGTH_TICKS + hour*engine.DAY_LENGTH_TICKS//24
            world.process_abstract_simulation()
            world.process_macro_daily_tick()
            world._run_daily_governance()
            world._update_npc_ages()
            world._update_abstract_simulation()
        for village in villages:
            negative += sum(q < 0 for q in village.supply.values())
            declarations.update(tuple(sorted((village.id, other))) for other in village.at_war_with)
            for building in village.buildings:
                if building.id not in initial_ids:
                    initial_ids.add(building.id)
                    construction.append((village.name, building.building_type, day, building.id))
        if day == 1 or day % 15 == 0:
            report(probe="remote_progress", day=day, wars=len(declarations), new_buildings=len(construction), negative_stock=negative)
    report(probe="remote_complete", seed=seed, days=days, initial=list(initial.values()),
           final=[{"name":v.name, "buildings":len(v.buildings), "people":sum(world._get_npc_settlement(n) is v for n in world.village_npcs), "relations":list(v.village_relationships.values())} for v in villages],
           new_buildings=[{"village":name,"type":kind,"day":day,"staff":world._count_active_workers_for_building(world.buildings_by_id[bid])} for name,kind,day,bid in construction],
           blueprints=[{"type":bp.target_build,"required":bp.required_materials,"delivered":dict(bp.delivered_materials.items()),"status":bp.status} for bp in world.blueprints_by_id.values()],
           wars=len(declarations), negative_stock=negative)
    assert negative == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("probe", choices=["travel", "remote"])
    parser.add_argument("--seed", type=int, default=451)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--prepared", action="store_true")
    args = parser.parse_args()
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    travel(args.seed, args.prepared) if args.probe == "travel" else remote(args.seed, args.days)
