from unittest.mock import MagicMock
import engine
import config
from simulation.world_model import Chunk, Village, Building
import random
import traceback
import sys

def create_mock_chunk():
    chunk = Chunk(0, 0, "forest")
    chunk.village = Village()
    return chunk

class MockWorld(engine.World):
    def __init__(self):
        pass
    def _call_llm_for_worldgen(self, prompt):
        return "{}"

world = MockWorld()
world.atlas = MagicMock()
world._populate_village_npcs = MagicMock()
world._initialize_economy = MagicMock()

chunk = create_mock_chunk()

world._generate_village_structure(chunk, 0, 0)
print(f"Num buildings: {len(chunk.village.buildings)}")
