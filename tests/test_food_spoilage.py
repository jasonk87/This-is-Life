"""Food spoils at the rate the data says it does — per day, not per tick.

`spoilage_chance` in data/items.py reads as a daily figure (2% bread, 20% raw
meat) and World._update_inventory_spoilage applies it on a once-a-day gate. But
ItemReference.update_tick runs every world tick and rolled that number directly,
so at 14400 ticks to the day a loaf's expected life was about fifty ticks - five
in-game minutes. Building stores rotted faster than anyone could eat them.
"""

import unittest
from unittest.mock import patch

from config import DAY_LENGTH_TICKS
from data.items import ITEM_DEFINITIONS
from engine import World
from entities.items import Inventory, ItemReference, per_tick_spoilage_chance


class TestSpoilageRateConversion(unittest.TestCase):
    def test_a_daily_chance_becomes_that_chance_over_a_day(self):
        for daily in (0.005, 0.02, 0.05, 0.2):
            per_tick = per_tick_spoilage_chance(daily)
            survives_a_day = (1.0 - per_tick) ** DAY_LENGTH_TICKS
            self.assertAlmostEqual(
                1.0 - survives_a_day, daily, places=6,
                msg=f"a {daily:.1%}/day item did not spoil {daily:.1%} over a day",
            )

    def test_the_edges_are_handled(self):
        self.assertEqual(per_tick_spoilage_chance(0.0), 0.0)
        self.assertEqual(per_tick_spoilage_chance(1.0), 1.0)
        self.assertEqual(per_tick_spoilage_chance(-1.0), 0.0)

    def test_a_per_tick_chance_is_far_below_the_daily_one(self):
        """Regression: the daily number used to be rolled directly, every tick."""
        for daily in (0.02, 0.2):
            self.assertLess(per_tick_spoilage_chance(daily), daily / 1000)

    def test_every_spoiling_item_survives_most_of_a_day(self):
        for item_key, definition in ITEM_DEFINITIONS.items():
            daily = definition.get("properties", {}).get("spoilage_chance", 0.0)
            if not daily:
                continue
            per_tick = per_tick_spoilage_chance(daily)
            survives = (1.0 - per_tick) ** DAY_LENGTH_TICKS
            self.assertGreater(
                survives, 0.5,
                f"{item_key} has a {daily:.0%}/day spoilage rate but only {survives:.1%} survives a day",
            )


