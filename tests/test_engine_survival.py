import unittest
from engine import World
from engine import NPC
from entities.items import Inventory, ItemReference

class TestSurvivalOverrides(unittest.TestCase):
    def test_hunger_override_can_find_item_reference(self):
        world = World(seed=123)
        npc = NPC(10, 10, name="Hungry NPC")
        world.village_npcs.append(npc)
        npc.hunger = 0.8  # trigger hunger override

        # Create an inventory with an item reference
        inv = Inventory()
        inv.add_item_reference(ItemReference("processed_meat"))
        world.items_on_map[(11, 10)] = inv

        # Verify the nearest edible food target is correctly found
        target = world._find_nearest_edible_food_target(npc)
        self.assertIsNotNone(target)
        self.assertEqual(target["item_key"], "processed_meat")
        self.assertEqual(target["coords"], (11, 10))

    def test_validation_warning_aggregation_keys(self):
        world = World(seed=123)
        # Verify bounded keys for typical problems
        world._warn_simulation_validation("survival_override_no_valid_target", (1, "cold"), "No valid warmth/shelter target found.", actor=None)
        world._warn_simulation_validation("survival_override_no_valid_target", (1, "cold"), "No valid warmth/shelter target found.", actor=None)

        counts = getattr(world, "validation_warning_counts", {})
        key = ("survival_override_no_valid_target", (1, "cold"))
        self.assertIn(key, counts)
        self.assertEqual(counts[key], 2)
