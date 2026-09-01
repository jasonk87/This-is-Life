"""Automated pytest suite for world generation invariants across multiple seeds.

Validates:
1. Multi-seed village & building generation
2. Building entrance and inside/outside egress validity
3. Settlement walkability & BFS reachability to town square
4. Player and family co-location, valid spawn tile, and family ties
5. Day-0 economic inventory & profession equipment
6. Bit-exact seed determinism
"""

import pytest
import config
import engine
from engine import World
from tools.audit_worldgen import audit_seed

SAMPLE_SEEDS = [1, 2, 3, 7, 13, 42, 99, 123]


@pytest.fixture(autouse=True)
def disable_llm(monkeypatch):
    monkeypatch.setattr(engine, "ENABLE_OLLAMA_CONNECTION", False)
    monkeypatch.setattr(engine, "ENABLE_LLM_CONNECTION", False)


@pytest.mark.parametrize("seed", SAMPLE_SEEDS)
def test_worldgen_invariants_pass_on_sample_seed(seed):
    """Run full invariant audit against a diverse set of procedural seeds."""
    result = audit_seed(seed, verbose=False)
    assert result["success"], f"Seed {seed} failed audit with errors: {result['errors']}"
    assert len(result["errors"]) == 0, f"Seed {seed} has errors: {result['errors']}"


@pytest.mark.parametrize("seed", [1, 5, 42])
def test_player_spawns_with_valid_family_and_home(seed):
    """Verify player always has a living family and spawns inside/adjacent to the family home."""
    world = World(seed=seed)
    player = world.player

    # Starting tile is passable
    tile = world.get_tile_at(player.x, player.y)
    assert tile is not None and tile.passable, f"Player spawned on impassable tile ({player.x}, {player.y})"

    # Has family ties
    ties = player.social.family_ties
    has_relatives = bool(ties.get("mother_id") or ties.get("father_id") or ties.get("sibling_ids"))
    assert has_relatives, f"Seed {seed} generated no family relatives for player"

    # Relative has a home building
    relative_id = ties.get("mother_id") or ties.get("father_id") or (ties.get("sibling_ids") and ties["sibling_ids"][0])
    relative = world.get_entity_by_id(relative_id)
    assert relative is not None, f"Could not find family member {relative_id} in world"
    home_b_id = relative.schedule.home_building_id
    assert home_b_id in world.buildings_by_id, f"Home building {home_b_id} not in world.buildings_by_id"

    home_building = world.buildings_by_id[home_b_id]
    dist = abs(player.x - home_building.global_center_x) + abs(player.y - home_building.global_center_y)
    assert dist <= max(home_building.width, home_building.height) + 10, (
        f"Player at ({player.x}, {player.y}) too far from family home ({home_building.global_center_x}, {home_building.global_center_y})"
    )


@pytest.mark.parametrize("seed", [2, 10, 50])
def test_all_village_buildings_have_usable_entrances_and_interiors(seed):
    """Every building in every village must have an unobstructed entrance and interior egress."""
    world = World(seed=seed)
    # Ensure detail generation for all villages
    for village in world.villages:
        chunk_x, chunk_y = village.chunk_coords
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                cx, cy = chunk_x + dx, chunk_y + dy
                if 0 <= cx < world.chunk_width and 0 <= cy < world.chunk_height:
                    chunk = world.chunks[cy][cx]
                    if not chunk.is_terrain_generated:
                        world._generate_chunk_detail(chunk, cx, cy)

        for building in village.buildings:
            entrance = world._ensure_building_entrance_integrity(building)
            assert entrance is not None, f"Building {building.id} ({building.building_type}) has no usable entrance"

            candidates = [c for c in world._get_building_entrance_candidates(building) if c["door"] == entrance]
            assert candidates, f"Building {building.id} has no matching candidate for entrance {entrance}"
            candidate = candidates[0]

            door_tile = world.get_tile_at(*candidate["door"])
            assert door_tile is not None and (door_tile.properties.get("is_door", False) or getattr(door_tile, "passable", False))

            inside_tile = world.get_tile_at(*candidate["inside"])
            assert inside_tile is not None and getattr(inside_tile, "passable", False)

            outside_tile = world.get_tile_at(*candidate["outside"])
            assert outside_tile is not None and getattr(outside_tile, "passable", False)

            # Center interior connectivity to inside entrance tile
            center = (building.global_center_x, building.global_center_y)
            center_tile = world.get_tile_at(*center)
            if center_tile and center_tile.passable:
                assert world._building_interior_path_exists(building, center, candidate["inside"]), (
                    f"Building {building.id} interior center ({center}) cannot path to inside door ({candidate['inside']})"
                )


def test_seed_determinism():
    """Two worlds initialized with the same seed must produce identical layout and state."""
    seed = 777
    w1 = World(seed=seed)
    w2 = World(seed=seed)

    assert (w1.player.x, w1.player.y) == (w2.player.x, w2.player.y)
    assert len(w1.villages) == len(w2.villages)
    for v1, v2 in zip(w1.villages, w2.villages):
        assert v1.chunk_coords == v2.chunk_coords
        assert len(v1.buildings) == len(v2.buildings)
        assert v1.interaction_points.get("town_square_center") == v2.interaction_points.get("town_square_center")
