"""A starving villager can see the bread in their own hand.

`_find_nearest_edible_food_target` searched `items_on_map` - food lying loose on
the ground - for five hardcoded keys:

    simple_food, cooked_meat, food_ration, rotten_food, processed_meat

Only two of those five pass `is_entity_edible`. The other three are not food as
far as the engine is concerned, so they could never match. Meanwhile bread,
apple, fish, smoked_meat, cooked_fish, cooked_mutton, cooked_venison, pear,
acorn and smoked_fish - ten of the twelve edible items in the game, and all of
the ones a village actually contains - were never looked for at all.

And nothing in a generated world lies on the ground. Food lives in bakeries,
taverns, general stores and people's pockets. So the only route that reduces
`actor.hunger` could never fire.

Measured on seed 2024 before the fix: all ninety villagers pinned at the 2.0
hunger cap, every one of them carrying bread or apples, one standing inside a
bakery holding twenty-three loaves, reporting "no edible food" 498 times per
three thousand ticks.

Two things are fixed here: the ground search now matches whatever edible item is
actually present rather than a fixed list, and a villager who is carrying food
eats it instead of walking off to look for some.

**What is deliberately not fixed here**, because it is tuning and supply rather
than correctness - see the module docstring note in the commit:

  - `advance_actor_hunger` adds 0.01 every tick, so a villager crosses the 0.7
    override threshold every seventy ticks and one loaf of bread (0.5) buys
    fifty. Keeping ninety villagers fed at that rate needs thousands of meals
    per game day against a village supply of about a hundred items.
  - Nothing restocks a villager's pack, so eating what they carry buys a couple
    of hundred ticks and then the warning returns.

Neither has a behavioural consequence today: with hunger forced to zero the work
distribution is unchanged (63 vs 65 at_work over 2000 ticks), nobody dies, and
`physical.hunger` - the field that actually gates scheduling - sits healthy
around 21/100. That is why they are recorded rather than chased.
"""

import unittest

from tests.world_cache import fresh_world


class TestAVillagerEatsWhatTheyCarry(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=2024, pre_simulate=False)
        self.npc = self.world.village_npcs[0]
        self.npc.economic.npc_inventory.clear()

    def test_carried_bread_is_eaten(self):
        self.npc.economic.npc_inventory.add_item("bread", 1)
        self.npc.hunger = 1.0

        self.assertTrue(self.world._eat_from_own_inventory(self.npc),
                        "a starving villager did not eat the bread they were holding")
        self.assertLess(self.npc.hunger, 1.0, "eating did not reduce hunger")
        self.assertEqual(self.npc.economic.npc_inventory.get("bread", 0), 0,
                         "hunger went down without the bread being consumed")

    def test_hunger_falls_by_the_items_nutrition(self):
        self.npc.economic.npc_inventory.add_item("bread", 1)
        self.npc.hunger = 1.0
        self.world._eat_from_own_inventory(self.npc)
        self.assertAlmostEqual(self.npc.hunger,
                               1.0 - self.world.get_entity_nutrition_value("bread"), places=6)

    def test_the_most_filling_item_is_chosen(self):
        """An apple is 0.1 and bread is 0.5 - eat the bread."""
        self.npc.economic.npc_inventory.add_item("apple", 1)
        self.npc.economic.npc_inventory.add_item("bread", 1)
        self.npc.hunger = 1.0
        self.world._eat_from_own_inventory(self.npc)
        self.assertEqual(self.npc.economic.npc_inventory.get("bread", 0), 0)
        self.assertEqual(self.npc.economic.npc_inventory.get("apple", 0), 1)

    def test_carrying_nothing_edible_is_not_a_meal(self):
        self.npc.economic.npc_inventory.add_item("raw_log", 3)
        self.npc.hunger = 1.0
        self.assertFalse(self.world._eat_from_own_inventory(self.npc))
        self.assertEqual(self.npc.hunger, 1.0)
        self.assertEqual(self.npc.economic.npc_inventory.get("raw_log", 0), 3,
                         "a log was eaten")

    def test_hunger_never_goes_negative(self):
        self.npc.economic.npc_inventory.add_item("bread", 1)
        self.npc.hunger = 0.05
        self.world._eat_from_own_inventory(self.npc)
        self.assertGreaterEqual(self.npc.hunger, 0.0)


class TestTheGroundSearchSeesRealFood(unittest.TestCase):
    """The ten edible items the hardcoded list could never match."""

    def setUp(self):
        self.world = fresh_world(seed=2024, pre_simulate=False)
        self.npc = self.world.village_npcs[0]
        self.world.items_on_map.clear()

    def test_bread_on_the_ground_is_found(self):
        self.world.drop_item_on_map("bread", 1, self.npc.x + 1, self.npc.y)
        target = self.world._find_nearest_edible_food_target(self.npc)
        self.assertIsNotNone(target, "a loaf one tile away was invisible")
        self.assertEqual(target["item_key"], "bread")

    def test_every_edible_item_can_be_found(self):
        """Guards against a new food being added that the search cannot see."""
        from data.items import ITEM_DEFINITIONS

        edible = [k for k in ITEM_DEFINITIONS if self.world.is_entity_edible(k)]
        self.assertGreater(len(edible), 2, "expected more than two edible items in the game")
        for key in edible:
            with self.subTest(item=key):
                self.world.items_on_map.clear()
                self.world.drop_item_on_map(key, 1, self.npc.x + 1, self.npc.y)
                target = self.world._find_nearest_edible_food_target(self.npc)
                self.assertIsNotNone(target, f"{key} is edible but the search cannot see it")

    def test_something_inedible_is_not_mistaken_for_food(self):
        self.world.drop_item_on_map("raw_log", 1, self.npc.x + 1, self.npc.y)
        self.assertIsNone(self.world._find_nearest_edible_food_target(self.npc))


if __name__ == "__main__":
    unittest.main()
