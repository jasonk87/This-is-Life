import unittest
from engine import World
from simulation.systems.architecture import BUILDING_ARCHETYPES, generate_building

class TestBlueprintVariants(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.world.chunk_width = 1
        self.world.chunk_height = 1
        self.world._generate_chunk_detail(self.world.chunks[0][0], 0, 0)

    def test_variant_id_persists_on_generated_buildings(self):
        blueprint = self.world.place_construction_blueprint("house", 5, 5)
        self.assertIsNotNone(blueprint.variant_id)

        # fully supply and complete
        for item, count in blueprint.required_materials.items():
            for _ in range(count):
                blueprint.deposit_item_reference(None)
        blueprint.deposited_inventory = dict(blueprint.required_materials)

        self.world._complete_construction_blueprint(blueprint)
        building = [b for b in self.world.buildings_by_id.values() if b.building_type == "house"][-1]
        self.assertEqual(building.variant_id, blueprint.variant_id)

    def test_fallback_works_when_variant_invalid(self):
        gen_building = generate_building("shack", 0, 0, 5, 5)
        self.assertEqual(gen_building.footprint, (0, 0, 5, 5))


    def test_fenced_yard_footprint_prevents_overlap(self):
        # We know house middle variant has fenced_yard_size = 3. Width 7.
        # So reservation is 13x13.
        # If we place one at 10, 10
        blueprint1 = self.world.place_construction_blueprint("house", 10, 10)
        self.assertIsNotNone(blueprint1)

        # Placing another at 15, 15 should fail because it intersects the 13x13 yard box of 10,10.
        # Max bounds of bp1: start_x = 10 - 3 = 7. End_x = 7 + 13 = 20.
        # 15,15 is inside the yard.
        blueprint2 = self.world.place_construction_blueprint("house", 15, 15)
        self.assertIsNone(blueprint2) # overlaps yard

        # Placing at 21, 21 should succeed
        blueprint3 = self.world.place_construction_blueprint("house", 24, 24)
        self.assertIsNotNone(blueprint3)
