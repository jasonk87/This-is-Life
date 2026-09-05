"""Settlement Survival Simulation Tool.

Simulates an active village over multiple in-game days in a headless environment,
verifying that NPCs survive autonomously through honest daily routines:
eating, drinking from wells/taverns, working shifts, sleeping, and staying warm.

Usage:
    python tools/simulate_settlement_survival.py --ticks 1000 --seed 1
    python tools/simulate_settlement_survival.py --ticks 1500 --seeds 1,2,3 --verbose
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config
import engine
from engine import World
from simulation.systems.tick import run_world_tick


def simulate_village_survival(seed: int, ticks_to_run: int = 1000, verbose: bool = False) -> dict[str, Any]:
    """Run an active village through multi-cycle autonomous simulation using run_world_tick."""
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False

    start_time = time.perf_counter()

    world = World(seed=seed)
    if not world.villages:
        return {"seed": seed, "success": False, "error": "No villages generated"}

    # Target the player's starting village
    target_village = world._get_village_for_npc(world.player) or world.villages[0]
    chunk_x, chunk_y = target_village.chunk_coords

    # Detail generate the village chunk and its 3x3 surrounding wilderness
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            cx, cy = chunk_x + dx, chunk_y + dy
            if 0 <= cx < world.chunk_width and 0 <= cy < world.chunk_height:
                chunk = world.chunks[cy][cx]
                if not chunk.is_terrain_generated:
                    world._generate_chunk_detail(chunk, cx, cy)

    # Gather villagers belonging to this village
    villagers = [npc for npc in world.village_npcs if world._get_village_for_npc(npc) == target_village]
    if not villagers:
        villagers = list(world.village_npcs)

    initial_npc_count = len(villagers)
    if initial_npc_count == 0:
        return {"seed": seed, "success": False, "error": "0 villagers in village"}

    # Track metrics
    stats = {
        "seed": seed,
        "ticks_run": ticks_to_run,
        "initial_villagers": initial_npc_count,
        "surviving_villagers": initial_npc_count,
        "deaths": 0,
        "death_causes": collections.Counter(),
        "eating_events": 0,
        "drinking_events": 0,
        "work_actions": 0,
        "sleeping_events": 0,
        "average_final_hunger": 0.0,
        "average_final_thirst": 0.0,
        "max_final_hunger": 0,
        "max_final_thirst": 0,
        # Attrition, which deaths alone cannot show over a short run.
        #
        # This function defaults to 1000 ticks and the suite calls it with 300 -
        # half a game hour. Environmental damage lands once every 576 ticks, so
        # no villager can lose even one point of health in that window, let
        # alone die. That is how a settled thermal bug that took a village from
        # 116 alive to 16 in two simulated days passed a test whose whole
        # purpose was to assert that nobody dies.
        #
        # Thermal distress is the leading indicator and it appears within about
        # 120 ticks, so a 300-tick run can see it clearly even though it can
        # never see the death it leads to.
        "thermal_distress": 0,
        "health_lost": 0,
        "success": True,
        "errors": [],
    }

    starting_health = {
        npc.id: getattr(npc.combat, "hp", 0) for npc in villagers
    }

    # Simulation loop
    for tick in range(1, ticks_to_run + 1):
        prev_states = {
            npc.id: (npc.physical.hunger, npc.physical.thirst, npc.schedule.current_task)
            for npc in villagers
            if getattr(npc.combat, "hp", 1) > 0
        }

        # Run official simulation tick
        run_world_tick(world)

        # Detect actions performed
        for npc in villagers:
            if getattr(npc.combat, "hp", 1) <= 0:
                continue

            if npc.id in prev_states:
                prev_h, prev_t, prev_task = prev_states[npc.id]
                if npc.physical.hunger < prev_h:
                    stats["eating_events"] += 1
                if npc.physical.thirst < prev_t:
                    stats["drinking_events"] += 1
                if str(npc.schedule.current_task).lower() in {"working", "hauling", "chopping", "farming", "smithing", "selling"}:
                    stats["work_actions"] += 1
                if str(npc.schedule.current_task).lower() == "sleeping":
                    stats["sleeping_events"] += 1

    # End of simulation evaluation
    alive_villagers = [n for n in villagers if getattr(n.combat, "hp", 1) > 0]
    stats["surviving_villagers"] = len(alive_villagers)
    stats["survival_rate"] = len(alive_villagers) / initial_npc_count
    stats["deaths"] = initial_npc_count - len(alive_villagers)

    if alive_villagers:
        stats["average_final_hunger"] = round(sum(n.physical.hunger for n in alive_villagers) / len(alive_villagers), 1)
        stats["average_final_thirst"] = round(sum(n.physical.thirst for n in alive_villagers) / len(alive_villagers), 1)
        stats["max_final_hunger"] = max(n.physical.hunger for n in alive_villagers)
        stats["max_final_thirst"] = max(n.physical.thirst for n in alive_villagers)

    stats["thermal_distress"] = sum(
        1 for npc in alive_villagers
        if "Freezing" in npc.physical.status_effects
        or "Overheating" in npc.physical.status_effects
    )
    stats["health_lost"] = sum(
        max(0, starting_health.get(npc.id, 0) - getattr(npc.combat, "hp", 0))
        for npc in alive_villagers
    )
    stats["season"] = world.seasons[world.current_season_index]

    if stats["deaths"] > 0:
        stats["success"] = False
        stats["errors"].append(f"{stats['deaths']} villagers died during {ticks_to_run} ticks of simulation")

    stats["duration_seconds"] = round(time.perf_counter() - start_time, 2)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Simulate village survival over multiple simulation cycles.")
    parser.add_argument("--ticks", type=int, default=1000, help="Number of ticks to simulate (default: 1000)")
    parser.add_argument("--seeds", type=str, default="1", help="Comma-separated seed list (default: 1)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose reporting")
    args = parser.parse_args()

    seed_list = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]

    print(f"\n=======================================================")
    print(f"   SETTLEMENT AUTONOMOUS SURVIVAL SIMULATION          ")
    print(f"=======================================================")
    print(f"Simulating {len(seed_list)} seed(s) for {args.ticks} ticks each...\n")

    for idx, seed in enumerate(seed_list, 1):
        res = simulate_village_survival(seed, ticks_to_run=args.ticks, verbose=args.verbose)
        status = "PASS" if res["success"] else "FAIL"

        print(f" [{idx:02d}/{len(seed_list):02d}] Seed {seed:<5} -> {status} "
              f"({res['duration_seconds']}s | {res['surviving_villagers']}/{res['initial_villagers']} survived "
              f"[{res.get('survival_rate', 0):.0%}] | Meals: {res['eating_events']} | Drinks: {res['drinking_events']} | "
              f"Avg Hunger: {res['average_final_hunger']}/100 | Avg Thirst: {res['average_final_thirst']}/100)")

        if not res["success"]:
            for err in res["errors"]:
                print(f"       ERROR: {err}")

    print(f"\nSimulation complete.\n")


if __name__ == "__main__":
    main()
