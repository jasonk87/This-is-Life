"""Unit tests for the hardcore sensory observation engine, look mode, and smart controls."""

import pytest
import engine
from engine import World, NPC, Tile
from presentation.sensory_observation import (
    observe_entity,
    observe_tile,
    get_tile_sensory_summary,
)
from main import execute_smart_interaction, handle_look_mode_input
from types import SimpleNamespace
from tcod_compat import tcod


@pytest.fixture(autouse=True)
def disable_llm():
    """Ensure LLM connections are disabled for fast deterministic tests."""
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False


def test_observe_npc_sensory_details():
    """Verify observe_entity generates deep, realistic sensory descriptions without shortcuts."""
    world = World(seed=42)
    player = world.player

    # Create an NPC farmer
    npc = NPC(player.x + 1, player.y, name="Cedric", personality="hardworking")
    world._set_entity_profession(npc, "Farmer", reason="test")
    npc.schedule.current_task = "tilling_soil"
    npc.equipment.weapon = "knife_stone"
    npc.equipment.body = "leather_jerkin"
    npc.economic.npc_inventory["bread"] = 2
    npc.physical.hunger = 75
    npc.physical.body_temperature = 34.5  # Chilled
    world.npcs.append(npc)

    desc = observe_entity(npc, player, world)
    assert "Cedric" in desc
    assert "Farmer" in desc
    assert "tilling the soil" in desc.lower()
    assert "knife" in desc.lower()
    assert "leather jerkin" in desc.lower()
    assert "carrying" in desc.lower()
    assert "hungry" in desc.lower()
    assert "shivering" in desc.lower() or "cold" in desc.lower()


def set_tile(world, x, y, name, passable=True, properties=None):
    from config import CHUNK_SIZE
    cx, cy = x // CHUNK_SIZE, y // CHUNK_SIZE
    lx, ly = x % CHUNK_SIZE, y % CHUNK_SIZE
    chunk = world.chunks[cy][cx]
    if not chunk.tiles:
        world._generate_chunk_detail(chunk, cx, cy)
    tile = Tile(ord("."), (200, 200, 200), passable, name, properties=properties or {})
    chunk.tiles[ly][lx] = tile
    return tile


def test_observe_tile_sensory_details():
    """Verify observe_tile describes terrain, crops, containers, and workstations."""
    world = World(seed=42)

    # 1. Growing crop tile
    set_tile(world, 10, 10, "Growing Wheat", True, {"growth_progress": 50, "growth_needed": 100})
    desc_crop = observe_tile(world, 10, 10)
    assert "50%" in desc_crop
    assert "wheat" in desc_crop.lower()

    # 2. Baking Oven workstation
    set_tile(world, 11, 10, "Stone Oven", True, {"workstation_type": "oven", "heat_source": True, "heat_source_radius": 4})
    desc_oven = observe_tile(world, 11, 10)
    assert "oven" in desc_oven.lower()
    assert "warmth" in desc_oven.lower() or "heat" in desc_oven.lower()

    # 3. Ground loot
    world.items_on_map[(12, 10)] = {"apple": 3}
    desc_ground = observe_tile(world, 12, 10)
    assert "apple" in desc_ground.lower()


def test_get_tile_sensory_summary():
    """Verify one-line summary for HUD status bar."""
    world = World(seed=42)

    # Workstation
    set_tile(world, 5, 5, "Grinding Stone", True, {"workstation_type": "grinding_stone"})
    summary = get_tile_sensory_summary(world, 5, 5)
    assert "Grinding Stone" in summary or "Milling" in summary


def test_smart_interaction_door_and_crops():
    """Verify execute_smart_interaction performs intuitive in-world action on facing tile."""
    world = World(seed=42)
    player = world.player

    # Set facing tile to closed door with valid opens_to reference
    facing_x, facing_y = player.x + 1, player.y
    player.state.last_dx, player.state.last_dy = 1, 0
    set_tile(world, facing_x, facing_y, "Wooden Door", False, {"is_door": True, "is_open": False, "opens_to": "wooden_door_open"})

    # Execute smart interaction
    result = execute_smart_interaction(world, None)
    assert result is True
    # Door should now be open / passable
    tile = world.get_tile_at(facing_x, facing_y)
    assert tile.passable is True


def test_look_mode_navigation():
    """Verify look mode moves cursor and provides sensory summaries."""
    world = World(seed=42)
    player = world.player
    world.game_state = "LOOK_MODE"
    world.look_cursor_x = player.x
    world.look_cursor_y = player.y

    # Move cursor right
    right_event = SimpleNamespace(sym=tcod.event.KeySym.RIGHT)
    handle_look_mode_input(right_event, world)
    assert world.look_cursor_x == player.x + 1

    # Exit look mode
    esc_event = SimpleNamespace(sym=tcod.event.KeySym.ESCAPE)
    handle_look_mode_input(esc_event, world)
    assert world.game_state == "PLAYING"
