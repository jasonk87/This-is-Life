import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from engine import World, NPC, Animal
from config import NPC_SCHEDULE_UPDATE_INTERVAL, WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from tile_types import Tile
import config

class TestHuntToTable(unittest.TestCase):
    def setUp(self):
        config.ENABLE_OLLAMA_CONNECTION = False
        # Patch WorldGenerator and chunk init
        with patch('engine.WorldGenerator') as MockGenerator:
            MockGenerator.return_value.get_biome_at.return_value = "plains"
            MockGenerator.return_value.get_poi_at.return_value = None

            with patch.object(World, '_initialize_chunks') as mock_init_chunks:
                mock_chunks = [[MagicMock() for _ in range(WORLD_WIDTH // CHUNK_SIZE)] for _ in range(WORLD_HEIGHT // CHUNK_SIZE)]
                for row in mock_chunks:
                    for chunk in row:
                        chunk.is_generated = True
                        chunk.is_terrain_generated = True
                        chunk.village = None
                        chunk.biome = "plains"
                        chunk.tiles = [[MagicMock(passable=True, properties={}, name="Plains") for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]
                mock_init_chunks.return_value = mock_chunks
                self.world = World(seed=1)

        self.world.transparency_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), True, order="C")
        self.world.current_fov_radius = 50

    def test_player_cooking(self):
        player = self.world.player
        # 1. Give player raw meat
        player.add_item("raw_meat", 1)
        self.assertTrue(player.has_item("raw_meat"))

        # 2. Place a fire
        fire_x, fire_y = player.x + 1, player.y
        chunk_x, chunk_y = fire_x // CHUNK_SIZE, fire_y // CHUNK_SIZE
        local_x, local_y = fire_x % CHUNK_SIZE, fire_y % CHUNK_SIZE

        fire_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_tile = Tile(fire_def['char'], fire_def['color'], fire_def['passable'], fire_def['name'], fire_def['properties'])
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = fire_tile

        # 3. Attempt cook
        self.world.player_attempt_cook(fire_x, fire_y)

        # 4. Check inventory
        self.assertFalse(player.has_item("raw_meat"))
        self.assertTrue(player.has_item("cooked_meat"))

    def test_hunter_butchering(self):
        # 1. Create Hunter and set profession
        hunter = NPC(10, 10, name="Hunter Dan")
        hunter.economic.profession = "Hunter"
        self.world.village_npcs.append(hunter)

        # 2. Create Corpse
        corpse_x, corpse_y = 12, 10
        chunk_x, chunk_y = corpse_x // CHUNK_SIZE, corpse_y // CHUNK_SIZE
        local_x, local_y = corpse_x % CHUNK_SIZE, corpse_y % CHUNK_SIZE

        corpse_def = DECORATION_ITEM_DEFINITIONS["corpse_animal"]
        props = corpse_def['properties'].copy()
        props['animal_type'] = 'deer' # Assuming deer exists and has drops
        corpse_tile = Tile(corpse_def['char'], corpse_def['color'], corpse_def['passable'], corpse_def['name'], props)
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = corpse_tile

        # 3. Force update schedules - Hunter should find corpse
        # Mock schedule so we can force the butchering task
        hunter.schedule.work_building_id = "dummy_lodge" # Needs a work building to trigger work logic

        # We need to mock the finding logic or just assert it works.
        # Let's manually set the task to verify the execution logic first.
        hunter.current_sub_task = "butcher_carcass"
        hunter.sub_task_target_coords = (corpse_x, corpse_y)
        hunter.x, hunter.y = corpse_x, corpse_y # Teleport to target
        hunter.sub_task_timer = 1 # 1 tick left

        # 4. Run work sub task handler
        # Mock get_sub_task_data to return valid data
        with patch('engine.get_sub_task_data') as mock_get_data:
            mock_get_data.return_value = {
                "id": "butcher_carcass", "display_name": "Butchering", "duration_ticks": 100,
                "target_zone_tag": "corpse", "action_verb": "butchering"
            }
            # We also need a dummy building for the Hunter
            from engine import Building
            dummy_lodge = Building(0, 0, 5, 5, "Hunter's Lodge", "workplace")
            dummy_lodge.id = "dummy_lodge"
            self.world.buildings_by_id["dummy_lodge"] = dummy_lodge

            # Execute
            self.world._handle_npc_work_sub_tasks(hunter)

            # 5. Verify corpse removed and items added
            new_tile = self.world.get_tile_at(corpse_x, corpse_y)

        # _handle_npc_work_sub_tasks does logic, then decrements.
        # If timer > 0, it won't complete.
        # We set timer to 1. It decrements to 0.
        # The logic block for completion runs IF npc.sub_task_timer <= 0 in the *next* call or at the top?

        # Actually, the `_handle_npc_work_sub_tasks` logic for completion checks:
        # if npc.current_sub_task and npc.sub_task_timer <= 0 and ...
        # So if we set it to 1, the loop runs, decrements to 0. The *next* call handles completion.
        # Let's run it one more time.

        self.world._handle_npc_work_sub_tasks(hunter)

        new_tile = self.world.get_tile_at(corpse_x, corpse_y)
        self.assertEqual(new_tile.name, "Bones")
        self.assertTrue(hunter.has_item("raw_venison") or hunter.has_item("animal_pelt")) # Deer drops these

if __name__ == '__main__':
    unittest.main()
