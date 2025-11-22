
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine import World, Building, NPC, Player
from config import DAY_LENGTH_TICKS, CHUNK_SIZE

class TestSocialImpact(unittest.TestCase):
    def setUp(self):
        # Setup a mock world
        with patch('engine.World._initialize_chunks') as mock_init_chunks, \
             patch('engine.WORLD_WIDTH', new=CHUNK_SIZE), \
             patch('engine.WORLD_HEIGHT', new=CHUNK_SIZE), \
             patch('engine.World._spawn_traveling_merchants'): # Skip merchant spawn to avoid empty village error
            # We need to mock the chunk grid to match the dimensions calculated by World.__init__
            # If WORLD_WIDTH == CHUNK_SIZE, then chunk_width = 1
            mock_init_chunks.return_value = [[MagicMock()]] # 1x1 chunk grid
            self.world = World(seed=42)

        # Mock Ollama to avoid network calls
        self.world._call_ollama = MagicMock(return_value="{}")
        self.world.add_message_to_chat_log = MagicMock()

        # Create a workplace
        self.mill = Building(10, 10, 5, 5, "lumber_mill", global_chunk_x_start=0, global_chunk_y_start=0)
        self.world.buildings_by_id[self.mill.id] = self.mill

        # Create Boss
        self.boss = NPC(12, 12, "Bossman", personality="bossy")
        self.boss.economic.profession = "Lumber Mill Foreman"
        self.boss.schedule.work_building_id = self.mill.id
        self.world.village_npcs.append(self.boss)

        # Create Worker
        self.worker = NPC(12, 13, "Worker", personality="hardworking")
        self.worker.economic.profession = "Woodcutter"
        self.worker.schedule.work_building_id = self.mill.id
        self.world.village_npcs.append(self.worker)

        # Create Unemployed
        self.unemployed = NPC(15, 15, "Lazy", personality="lazy")
        self.unemployed.economic.profession = "Unemployed"
        self.world.village_npcs.append(self.unemployed)

    def test_firing_creates_grudge(self):
        # Setup firing condition
        self.worker.economic.work_performance = 0
        self.world.game_time = DAY_LENGTH_TICKS # Ensure daily update runs

        # Force the random firing chance to hit
        with patch('random.random', return_value=0.0):
            self.world._update_npc_careers()

        # Check results
        self.assertEqual(self.worker.economic.profession, "Unemployed")
        self.assertIn(self.boss.id, self.worker.social.grudges)
        self.assertIn("Fired me", self.worker.social.grudges[self.boss.id][0])

    def test_hiring_improves_relationship(self):
        # Hire the unemployed NPC
        self.world._assign_job(self.unemployed, self.mill)

        # Check results
        self.assertEqual(self.unemployed.economic.profession, "Woodcutter") # Or whatever _assign_job decides based on vacancies logic, but here it defaults/finds role
        # Relationship should increase
        self.assertGreater(self.unemployed.social.relationships.get(self.boss.id, 50), 50)
        self.assertGreater(self.boss.social.relationships.get(self.unemployed.id, 50), 50)

    def test_job_referral_logic(self):
        # Setup: Unemployed NPC needs a job. Player knows about the Mill.
        self.world.player.knowledge.known_locations[self.mill.id] = (self.mill.global_center_x, self.mill.global_center_y)

        # Ensure Mill has vacancy (Boss + Worker = 2, max is usually 4 for mill in gen, but let's force it)
        self.mill.max_workers = 5

        # Mock player input
        player_input = "I know of a job at the lumber mill."

        # Trigger dialogue
        self.world.continue_npc_dialogue(self.unemployed, player_input)

        # Check result: NPC should be applying
        self.assertEqual(self.unemployed.schedule.current_task, "applying_for_job")
        self.assertEqual(self.unemployed.schedule.current_destination_coords, (self.mill.global_center_x, self.mill.global_center_y))

if __name__ == '__main__':
    unittest.main()
