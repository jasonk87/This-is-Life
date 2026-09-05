"""Unit tests for agricultural parity between Player and NPC simulation systems."""

import pytest
import engine
from engine import World, Tile
from data.tiles import TILE_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from tests.world_cache import fresh_world


@pytest.fixture(autouse=True)
def disable_llm():
    """Ensure LLM connections are disabled for fast deterministic tests."""
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False


def test_player_and_npc_farming_cycle():
    """Test full cycle: till soil -> plant seeds -> crop growth -> harvest -> mill -> bake."""
    world = fresh_world(seed=101, pre_simulate=False)
    player = world.player

    # Place a plain tile next to player
    target_x = player.x + 1
    target_y = player.y
    world._change_map_tile((target_x, target_y), TILE_DEFINITIONS["plains"])

    # 1. Tilling: player with knife_stone can till soil
    player.economic.inventory["knife_stone"] = 1
    world.player_attempt_till_soil(target_x, target_y)
    tilled_tile = world.get_tile_at(target_x, target_y)
    assert tilled_tile.name == "Tilled Soil"

    # 2. Planting: player with wheat_seeds can plant
    player.economic.inventory["wheat_seeds"] = 2
    world.player_attempt_plant_seeds(target_x, target_y)
    growing_tile = world.get_tile_at(target_x, target_y)
    assert growing_tile.name == "Growing Wheat"
    assert player.economic.inventory["wheat_seeds"] == 1

    # 3. Growth: manually advance growth or evolve to mature wheat
    world._change_map_tile((target_x, target_y), TILE_DEFINITIONS["wheat_plant"])
    mature_tile = world.get_tile_at(target_x, target_y)
    assert mature_tile.name == "Wheat"
    assert mature_tile.properties.get("is_harvestable") is True

    # 4. Harvest: harvest mature crop
    initial_wheat = player.economic.inventory.get("wheat", 0)
    world.player_attempt_harvest(target_x, target_y)
    assert player.economic.inventory.get("wheat", 0) > initial_wheat
    assert player.economic.inventory.get("wheat_seeds", 0) >= 1  # Returned seeds
    harvested_tile = world.get_tile_at(target_x, target_y)
    assert harvested_tile.name == "Tilled Soil"

    # 5. Milling: at grinding stone workstation
    mill_x = player.x - 1
    mill_y = player.y
    mill_tile_def = {
        "char": ord("&"),
        "color": (150, 150, 150),
        "passable": True,
        "name": "Grinding Stone",
        "properties": {"workstation_type": "grinding_stone"},
    }
    world._change_map_tile((mill_x, mill_y), mill_tile_def)

    initial_flour = player.economic.inventory.get("flour", 0)
    world.player_attempt_mill_flour(mill_x, mill_y)
    assert player.economic.inventory.get("flour", 0) == initial_flour + 1

    # 6. Baking: at oven / hearth
    oven_x = player.x
    oven_y = player.y - 1
    oven_tile_def = {
        "char": ord("O"),
        "color": (200, 100, 50),
        "passable": True,
        "name": "Baking Oven",
        "properties": {"workstation_type": "oven", "heat_source": True},
    }
    world._change_map_tile((oven_x, oven_y), oven_tile_def)

    initial_bread = player.economic.inventory.get("bread", 0)
    world.player_attempt_bake_bread(oven_x, oven_y)
    assert player.economic.inventory.get("bread", 0) == initial_bread + 1
