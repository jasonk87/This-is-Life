"""Integration tests for Day-0 settlement viability and autonomous NPC survival."""

import pytest
import engine
from engine import World
from simulation.systems.tick import run_world_tick
from tools.simulate_settlement_survival import simulate_village_survival


@pytest.fixture(autouse=True)
def disable_llm():
    """Ensure LLM connections are disabled for fast headless deterministic testing."""
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False


def test_settlement_day0_stocking_invariants():
    """Verify that village buildings and residents are seeded with honest starter provisions and tools."""
    world = World(seed=42)
    assert len(world.villages) > 0

    target_village = world._get_village_for_npc(world.player) or world.villages[0]
    chunk_x, chunk_y = target_village.chunk_coords

    # Generate chunk detail
    chunk = world.chunks[chunk_y][chunk_x]
    if not chunk.is_terrain_generated:
        world._generate_chunk_detail(chunk, chunk_x, chunk_y)

    building_types = {b.building_type: b for b in target_village.buildings}

    # Verify commercial food workplaces have inventory and funds
    if "tavern" in building_types:
        tavern = building_types["tavern"]
        assert tavern.building_inventory.get("money", 0) >= 100
        food_count = sum(tavern.building_inventory.get(k, 0) for k in ["bread", "cooked_meat", "stew", "apple"])
        assert food_count > 0, "Tavern must have starter food"

    if "bakery" in building_types:
        bakery = building_types["bakery"]
        assert bakery.building_inventory.get("money", 0) >= 50
        assert bakery.building_inventory.get("flour", 0) > 0
        assert bakery.building_inventory.get("bread", 0) > 0

    if "general_store" in building_types:
        store = building_types["general_store"]
        assert store.building_inventory.get("money", 0) >= 100
        assert store.building_inventory.get("axe_stone", 0) > 0

    # Verify villagers have starter pocket money and subsistence supplies
    villagers = [npc for npc in world.village_npcs if world._get_village_for_npc(npc) == target_village]
    assert len(villagers) >= 5, "Village must have residents"

    for npc in villagers:
        assert npc.economic.money > 0, f"Villager {npc.name} should start with pocket money"
        # At least one subsistence item (bread, apple, or water)
        personal_provisions = sum(npc.economic.npc_inventory.get(k, 0) for k in ["bread", "apple", "smoked_meat", "water_flask"])
        assert personal_provisions > 0, f"Villager {npc.name} should have personal starter provisions"

        # Production roles have their essential tools
        if npc.economic.profession in ["Blacksmith", "Woodcutter", "Lumber Mill Foreman"]:
            assert npc.economic.npc_inventory.get("axe_stone", 0) > 0 or npc.equipment.weapon == "axe_stone"
        elif npc.economic.profession in ["Farmer", "Cowherd"]:
            assert npc.economic.npc_inventory.get("knife_stone", 0) > 0 or npc.equipment.weapon == "knife_stone"
        elif npc.economic.profession in ["Miner"]:
            assert npc.economic.npc_inventory.get("stone_pickaxe", 0) > 0 or npc.equipment.weapon == "stone_pickaxe"
        elif npc.economic.profession in ["Hunter"]:
            assert npc.economic.npc_inventory.get("short_bow", 0) > 0 or npc.equipment.weapon == "short_bow"


@pytest.mark.parametrize("seed", [1, 2, 7])
def test_settlement_autonomous_survival(seed: int):
    """Verify that an active settlement survives autonomously without starvation deaths."""
    result = simulate_village_survival(seed=seed, ticks_to_run=300, verbose=False)

    assert result["success"] is True, f"Simulation failed on seed {seed}: {result.get('errors')}"
    assert result["surviving_villagers"] == result["initial_villagers"], f"Villager died on seed {seed}"
    assert result["survival_rate"] == 1.0
    assert result["average_final_hunger"] <= 50.0
    assert result["average_final_thirst"] <= 50.0
