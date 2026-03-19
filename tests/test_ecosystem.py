import unittest
from unittest.mock import MagicMock, patch
from runtime_compat import np
from engine import World, NPC, Animal
from data.animals import ANIMAL_DEFINITIONS
from data.tiles import TILE_DEFINITIONS
from config import WORLD_WIDTH, WORLD_HEIGHT, CHUNK_SIZE

class TestEcosystem(unittest.TestCase):
    def setUp(self):
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
                        chunk.tiles = [[MagicMock() for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]
                        for r in chunk.tiles:
                            for t in r:
                                t.name = "Plains"
                                t.passable = True
                                t.properties = {}
                mock_init_chunks.return_value = mock_chunks
                self.world = World(seed=1)

        self.world.transparency_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), True)

    def test_herbivore_grazing(self):
        # Setup a hungry sheep and some grass
        sheep = Animal(10, 10, name="Sheep", animal_type="sheep")
        sheep.physical.hunger = 80 # Very hungry
        self.world.npcs.append(sheep)

        grass_x, grass_y = 11, 10
        grass_chunk_x, grass_chunk_y = grass_x // CHUNK_SIZE, grass_y // CHUNK_SIZE
        grass_local_x, grass_local_y = grass_x % CHUNK_SIZE, grass_y % CHUNK_SIZE

        # Set specific tile to Tall Grass
        grass_tile = self.world.chunks[grass_chunk_y][grass_chunk_x].tiles[grass_local_y][grass_local_x]
        grass_tile.name = "Tall Grass"

        # Debug
        print(f"DEBUG: Sheep Hunger: {sheep.physical.hunger}")
        print(f"DEBUG: Sheep Diet: {ANIMAL_DEFINITIONS['sheep'].get('diet_type')}")
        print(f"DEBUG: Sheep Food: {ANIMAL_DEFINITIONS['sheep'].get('food_sources')}")
        print(f"DEBUG: Tile at {grass_x},{grass_y} name: {self.world.get_tile_at(grass_x, grass_y).name}")

        # Mock pathfinding to succeed
        # Advance time to bypass schedule throttle
        self.world.game_time = 100

        with patch.object(self.world, 'calculate_path', return_value=[(10,10), (11,10)]) as mock_path:
             self.world._update_npc_schedules()
             print(f"DEBUG: Path called? {mock_path.called}")

        print(f"DEBUG: Sheep Task: {sheep.schedule.current_task}")

        # Sheep should now be moving to graze
        self.assertEqual(sheep.schedule.current_task, "grazing")
        self.assertEqual(sheep.schedule.current_destination_coords, (11, 10))

        # Teleport sheep to grass and update again to trigger eating
        sheep.x, sheep.y = 11, 10
        self.world.game_time = 200 # Advance time again
        self.world._update_npc_schedules()

        # Check if grass was eaten (mocked tile change via _change_map_tile call interception or state check)
        # Since we mock chunks, checking _change_map_tile call is best, or checking tile name if updated in-place
        # The engine uses _change_map_tile which replaces the tile object in the array.
        # Let's check if hunger reduced.
        self.assertLess(sheep.physical.hunger, 80)
        self.assertEqual(sheep.schedule.current_task, "idle")

    def test_predator_eating_corpse(self):
        # Setup hungry wolf and a corpse
        wolf = Animal(20, 20, name="Wolf", animal_type="wolf")
        wolf.physical.hunger = 80
        # Wolf needs a target first to "lose" it, or we can manually set sub_task_target_coords
        # Logic: if prey is None and sub_task_target_coords is set, it checks for corpse.
        wolf.schedule.current_task = "hunting"
        wolf.sub_task_target_coords = (22, 22) # Fake last known loc
        self.world.npcs.append(wolf)

        corpse_x, corpse_y = 22, 22
        corpse_chunk_x, corpse_chunk_y = corpse_x // CHUNK_SIZE, corpse_y // CHUNK_SIZE
        corpse_local_x, corpse_local_y = corpse_x % CHUNK_SIZE, corpse_y % CHUNK_SIZE

        corpse_tile = self.world.chunks[corpse_chunk_y][corpse_chunk_x].tiles[corpse_local_y][corpse_local_x]
        corpse_tile.name = "Animal Corpse"

        self.world.game_time = 200 # Advance time

        with patch.object(self.world, 'calculate_path', return_value=[(20,20), (21,21), (22,22)]):
            self.world._update_npc_schedules()

        self.assertEqual(wolf.schedule.current_task, "eating_corpse")

        # Teleport and eat
        wolf.x, wolf.y = 22, 22
        self.world.game_time = 300 # Advance time again
        self.world._update_npc_schedules()

        self.assertEqual(wolf.physical.hunger, 0)
        self.assertEqual(wolf.schedule.current_task, "idle")

if __name__ == '__main__':
    unittest.main()
