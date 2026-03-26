import pytest
import math
from unittest.mock import MagicMock
from engine import World
from simulation.systems.architecture import BUILDING_ARCHETYPES
from simulation.world_model import Chunk, Village, Building
from config import CHUNK_SIZE
import random

def create_mock_chunk():
    chunk = Chunk(0, 0, "forest")
    chunk.village = Village()
    return chunk

def test_building_placement_bias():
    world = object.__new__(World)
    world.atlas = MagicMock()
    world._call_llm_for_worldgen = MagicMock(return_value="{}")
    world._populate_village_npcs = MagicMock()
    world._initialize_economy = MagicMock()

    chunk = create_mock_chunk()

    # We want a deterministic seed
    random.seed(42)
    world._generate_village_structure(chunk, 0, 0)

    buildings = chunk.village.buildings

    civic_dists = []
    industrial_dists = []

    road_x = CHUNK_SIZE // 2
    road_y = CHUNK_SIZE // 2

    for b in buildings:
        dist = abs(b.x - road_x) + abs(b.y - road_y)
        if b.category in ["civic", "civic_workplace", "commercial_workplace", "medical"]:
            civic_dists.append(dist)
        elif b.category in ["industrial", "industrial_workplace"]:
            industrial_dists.append(dist)

    avg_civic_dist = sum(civic_dists) / len(civic_dists) if civic_dists else float('inf')
    avg_ind_dist = sum(industrial_dists) / len(industrial_dists) if industrial_dists else 0

    assert avg_civic_dist < avg_ind_dist, f"Civic buildings should be closer to center than industrial. Civic: {avg_civic_dist}, Industrial: {avg_ind_dist}"

def test_building_placement_determinism():
    world1 = object.__new__(World)
    world1.atlas = MagicMock()
    world1._call_llm_for_worldgen = MagicMock(return_value="{}")
    world1._populate_village_npcs = MagicMock()
    world1._initialize_economy = MagicMock()
    chunk1 = create_mock_chunk()

    world2 = object.__new__(World)
    world2.atlas = MagicMock()
    world2._call_llm_for_worldgen = MagicMock(return_value="{}")
    world2._populate_village_npcs = MagicMock()
    world2._initialize_economy = MagicMock()
    chunk2 = create_mock_chunk()

    random.seed(42)
    world1._generate_village_structure(chunk1, 0, 0)

    random.seed(42)
    world2._generate_village_structure(chunk2, 0, 0)

    assert len(chunk1.village.buildings) == len(chunk2.village.buildings)

    for i in range(len(chunk1.village.buildings)):
        b1 = chunk1.village.buildings[i]
        b2 = chunk2.village.buildings[i]
        assert b1.x == b2.x
        assert b1.y == b2.y
        assert b1.building_type == b2.building_type

def test_building_fallback():
    world = object.__new__(World)
    world.atlas = MagicMock()
    world._call_llm_for_worldgen = MagicMock(return_value="{}")
    world._populate_village_npcs = MagicMock()
    world._initialize_economy = MagicMock()
    chunk = create_mock_chunk()

    random.seed(42)
    world._generate_village_structure(chunk, 0, 0)

    assert len(chunk.village.buildings) > 0 # At least some buildings got placed
