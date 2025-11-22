import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from engine import World, Event, NPC, Animal
from entities.base import DireWolf
from config import NPC_SCHEDULE_UPDATE_INTERVAL, WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE

class TestKnowledgeTravel(unittest.TestCase):
    def setUp(self):
        # Patch WorldGenerator to avoid noise generation which might be slow or inconsistent
        with patch('engine.WorldGenerator') as MockGenerator:
            MockGenerator.return_value.get_biome_at.return_value = "plains"
            MockGenerator.return_value.get_poi_at.return_value = None

            # Patch the chunk initialization to avoid complex world gen logic
            with patch.object(World, '_initialize_chunks') as mock_init_chunks:
                # Create a grid of mock chunks matching world dimensions
                mock_chunks = [[MagicMock() for _ in range(WORLD_WIDTH // CHUNK_SIZE)] for _ in range(WORLD_HEIGHT // CHUNK_SIZE)]
                for row in mock_chunks:
                    for chunk in row:
                        chunk.is_generated = True # Assume generated
                        chunk.is_terrain_generated = True # Assume terrain generated
                        chunk.village = None
                        chunk.biome = "plains"

                        # Create tiles with real dictionary properties to avoid MagicMock issues in .get()
                        tiles = []
                        for _ in range(CHUNK_SIZE):
                            row_tiles = []
                            for _ in range(CHUNK_SIZE):
                                tile = MagicMock()
                                tile.passable = True
                                tile.properties = {} # Real dict
                                tile.name = "Plains"
                                row_tiles.append(tile)
                            tiles.append(row_tiles)
                        chunk.tiles = tiles

                mock_init_chunks.return_value = mock_chunks

                self.world = World(seed=1)

        # Setup simplified FOV for testing
        self.world.transparency_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), True)
        self.world.current_fov_radius = 50 # Large radius for testing

    def test_broadcast_news(self):
        # Create speaker and listener
        speaker = NPC(10, 10, name="Town Crier")
        listener_near = NPC(15, 10, name="Villager Near") # Dist 5
        listener_far = NPC(50, 50, name="Villager Far")   # Dist far

        self.world.village_npcs.extend([speaker, listener_near, listener_far])

        # Create an event
        event = Event("test_event", "Something happened!", speaker.id, self.world.game_time)

        # Broadcast
        self.world.broadcast_news(speaker, 20, event)

        # Check knowledge
        self.assertIn(event.id, listener_near.knowledge.known_events)
        self.assertNotIn(event.id, listener_far.knowledge.known_events)

    def test_hunter_warning(self):
        # Create Hunter
        hunter = NPC(10, 10, name="Hunter Bob")
        hunter.economic.profession = "Hunter"
        self.world.village_npcs.append(hunter)

        # Create Threat (Wolves) - Using Animal class
        wolf1 = Animal(15, 10, name="Wolf 1", animal_type="wolf")
        wolf2 = Animal(16, 10, name="Wolf 2", animal_type="wolf")
        self.world.npcs.extend([wolf1, wolf2])

        # Initialize FOV maps for the test
        hunter.id = 1
        # Use correct shape (H, W) for order='C' (which matches our refactor)
        # Note: If refactor to order='C' is done, indexing should be [y, x]
        self.world.npc_fov_maps[hunter.id] = np.full((WORLD_HEIGHT, WORLD_WIDTH), True)

        # Advance time to trigger schedule update
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL + 1

        # Mock _update_npc_fov to avoid re-calculating and overwriting our simple map
        with patch.object(self.world, '_update_npc_fov'):
            self.world._update_npc_schedules()

        self.assertTrue(hunter.is_frightened)
        self.assertIn(wolf1.id, hunter.threat_source_ids)

        # Check if event was logged
        threat_events = [e for e in self.world.global_events if e.type == "threat_detected"]
        self.assertTrue(len(threat_events) > 0)
        self.assertEqual(threat_events[0].subject_id, hunter.id)

if __name__ == '__main__':
    unittest.main()
