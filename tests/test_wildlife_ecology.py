import unittest

from engine import World, Chunk, Building, ChunkManager
from simulation.ecology import RegionalWildlifePopulation, WILDLIFE_SPECIES
from simulation.world_model import Village
from tile_types import Tile
from data.tiles import TILE_DEFINITIONS
from tests.world_cache import fresh_world


class TestWildlifeEcologyFoundation(unittest.TestCase):
    def setUp(self):
        import engine
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=321, pre_simulate=False)
        self.world.npcs = []
        self.world.village_npcs = []
        self.world.player.x = 2
        self.world.player.y = 2
        self.world.chunk_width = 1
        self.world.chunk_height = 1
        self.world.chunk_manager = ChunkManager(engine.CHUNK_SIZE, 1, 1)
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)] if (sx, sy) != (ex, ey) else []
        self.region = self.world.atlas.create_region("Test Plains", "plains")
        self.world.atlas.assign_chunk_to_region(0, 0, self.region)
        self.chunk = Chunk("plains", region_id=self.region.id)
        plains = TILE_DEFINITIONS["plains"]
        self.chunk.tiles = [
            [Tile(plains["char"], plains["color"], plains["passable"], plains["name"], properties={}) for _ in range(engine.CHUNK_SIZE)]
            for _ in range(engine.CHUNK_SIZE)
        ]
        self.chunk.is_terrain_generated = True
        self.chunk.allow_wildlife_population = True
        self.world.chunks = [[self.chunk]]

    def _only_species(self, species_key: str, count: int = 40) -> RegionalWildlifePopulation:
        populations = self.world.ecology.get_region_populations(self.world, self.region.id)
        for key, population in populations.items():
            population.population_count = 0
        population = populations[species_key]
        population.population_count = count
        population.carrying_capacity = max(population.carrying_capacity, count)
        population.visible_entity_ids.clear()
        population.refresh_pressure()
        return population

    def test_regional_wildlife_population_creation(self):
        populations = self.world.ecology.get_region_populations(self.world, self.region.id)

        for species_key in ["deer", "rabbit", "turkey", "wolf"]:
            self.assertIn(species_key, populations)
            self.assertGreater(populations[species_key].population_count, 0)
            self.assertGreater(populations[species_key].carrying_capacity, 0)
            self.assertTrue(populations[species_key].preferred_biomes)
            self.assertIn(species_key, WILDLIFE_SPECIES)

    def test_visible_wildlife_manifested_from_population(self):
        population = self._only_species("deer", count=45)

        self.world._populate_chunk_wildlife(self.chunk, 0, 0)

        deer = [animal for animal in self.world.npcs if getattr(animal, "animal_type", None) == "deer"]
        self.assertGreater(len(deer), 0)
        self.assertLessEqual(len(deer), self.world.ecology.target_visible_count(population))
        self.assertTrue(all(animal.wildlife_region_id == self.region.id for animal in deer))
        self.assertEqual(population.population_count, 45)

    def test_terrain_preference_filters_manifestation_tiles(self):
        import engine
        road = TILE_DEFINITIONS["road"]
        grass = TILE_DEFINITIONS["tall_grass"]
        self.chunk.tiles = [
            [Tile(road["char"], road["color"], road["passable"], road["name"], properties={}) for _ in range(engine.CHUNK_SIZE)]
            for _ in range(engine.CHUNK_SIZE)
        ]
        self.chunk.tiles[20][20] = Tile(grass["char"], grass["color"], grass["passable"], grass["name"], properties={})
        self._only_species("deer", count=30)

        self.world._populate_chunk_wildlife(self.chunk, 0, 0)

        deer = [animal for animal in self.world.npcs if getattr(animal, "animal_type", None) == "deer"]
        self.assertEqual(len(deer), 1)
        self.assertEqual((deer[0].x, deer[0].y), (20, 20))

    def test_wildlife_avoids_dense_settlement_core(self):
        village = Village(region_id=self.region.id)
        building = Building(18, 18, 6, 6, building_type="house", category="residential")
        village.add_building(building)
        village.interaction_points["town_square_center"] = [(25, 25)]
        self.chunk.village = village
        self._only_species("rabbit", count=80)

        self.world._populate_chunk_wildlife(self.chunk, 0, 0)

        rabbits = [animal for animal in self.world.npcs if getattr(animal, "animal_type", None) == "rabbit"]
        self.assertGreater(len(rabbits), 0)
        for rabbit in rabbits:
            self.assertGreater(abs(rabbit.x - building.global_center_x) + abs(rabbit.y - building.global_center_y), 8)
            self.assertGreater(abs(rabbit.x - 25) + abs(rabbit.y - 25), 8)

    def test_regional_population_reduces_when_manifested_animal_dies(self):
        population = self._only_species("deer", count=20)
        self.world._populate_chunk_wildlife(self.chunk, 0, 0)
        deer = next(animal for animal in self.world.npcs if getattr(animal, "animal_type", None) == "deer")
        before = population.population_count

        deer.physical.is_dead = True
        self.world.handle_npc_death(deer, killer_id=self.world.player.id)

        self.assertEqual(population.population_count, before - 1)
        self.assertTrue(deer.ecology_death_recorded)

    def test_abstract_recovery_repopulates_without_visible_spawn(self):
        population = self._only_species("turkey", count=3)
        population.carrying_capacity = 20
        before_visible = len(self.world.npcs)
        self.world.game_time = 1000

        self.world.ecology.process_tick(self.world)

        self.assertGreater(population.population_count, 3)
        self.assertEqual(len(self.world.npcs), before_visible)

    def test_wildlife_persists_and_does_not_infinitely_spawn_while_nearby(self):
        self._only_species("rabbit", count=100)
        self.world._populate_chunk_wildlife(self.chunk, 0, 0)
        first_ids = {animal.id for animal in self.world.npcs if getattr(animal, "animal_type", None) == "rabbit"}

        self.world._populate_chunk_wildlife(self.chunk, 0, 0)
        second_ids = {animal.id for animal in self.world.npcs if getattr(animal, "animal_type", None) == "rabbit"}

        self.assertEqual(first_ids, second_ids)
        self.assertLessEqual(len(second_ids), WILDLIFE_SPECIES["rabbit"]["max_visible_per_region"])

    def test_flee_behavior_sets_visible_activity_and_fear_state(self):
        self._only_species("deer", count=30)
        self.world._manifest_wildlife_entity("deer", 5, 5, self.region.id, f"{self.region.id}:deer")
        deer = self.world.npcs[-1]
        self.world.player.x = 6
        self.world.player.y = 5

        self.assertTrue(deer.ai_brain.take_turn(deer, self.world))

        self.assertEqual(deer.schedule.current_task, "fleeing")
        self.assertEqual(deer.current_sub_task, "Fleeing")
        self.assertEqual(deer.fear_state, "startled")
        self.assertGreater(deer.stress, 0)

    def test_offscreen_population_changes_remain_abstract_until_chunk_manifestation(self):
        population = self._only_species("wolf", count=12)
        self.world.game_time = 1000
        self.world.ecology.process_tick(self.world)

        self.assertEqual(len(self.world.npcs), 0)
        self.assertGreaterEqual(population.population_count, 12)

        self.world._populate_chunk_wildlife(self.chunk, 0, 0)
        self.assertGreater(len([animal for animal in self.world.npcs if getattr(animal, "animal_type", None) == "wolf"]), 0)


if __name__ == "__main__":
    unittest.main()
