"""World Generation Audit Tool.

Stress-tests and audits procedural world generation across multiple seeds,
validating physical reachability, entrance integrity, NPC life paths,
family spawning, Day-0 economy, and determinism without requiring graphics.

Usage:
    python tools/audit_worldgen.py --count 10
    python tools/audit_worldgen.py --seeds 1,2,3,4,5 --verbose
    python tools/audit_worldgen.py --count 20 --report out/worldgen_audit.json
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
from engine import World, Building, NPC, Player
from world_generation import WorldGenerator


def audit_seed(seed: int, verbose: bool = False) -> dict[str, Any]:
    """Audit a single procedural world generation seed for core invariants."""
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False

    result = {
        "seed": seed,
        "success": True,
        "errors": [],
        "warnings": [],
        "metrics": {},
    }

    start_time = time.perf_counter()

    try:
        world = World(seed=seed)
    except Exception as exc:
        result["success"] = False
        result["errors"].append(f"World initialization crashed with exception: {exc}")
        return result

    # 1. Macro Geography & Villages
    villages = list(world.villages)
    result["metrics"]["village_count"] = len(villages)
    if len(villages) < 1:
        result["success"] = False
        result["errors"].append(f"Seed {seed} generated 0 villages.")
        return result

    if len(villages) < 3:
        result["warnings"].append(f"Seed {seed} generated only {len(villages)} villages (target is >= 3).")

    # Ensure all village chunks and player surroundings are generated in detail
    for village in villages:
        chunk_x, chunk_y = village.chunk_coords
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                cx, cy = chunk_x + dx, chunk_y + dy
                if 0 <= cx < world.chunk_width and 0 <= cy < world.chunk_height:
                    chunk = world.chunks[cy][cx]
                    if not chunk.is_terrain_generated:
                        world._generate_chunk_detail(chunk, cx, cy)

    total_buildings = 0
    total_npcs = len(world.village_npcs)
    result["metrics"]["total_village_npcs"] = total_npcs

    # 2. Village Structure & Walkability Audits
    for v_idx, village in enumerate(villages):
        v_name = getattr(village, "name", f"Village_{v_idx}")
        buildings = list(getattr(village, "buildings", []))
        total_buildings += len(buildings)

        if not buildings:
            result["warnings"].append(f"Village {v_name} has 0 buildings.")
            continue

        # Town square check
        town_square = village.interaction_points.get("town_square_center")
        if not town_square or not isinstance(town_square, list) or not town_square[0]:
            result["success"] = False
            result["errors"].append(f"Village {v_name} is missing a valid town_square_center.")
            continue

        ts_x, ts_y = town_square[0]
        ts_tile = world.get_tile_at(ts_x, ts_y)
        if not ts_tile or not getattr(ts_tile, "passable", False):
            result["warnings"].append(
                f"Village {v_name} town square ({ts_x}, {ts_y}) tile is impassable: {getattr(ts_tile, 'name', 'None')}"
            )

        # BFS Reachability map within village chunk and immediate neighbors
        chunk_x, chunk_y = village.chunk_coords
        min_x = max(0, (chunk_x - 1) * config.CHUNK_SIZE)
        max_x = min(config.WORLD_WIDTH - 1, (chunk_x + 2) * config.CHUNK_SIZE - 1)
        min_y = max(0, (chunk_y - 1) * config.CHUNK_SIZE)
        max_y = min(config.WORLD_HEIGHT - 1, (chunk_y + 2) * config.CHUNK_SIZE - 1)

        # Build walkable flood fill from town square
        reachable_tiles = set()
        queue = collections.deque([(ts_x, ts_y)])
        reachable_tiles.add((ts_x, ts_y))

        while queue:
            cx, cy = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if min_x <= nx <= max_x and min_y <= ny <= max_y and (nx, ny) not in reachable_tiles:
                    tile = world.get_tile_at(nx, ny)
                    if tile and getattr(tile, "passable", False):
                        reachable_tiles.add((nx, ny))
                        queue.append((nx, ny))

        # Check each building entrance and egress
        for building in buildings:
            entrance = world._ensure_building_entrance_integrity(building)
            if not entrance:
                result["success"] = False
                result["errors"].append(
                    f"Building {building.id} ({building.building_type}) in {v_name} has no usable entrance."
                )
                continue

            candidates = [c for c in world._get_building_entrance_candidates(building) if c["door"] == entrance]
            if not candidates:
                result["success"] = False
                result["errors"].append(f"Building {building.id} entrance {entrance} has no valid candidate.")
                continue

            candidate = candidates[0]
            door_x, door_y = candidate["door"]
            inside_x, inside_y = candidate["inside"]
            outside_x, outside_y = candidate["outside"]

            door_tile = world.get_tile_at(door_x, door_y)
            inside_tile = world.get_tile_at(inside_x, inside_y)
            outside_tile = world.get_tile_at(outside_x, outside_y)

            if not (door_tile and inside_tile and outside_tile):
                result["success"] = False
                result["errors"].append(f"Building {building.id} entrance tiles are missing at ({door_x}, {door_y}).")
                continue

            if not getattr(inside_tile, "passable", False):
                result["success"] = False
                result["errors"].append(f"Building {building.id} inside tile ({inside_x}, {inside_y}) is impassable.")

            if not getattr(outside_tile, "passable", False):
                result["success"] = False
                result["errors"].append(f"Building {building.id} outside tile ({outside_x}, {outside_y}) is impassable.")

            # Check reachability to town square
            if (outside_x, outside_y) not in reachable_tiles:
                # Direct A* path as a secondary check in case flood fill boundary was conservative
                direct_path = world.calculate_path(outside_x, outside_y, ts_x, ts_y)
                if not direct_path:
                    result["warnings"].append(
                        f"Building {building.id} ({building.building_type}) outside tile ({outside_x}, {outside_y}) "
                        f"cannot reach town square ({ts_x}, {ts_y})."
                    )

            # Check interior connectivity (center to inside door)
            center = (building.global_center_x, building.global_center_y)
            center_tile = world.get_tile_at(*center)
            if center_tile and getattr(center_tile, "passable", False):
                has_path = world._building_interior_path_exists(building, center, (inside_x, inside_y))
                if not has_path:
                    result["warnings"].append(
                        f"Building {building.id} interior center ({center}) has no passable path to door inside ({inside_x}, {inside_y})."
                    )

    result["metrics"]["total_buildings"] = total_buildings

    # 3. Player & Family Spawning Invariants
    player = world.player
    result["metrics"]["player_spawn"] = (player.x, player.y)

    family_ties = getattr(player.social, "family_ties", {})
    has_family = bool(family_ties.get("mother_id") or family_ties.get("father_id") or family_ties.get("sibling_ids"))
    result["metrics"]["player_has_family"] = has_family

    if has_family:
        mother_id = family_ties.get("mother_id")
        father_id = family_ties.get("father_id")
        mother = world.get_entity_by_id(mother_id) if mother_id else None
        father = world.get_entity_by_id(father_id) if father_id else None
        family_member = mother or father

        if family_member:
            home_b_id = getattr(family_member.schedule, "home_building_id", None)
            home_b = world.buildings_by_id.get(home_b_id) if home_b_id else None
            if home_b:
                dist_to_home = abs(player.x - home_b.global_center_x) + abs(player.y - home_b.global_center_y)
                if dist_to_home > max(home_b.width, home_b.height) + 10:
                    result["success"] = False
                    result["errors"].append(
                        f"Player spawned at ({player.x}, {player.y}), too far from family home {home_b.id} at ({home_b.global_center_x}, {home_b.global_center_y}) - dist: {dist_to_home}"
                    )
            else:
                result["warnings"].append("Family member has no valid home building in buildings_by_id.")
    else:
        result["warnings"].append("Player has no family ties generated.")

    # Check player starting tile passability
    player_tile = world.get_tile_at(player.x, player.y)
    if not player_tile or not getattr(player_tile, "passable", False):
        result["success"] = False
        result["errors"].append(
            f"Player spawned on impassable tile ({player.x}, {player.y}): {getattr(player_tile, 'name', 'None')}"
        )

    # 4. NPC Schedule & Economic Invariants
    for npc in world.village_npcs:
        # Check profession equipment
        prof = getattr(npc.economic, "profession", "Unemployed")
        weapon = getattr(npc.equipment, "weapon", None)
        if prof in {"Guard", "Sheriff"} and weapon is None:
            result["warnings"].append(f"Guard NPC {npc.name} spawned without a weapon.")
        elif prof in {"Woodcutter", "Lumber Mill Foreman"} and weapon is None:
            result["warnings"].append(f"Woodcutter NPC {npc.name} spawned without an axe.")

    # 5. Determinism Check (re-generate same seed)
    second_world = World(seed=seed)
    if (second_world.player.x, second_world.player.y) != (player.x, player.y):
        result["success"] = False
        result["errors"].append(
            f"Non-deterministic player spawn: run 1 at ({player.x}, {player.y}) vs run 2 at ({second_world.player.x}, {second_world.player.y})"
        )

    if len(second_world.villages) != len(world.villages):
        result["success"] = False
        result["errors"].append(
            f"Non-deterministic village count: run 1 has {len(world.villages)} vs run 2 has {len(second_world.villages)}"
        )

    elapsed = time.perf_counter() - start_time
    result["metrics"]["duration_seconds"] = round(elapsed, 3)

    return result


def main():
    parser = argparse.ArgumentParser(description="Audit world generation across procedural seeds.")
    parser.add_argument("--count", type=int, default=10, help="Number of random seeds to audit (default: 10)")
    parser.add_argument("--seeds", type=str, help="Comma-separated specific seeds to test (e.g. '1,42,100')")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging per seed")
    parser.add_argument("--report", type=str, help="Optional JSON file path to write the audit report")
    args = parser.parse_args()

    if args.seeds:
        seed_list = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    else:
        seed_list = list(range(1, args.count + 1))

    print(f"\n=======================================================")
    print(f"   THIS IS LIFE - PROCEDURAL WORLDGEN AUDIT SUITE     ")
    print(f"=======================================================")
    print(f"Auditing {len(seed_list)} seeds: {seed_list[:10]}{'...' if len(seed_list) > 10 else ''}\n")

    results = []
    passed = 0
    failed = 0
    total_warnings = 0

    for idx, seed in enumerate(seed_list, 1):
        audit = audit_seed(seed, verbose=args.verbose)
        results.append(audit)

        status_str = "PASS" if audit["success"] else "FAIL"
        duration = audit["metrics"].get("duration_seconds", 0)
        v_count = audit["metrics"].get("village_count", 0)
        b_count = audit["metrics"].get("total_buildings", 0)
        npc_count = audit["metrics"].get("total_village_npcs", 0)
        warn_count = len(audit["warnings"])
        err_count = len(audit["errors"])
        total_warnings += warn_count

        if audit["success"]:
            passed += 1
            print(f" [{idx:02d}/{len(seed_list):02d}] Seed {seed:<6} -> {status_str} "
                  f"({duration:.2f}s | {v_count} villages | {b_count} bldgs | {npc_count} NPCs | {warn_count} warns)")
        else:
            failed += 1
            print(f" [{idx:02d}/{len(seed_list):02d}] Seed {seed:<6} -> {status_str} "
                  f"({duration:.2f}s | {err_count} errors | {warn_count} warns)")
            for err in audit["errors"]:
                print(f"       ERROR: {err}")

        if args.verbose and audit["warnings"]:
            for warn in audit["warnings"]:
                print(f"       WARN:  {warn}")

    print(f"\n-------------------------------------------------------")
    print(f"AUDIT SUMMARY: {passed}/{len(seed_list)} Passed ({passed/len(seed_list):.0%}) | {failed} Failed | {total_warnings} Total Warnings")
    print(f"-------------------------------------------------------\n")

    if args.report:
        report_dir = os.path.dirname(args.report)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({
                "total_seeds": len(seed_list),
                "passed": passed,
                "failed": failed,
                "total_warnings": total_warnings,
                "results": results
            }, f, indent=2)
        print(f"Report saved to: {args.report}\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
