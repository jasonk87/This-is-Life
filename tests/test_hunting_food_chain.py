import unittest

from engine import World, NPC, Building, Chunk, ChunkManager
from simulation.world_model import Village
from tile_types import Tile
from data.tiles import TILE_DEFINITIONS
from tests.world_cache import fresh_world
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini


class TestHuntingFoodChainFoundation(unittest.TestCase):
    def setUp(self):
        import engine
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=444, pre_simulate=False)
        self.world.npcs = []
        self.world.village_npcs = []
        self.world.player.x = 1
        self.world.player.y = 1
        self.world.chunk_width = 1
        self.world.chunk_height = 1
        self.world.chunk_manager = ChunkManager(engine.CHUNK_SIZE, 1, 1)
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)] if (sx, sy) != (ex, ey) else []
        self.region = self.world.atlas.create_region("Hunting Grounds", "plains")
        self.world.atlas.assign_chunk_to_region(0, 0, self.region)
        self.village = Village(region_id=self.region.id, chunk_coords=(0, 0))
        self.village.interaction_points = {"town_square_center": [(8, 8)]}
        self.chunk = Chunk("plains", region_id=self.region.id)
        plains = TILE_DEFINITIONS["plains"]
        self.chunk.tiles = [
            [Tile(plains["char"], plains["color"], plains["passable"], plains["name"], properties={}) for _ in range(engine.CHUNK_SIZE)]
            for _ in range(engine.CHUNK_SIZE)
        ]
        self.chunk.village = self.village
        self.chunk.is_terrain_generated = True
        self.chunk.allow_wildlife_population = True
        self.world.chunks = [[self.chunk]]
        self.world.atlas.add_village(self.village, chunk_coords=(0, 0), region=self.region)
        self.butcher_shop = Building(4, 4, 6, 6, building_type="butcher_shop", category="food_workplace")
        self.village.add_building(self.butcher_shop)
        self.world.buildings_by_id[self.butcher_shop.id] = self.butcher_shop
        self.hunter = NPC(10, 10, name="Hunter")
        self.hunter.economic.profession = "Hunter"
        self.hunter.schedule.work_building_id = self.butcher_shop.id
        self.world.village_npcs.append(self.hunter)
        populations = self.world.ecology.get_region_populations(self.world, self.region.id)
        for species_key, population in populations.items():
            if species_key != "deer":
                population.population_count = 0
                population.refresh_pressure()
        self.population = populations["deer"]
        self.population.population_count = 20
        self.population.carrying_capacity = 30
        self.population.refresh_pressure()

    def _spawn_deer(self, x=12, y=10):
        deer = self.world._manifest_wildlife_entity("deer", x, y, self.region.id, f"{self.region.id}:deer")
        self.population.visible_entity_ids.add(deer.id)
        return deer

    def test_hunter_selects_reachable_prey(self):
        unreachable = self._spawn_deer(15, 15)
        reachable = self._spawn_deer(12, 10)

        def path(sx, sy, ex, ey):
            if (ex, ey) == (unreachable.x, unreachable.y):
                return []
            return [(sx, sy), (ex, ey)] if (sx, sy) != (ex, ey) else []

        self.world.calculate_path = path
        selected = self.world._find_reachable_hunting_prey(self.hunter, search_radius=20)

        self.assertIs(selected, reachable)

    def test_active_hunt_reduces_population_and_creates_carcass_and_meat(self):
        deer = self._spawn_deer(11, 10)
        before = self.population.population_count

        self.assertTrue(self.world._assign_hunting_task_to_npc(self.hunter))
        self.assertTrue(self.world._handle_npc_hunting_task(self.hunter))

        self.assertTrue(deer.physical.is_dead)
        self.assertEqual(self.population.population_count, before - 1)
        self.assertEqual(self.world.get_tile_at(deer.x, deer.y).name, "Animal Corpse")
        self.assertGreater(self.hunter.economic.npc_inventory.get("raw_venison", 0), 0)
        self.assertEqual(self.world.items_on_map.get((deer.x, deer.y), {}).get("raw_venison", 0), 0)

    def test_hunter_hauls_meat_back_to_butcher_storage(self):
        self._spawn_deer(11, 10)
        self.assertTrue(self.world._assign_hunting_task_to_npc(self.hunter))
        self.assertTrue(self.world._handle_npc_hunting_task(self.hunter))
        self.hunter.x = self.butcher_shop.global_center_x
        self.hunter.y = self.butcher_shop.global_center_y
        self.hunter.schedule.current_path = []

        self.assertTrue(self.world._handle_npc_hunting_task(self.hunter))

        self.assertEqual(self.hunter.economic.npc_inventory.get("raw_venison", 0), 0)
        self.assertGreater(self.butcher_shop.building_inventory.get("processed_meat", 0), 0)

    def test_butcher_receiving_meat_improves_food_pressure(self):
        self.village.demand["food"] = 3
        self.butcher_shop.building_inventory.add_item("raw_meat", 1)

        processed = self.world._process_butcher_workplace(self.butcher_shop)
        self.world._refresh_village_food_pressure(self.village)

        self.assertEqual(processed, 1)
        self.assertEqual(self.butcher_shop.building_inventory.get("processed_meat", 0), 1)
        self.assertLess(self.village.demand.get("food", 0), 3)

    def test_wildlife_scarcity_prevents_magical_hunting_success(self):
        self.population.population_count = 0
        self.population.refresh_pressure()
        self._spawn_deer(11, 10)

        self.assertFalse(self.world._assign_hunting_task_to_npc(self.hunter))
        self.assertEqual(self.hunter.economic.npc_inventory.get("raw_venison", 0), 0)

    def test_hunter_roams_farther_when_nearby_wildlife_pressure_drops(self):
        self.population.population_count = 1
        self.population.carrying_capacity = 30
        self.population.refresh_pressure()

        self.assertGreaterEqual(self.world._get_hunter_search_radius(self.hunter), 100)

    def test_offscreen_abstract_hunting_respects_ecology_population(self):
        before = self.population.population_count

        produced = self.world._process_offscreen_hunting_for_village(self.village, [self.hunter])

        self.assertEqual(produced, 1)
        self.assertEqual(self.population.population_count, before - 1)
        self.assertGreater(self.village.supply.get("raw_venison", 0), 0)

    def test_offscreen_hunting_does_not_generate_food_without_population(self):
        self.population.population_count = 0
        self.population.refresh_pressure()

        produced = self.world._process_offscreen_hunting_for_village(self.village, [self.hunter])

        self.assertEqual(produced, 0)
        self.assertEqual(self.village.supply.get("raw_venison", 0), 0)
        self.assertGreater(self.village.demand.get("food", 0), 0)


if __name__ == "__main__":
    unittest.main()