class TestStoresSurviveTheDay(unittest.TestCase):
    """A settlement has to be able to keep food long enough to eat it."""

    def _spoiled_after(self, item_key, quantity, ticks):
        inventory = Inventory()
        inventory[item_key] = quantity
        for _ in range(ticks):
            inventory.process_tick()
        return quantity - inventory.get(item_key, 0)

    def test_bread_mostly_survives_an_hour(self):
        ticks_per_hour = DAY_LENGTH_TICKS // 24
        spoiled = self._spoiled_after("bread", 200, ticks_per_hour)
        self.assertLess(
            spoiled, 20,
            f"{spoiled} of 200 loaves rotted in one in-game hour",
        )

    def test_food_that_does_spoil_turns_into_what_the_data_says(self):
        """Forced, because the honest odds are now about one in seven hundred thousand."""
        item = ItemReference(key="bread")
        with patch("entities.items.random.random", return_value=0.0):
            became = item.update_tick()
        self.assertEqual(became, ITEM_DEFINITIONS["bread"]["properties"]["rots_into"])
        self.assertEqual(item.key, "rotten_food")

    def test_an_unlucky_roll_is_still_needed(self):
        item = ItemReference(key="bread")
        with patch("entities.items.random.random", return_value=1.0):
            became = item.update_tick()
        self.assertEqual(became, "bread")

    def test_nothing_spoils_when_the_item_does_not_rot(self):
        spoiled = self._spoiled_after("iron_ingot", 50, DAY_LENGTH_TICKS // 24)
        self.assertEqual(spoiled, 0)


class TestSpoilageIsResolvedPerStack(unittest.TestCase):
    """Whether a thing can rot is a property of the kind, not of each instance.

    process_tick used to look the answer up, and roll a die, for every object
    every tick. 96% of what a village stores cannot spoil at all - a general
    store's coins alone are thousands of instances each rolling against a
    chance of zero - and that pass cost about a fifth of every world tick.
    """

    def test_items_that_cannot_spoil_are_left_alone(self):
        inventory = Inventory()
        inventory["iron_ingot"] = 50
        with patch("entities.items.random.random", return_value=0.0) as rolled:
            inventory.process_tick()
        self.assertEqual(inventory.get("iron_ingot", 0), 50)
        self.assertEqual(rolled.call_count, 0, "a die was rolled for something that cannot rot")

    def test_items_that_can_spoil_still_do(self):
        inventory = Inventory()
        inventory["bread"] = 10
        with patch("entities.items.random.random", return_value=0.0):
            inventory.process_tick()
        self.assertEqual(inventory.get("bread", 0), 0)
        self.assertEqual(inventory.get("rotten_food", 0), 10)

    def test_non_perishables_still_age(self):
        inventory = Inventory()
        inventory["iron_ingot"] = 3
        before = [item.age_in_ticks for item in inventory.iter_item_references("iron_ingot")]
        inventory.process_tick()
        after = [item.age_in_ticks for item in inventory.iter_item_references("iron_ingot")]
        self.assertEqual(after, [age + 1 for age in before])

    def test_a_mixed_inventory_only_rolls_for_the_perishables(self):
        inventory = Inventory()
        inventory["money"] = 500
        inventory["wooden_plank"] = 100
        inventory["bread"] = 4
        with patch("entities.items.random.random", return_value=1.0) as rolled:
            inventory.process_tick()
        self.assertEqual(rolled.call_count, 4, "rolled for more than the four loaves")


class TestCarriedFoodSpoilsToo(unittest.TestCase):
    """The same loaf rotted in a pantry and kept forever in a pocket.

    Buildings and the ground were ticked by _tick_world_item_inventories; packs
    were not, and the one function that would have covered them
    (_update_inventory_spoilage) has no caller anywhere - and walks building
    inventories as well, so calling it would spoil those twice.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")

    def _spoil_one_tick(self, inventory):
        inventory["bread"] = 20
        with patch("entities.items.random.random", return_value=0.0):
            self.world._tick_world_item_inventories()
        return inventory.get("bread", 0)

    def test_food_in_the_players_pack_spoils(self):
        self.assertEqual(self._spoil_one_tick(self.world.player.economic.inventory), 0)

    def test_food_an_npc_is_carrying_spoils(self):
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        self.assertEqual(self._spoil_one_tick(npc.economic.npc_inventory), 0)

    def test_food_in_a_building_still_spoils(self):
        building = next(iter(self.world.buildings_by_id.values()))
        self.assertEqual(self._spoil_one_tick(building.building_inventory), 0)

    def test_a_carried_stack_mostly_survives_a_normal_day(self):
        """Gentle, not punishing - the same daily rates the rest of the world uses."""
        player = self.world.player
        player.economic.inventory["bread"] = 200
        for _ in range(DAY_LENGTH_TICKS // 24 * 6):
            player.economic.inventory.process_tick()
        self.assertGreater(
            player.economic.inventory.get("bread", 0), 180,
            "carried bread rotted far too fast over six in-game hours",
        )

    def test_preserved_food_outlasts_fresh(self):
        """Smoking meat is only worth doing if it actually keeps longer."""
        fresh = per_tick_spoilage_chance(
            ITEM_DEFINITIONS["raw_meat"]["properties"]["spoilage_chance"]
        )
        smoked = per_tick_spoilage_chance(
            ITEM_DEFINITIONS["smoked_meat"]["properties"]["spoilage_chance"]
        )
        self.assertLess(smoked, fresh)


if __name__ == "__main__":
    unittest.main()
