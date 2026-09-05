"""Unit tests for organic conversational living, domestic cooperation, and authentic outlaws without artificial quests."""

import pytest
import engine
from engine import World, NPC
from tests.world_cache import fresh_world


@pytest.fixture(autouse=True)
def disable_llm():
    """Ensure LLM connections are disabled for fast deterministic tests."""
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False


def test_conversational_family_domestic_needs():
    """Verify family members talk about real household needs like low pantry food."""
    world = fresh_world(seed=55, pre_simulate=False)
    player = world.player

    mother_id = player.social.family_ties.get("mother_id")
    if not mother_id:
        # Create a mock mother NPC living with player
        mother = NPC(player.x, player.y, name="Mother", dialogue=["Hello dear."])
        world.npcs.append(mother)
        mother_id = mother.id
        player.social.family_ties["mother_id"] = mother_id
        mother.social.family_ties["children_ids"] = [player.id]

    mother = world.get_entity_by_id(mother_id)
    assert mother is not None

    # Empty the home building pantry
    home_b_id = getattr(mother.schedule, "home_building_id", None)
    if home_b_id and home_b_id in world.buildings_by_id:
        home_b = world.buildings_by_id[home_b_id]
        home_b.building_inventory = {"money": 10}

    greeting = world._fallback_dialogue_greeting(mother)
    assert "pantry" in greeting.lower() or "bread" in greeting.lower() or "fed" in greeting.lower()


def test_conversational_workplace_wage_labor():
    """Verify player can ask craftsmen for work and receive honest wages without quests."""
    world = fresh_world(seed=55, pre_simulate=False)
    player = world.player

    # Create a blacksmith NPC
    smith = NPC(player.x + 1, player.y, name="Master Smith", personality="stoic")
    world._set_entity_profession(smith, "Blacksmith", reason="test")
    smith.economic.daily_wage = 30
    world.npcs.append(smith)

    initial_money = player.economic.money
    response_text, goal = world._fallback_dialogue_continue(smith, "Do you have any work for me?")
    assert player.economic.money > initial_money
    assert "share of coins" in response_text.lower() or "help" in response_text.lower()


def test_conversational_sharing_provisions():
    """Verify player can hand food/firewood to an NPC via conversation."""
    world = fresh_world(seed=55, pre_simulate=False)
    player = world.player

    neighbor = NPC(player.x + 1, player.y, name="Old Neighbor", personality="kind")
    world.npcs.append(neighbor)

    player.add_item("bread", 2)
    response_text, goal = world._fallback_dialogue_continue(neighbor, "Here is some bread for you.")
    assert "thank you" in response_text.lower()
    assert neighbor.economic.npc_inventory.get("bread", 0) >= 1
    assert player.economic.inventory.get("bread", 0) == 1


def test_outlaw_campsite_generation():
    """Verify authentic outlaw camps generate with real NPCs, campfires, and chests."""
    world = fresh_world(seed=77, pre_simulate=False)

    # Find an outlaw camp chunk or generate one directly
    outlaw_camp_chunk = None
    camp_coords = None
    for y in range(world.chunk_height):
        for x in range(world.chunk_width):
            chunk = world.chunks[y][x]
            if chunk.poi_type == "outlaw_camp":
                outlaw_camp_chunk = chunk
                camp_coords = (x, y)
                break
        if outlaw_camp_chunk:
            break

    if not outlaw_camp_chunk:
        # Pick any non-village, non-ruin chunk
        for y in range(world.chunk_height):
            for x in range(world.chunk_width):
                chunk = world.chunks[y][x]
                if not chunk.village and not chunk.ruin:
                    chunk.poi_type = "outlaw_camp"
                    outlaw_camp_chunk = chunk
                    camp_coords = (x, y)
                    break
            if outlaw_camp_chunk:
                break

    assert outlaw_camp_chunk is not None
    cx, cy = camp_coords
    world._generate_chunk_detail(outlaw_camp_chunk, cx, cy)

    # Verify campfire exists
    has_fire = any(tile.properties.get("workstation_type") == "fire" for row in outlaw_camp_chunk.tiles for tile in row)
    assert has_fire is True

    # Verify chest exists
    has_chest = any(tile.properties.get("is_container") is True for row in outlaw_camp_chunk.tiles for tile in row)
    assert has_chest is True

    # Verify outlaw NPC spawned
    outlaws = [npc for npc in world.npcs if getattr(getattr(npc, "economic", None), "profession", "") == "Outlaw"]
    assert len(outlaws) >= 1
    assert outlaws[0].attitude_to_player == "unfriendly"
    assert outlaws[0].economic.npc_inventory.get("smoked_meat", 0) > 0
