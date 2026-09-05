import unittest
from engine import World, NPC
from simulation.systems.architecture import BUILDING_ARCHETYPES, generate_building
from simulation.systems.architecture import BuildingArchetype, BlueprintVariant
from tests.world_cache import fresh_world


class TestBlueprintVariants(unittest.TestCase):
    def setUp(self):
        # Seeded so the generated world doesn't vary with ambient global
        # random state, which shifts with test ordering and even with which
        # modules pytest imported during collection.
        self.world = fresh_world(seed=4101, pre_simulate=False)
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

    def test_building_serialization_preserves_variant_id(self):
        # We test that variant_id persists using pickling natively via save envelope tests, but since save_manager relies on pickle, we test pickling the building itself.
        import pickle
        blueprint = self.world.place_construction_blueprint("house", 5, 5)
        # fully supply and complete
        for item, count in blueprint.required_materials.items():
            for _ in range(count):
                blueprint.deposit_item_reference(None)
        blueprint.deposited_inventory = dict(blueprint.required_materials)

        self.world._complete_construction_blueprint(blueprint)
        building = [b for b in self.world.buildings_by_id.values() if b.building_type == "house"][-1]

        pickled_building = pickle.dumps(building)
        loaded_building = pickle.loads(pickled_building)

        self.assertEqual(loaded_building.variant_id, blueprint.variant_id)

    def test_get_variant_fallback_behavior(self):
        # Create an archetype with some variants
        arch = BuildingArchetype("test", "test", (10, 10), [], [], [], [
            BlueprintVariant("test_rich", 10, 10, [], [], 0, [], "rich"),
            BlueprintVariant("test_middle", 10, 10, [], [], 0, [], "middle")
        ])

        # Test unknown tier "poor" returns the first variant defined
        variant = arch.get_variant("poor")
        self.assertEqual(variant.id, "test_rich")

        # Test an empty archetype returns a generated deterministic default
        arch_empty = BuildingArchetype("test_empty", "test", (16, 16))
        variant_empty = arch_empty.get_variant("poor")
        self.assertEqual(variant_empty.id, "default")
        self.assertEqual(variant_empty.width, 4)
        self.assertEqual(variant_empty.height, 4)

    def test_wealth_variant_selection_uses_economic_money(self):
        # Create a rich NPC with poor inventory money
        rich_npc = NPC(x=10, y=10, name="Rich Guy")
        rich_npc.economic.money = 600
        rich_npc.economic.npc_inventory.add_item("money", 10)  # Inventory money should be ignored
        self.world.village_npcs.append(rich_npc)
        self.assertEqual(self.world._get_owner_wealth_tier(rich_npc.id), "rich")
        blueprint_rich = self.world.place_construction_blueprint("house", 5, 5, owner_id=rich_npc.id)
        # Variant id depends on wealth
        rich_variant = BUILDING_ARCHETYPES["house"].get_variant("rich")
        self.assertEqual(blueprint_rich.variant_id, rich_variant.id)

        # Create a poor NPC with rich inventory money
        poor_npc = NPC(x=12, y=12, name="Poor Guy")
        poor_npc.economic.money = 10
        poor_npc.economic.npc_inventory.add_item("money", 1000)  # Inventory money should be ignored
        self.world.village_npcs.append(poor_npc)
        self.assertEqual(self.world._get_owner_wealth_tier(poor_npc.id), "poor")
        blueprint_poor = self.world.place_construction_blueprint("house", 25, 25, owner_id=poor_npc.id)
        poor_variant = BUILDING_ARCHETYPES["house"].get_variant("poor")
        self.assertEqual(blueprint_poor.variant_id, poor_variant.id)

if __name__ == "__main__":
    unittest.main()
