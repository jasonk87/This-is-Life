"""Unit tests for proximity eavesdropping, acoustic falloff, and smart controls."""

import pytest
import engine
from engine import World, NPC, Tile
from presentation.ambient_speech import (
    AmbientSpeechLine,
    format_ambient_speech_for_player,
    add_ambient_speech,
    visible_ambient_speech_lines,
)
from simulation.systems.tick import emit_environmental_sensory_cues
from main import execute_smart_interaction


@pytest.fixture(autouse=True)
def disable_llm():
    """Ensure LLM connections are disabled for fast deterministic tests."""
    engine.ENABLE_OLLAMA_CONNECTION = False
    engine.ENABLE_LLM_CONNECTION = False


def test_acoustic_eavesdropping_falloff():
    """Verify acoustic clarity depends on distance to speaker."""
    world = World(seed=42)
    player = world.player

    # Close speech (within 3 paces)
    close_line = AmbientSpeechLine(
        speech_id="s1",
        speaker_id=1,
        text="We are running out of flour at the bakery!",
        audible_radius=9,
        position=(player.x + 2, player.y),
        scene_type="market_concern",
    )
    close_formatted = format_ambient_speech_for_player(close_line, player)
    assert "running out of flour" in close_formatted

    # Far speech (8 paces away) -> muffled murmurs
    far_line = AmbientSpeechLine(
        speech_id="s2",
        speaker_id=2,
        text="Secret plotting against the sheriff",
        audible_radius=9,
        position=(player.x + 8, player.y),
        scene_type="market_concern",
    )
    far_formatted = format_ambient_speech_for_player(far_line, player)
    assert "chatter" in far_formatted.lower() or "murmurs" in far_formatted.lower() or "..." in far_formatted


def test_smart_interaction_workstations():
    """Verify smart interaction works on grinding stones and baking ovens."""
    world = World(seed=42)
    player = world.player
    from config import CHUNK_SIZE

    def set_tile(x, y, name, properties=None):
        cx, cy = x // CHUNK_SIZE, y // CHUNK_SIZE
        lx, ly = x % CHUNK_SIZE, y % CHUNK_SIZE
        chunk = world.chunks[cy][cx]
        if not chunk.tiles:
            world._generate_chunk_detail(chunk, cx, cy)
        tile = Tile(ord("."), (200, 200, 200), True, name, properties=properties or {})
        chunk.tiles[ly][lx] = tile
        return tile

    # 1. Grinding Stone
    fx, fy = player.x + 1, player.y
    player.state.last_dx, player.state.last_dy = 1, 0
    set_tile(fx, fy, "Grinding Stone", {"workstation_type": "grinding_stone"})
    player.add_item("wheat", 2)
    initial_flour = player.economic.inventory.get("flour", 0)
    executed = execute_smart_interaction(world, None)
    assert executed is True
    assert player.economic.inventory.get("flour", 0) == initial_flour + 1

    # 2. Baking Oven
    set_tile(fx, fy, "Baking Oven", {"workstation_type": "oven", "heat_source": True})
    initial_bread = player.economic.inventory.get("bread", 0)
    executed_bake = execute_smart_interaction(world, None)
    assert executed_bake is True
    assert player.economic.inventory.get("bread", 0) == initial_bread + 1


def test_environmental_sensory_cues_emission():
    """Verify nearby ovens/forges/fires produce natural sensory atmosphere messages."""
    world = World(seed=42)
    player = world.player
    from config import CHUNK_SIZE

    cx, cy = player.x // CHUNK_SIZE, player.y // CHUNK_SIZE
    lx, ly = player.x % CHUNK_SIZE, player.y % CHUNK_SIZE
    chunk = world.chunks[cy][cx]
    if not chunk.tiles:
        world._generate_chunk_detail(chunk, cx, cy)

    # Place an oven nearby
    tile = Tile(ord("O"), (200, 100, 50), True, "Stone Oven", properties={"workstation_type": "oven", "heat_source": True})
    chunk.tiles[min(CHUNK_SIZE - 1, ly + 1)][lx] = tile

    world.game_time = 80
    initial_entries = len(world.chat_log_entries)
    emit_environmental_sensory_cues(world)
    assert len(world.chat_log_entries) > initial_entries
    latest_msg = world.chat_log_entries[-1].text
    assert "bread" in latest_msg.lower() or "aroma" in latest_msg.lower()
