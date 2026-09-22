"""Reproducible, LLM-free measurements; macro mode is NOT a full gameplay soak."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
from simulation.systems.tick import run_world_tick


def snapshot(world):
    rows = []
    for village in world.villages:
        physical = Counter()
        for building in village.buildings:
            physical.update({k:q for k,q in building.building_inventory.items() if k != "money" and q > 0})
        people = world._get_settlement_residents(village)
        rows.append(dict(name=village.name, population=len(people), cache=village.population_cache,
            buildings=len(village.buildings), needs=sum(n.settlement_id == village.id for n in world.town_board.economic_needs),
            physical_mismatches={k:[village.supply.get(k,0), physical[k]] for k in set(physical)|set(village.supply)
                                 if village.supply.get(k,0) != physical[k]},
            negative_stacks=sum(q<0 for b in village.buildings for q in b.building_inventory.values()),
            hungry=sum(n.physical.hunger>=90 for n in people),
            foreign_job_knowledge=sum(any(m.event_type == "job_opportunity" and m.metadata.get("settlement_id") != village.id
                for m in n.knowledge.known_memories.values()) for n in people)))
    return rows


def run(seed, mode, days, ticks, output):
    engine.ENABLE_LLM_CONNECTION = engine.ENABLE_OLLAMA_CONNECTION = False
    world = engine.World(seed=seed, player_first_name="Observer")
    world._pre_simulate_world()
    initial = snapshot(world)
    start_tick = world.game_time
    initial_buildings = set(world.buildings_by_id)
    migrations, samples = [], []
    original = world.record_migration_event
    def record(**kwargs):
        result = original(**kwargs)
        actor = kwargs["npc"]
        migrations.append(dict(tick=world.game_time, id=actor.id, kind=kwargs["migration_kind"],
            group=list(actor.travel.group_member_ids), home=actor.schedule.home_building_id,
            work=actor.schedule.work_building_id, status=actor.travel.status))
        return result
    world.record_migration_event = record
    started = time.perf_counter()
    steps = ticks if mode == "runtime" else days*24
    for step in range(1, steps+1):
        if mode == "runtime":
            run_world_tick(world)
        else:
            # Same relative dispatch order, with only hourly calls. No forced
            # outcomes/stock/people; per-tick movement/survival/spoilage omitted.
            world.game_time = start_tick + step*(engine.DAY_LENGTH_TICKS//24)
            world._update_season()
            world._refresh_chunk_activity()
            world.process_abstract_simulation()
            world.process_macro_daily_tick()
            world._update_economy()
            world._run_daily_governance()
            world._update_npc_ages()
            world._update_npc_careers()
            world._update_abstract_simulation()
        interval = 600 if mode == "runtime" else 24
        if step % interval == 0 or step == steps:
            samples.append(dict(tick=world.game_time, villages=snapshot(world)))
            print(json.dumps(dict(seed=seed,mode=mode,step=step,of=steps,
                stages=dict(Counter(m["kind"] for m in migrations)),
                buildings=len(world.buildings_by_id)-len(initial_buildings))), flush=True)
    result = dict(seed=seed,mode=mode,steps=steps,elapsed=round(time.perf_counter()-started,2),
        elapsed_ticks=world.game_time-start_tick,initial=initial,final=snapshot(world),samples=samples,migrations=migrations,
        new_buildings=[dict(type=b.building_type, settlement=b.settlement_id,
            staff=sum(n.schedule.work_building_id == b.id and not n.physical.is_dead for n in world.village_npcs))
            for b in world.buildings_by_id.values() if b.id not in initial_buildings],
        traveling=[dict(id=n.id,leader=n.travel.group_leader_id,status=n.travel.status,
                        elapsed=world.game_time-n.travel.departed_tick)
                   for n in world.village_npcs if n.travel.is_traveling])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,indent=2), encoding="utf-8")
    print(json.dumps(dict(output=str(output),elapsed=result["elapsed"],stages=dict(Counter(m["kind"] for m in migrations)))),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=["runtime","macro"],default="runtime")
    parser.add_argument("--seed",type=int,default=451)
    parser.add_argument("--days",type=int,default=30)
    parser.add_argument("--ticks",type=int,default=2400)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    run(args.seed,args.mode,args.days,args.ticks,args.output)
