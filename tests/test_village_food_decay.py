import unittest
from unittest.mock import patch

import engine
from engine import Village, World


class TestDecayVillageFoodSupply(unittest.TestCase):
    """village.supply (the abstracted village-level food ledger that drives
    starvation/scarcity checks) used to never decay, unlike building_inventory/
    ground loot/personal npc_inventory, which all spoil per-item via
    ItemReference.update_tick's spoilage_chance/rots_into. _decay_village_food_supply
    adds an analogous, but separately-rated, decay pass gated on the same
    ITEM_DEFINITIONS properties the physical system uses."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=83)

    def test_decay_reduces_perishable_stock_and_adds_rotten_food(self):
        village = Village()
        village.supply["raw_meat"] = 100  # 100 * 3% = exactly 3, no rounding involved

        self.world._decay_village_food_supply(village)

        self.assertEqual(village.supply["raw_meat"], 97)
        self.assertEqual(village.supply["rotten_food"], 3)

    def test_wheat_does_not_decay_lacking_spoilage_properties(self):
        # wheat/flour are tagged food_ingredient but have no spoilage_chance/
        # rots_into in ITEM_DEFINITIONS at all - dry grain doesn't spoil in
        # the physical system either, so it shouldn't here.
        village = Village()
        village.supply["wheat"] = 500

        self.world._decay_village_food_supply(village)

        self.assertEqual(village.supply["wheat"], 500)
        self.assertNotIn("rotten_food", village.supply)

    def test_non_food_resource_is_untouched(self):
        village = Village()
        village.supply["raw_log"] = 200

        self.world._decay_village_food_supply(village)

        self.assertEqual(village.supply["raw_log"], 200)

    def test_item_is_removed_from_supply_once_fully_decayed(self):
        village = Village()
        village.supply["raw_meat"] = 1  # expected_loss = 0.03, whole stock at risk

        with patch("engine.random.random", return_value=0.0):  # forces the stochastic round-up
            self.world._decay_village_food_supply(village)

        self.assertNotIn("raw_meat", village.supply)
        self.assertEqual(village.supply["rotten_food"], 1)

    def test_rotten_food_does_not_decay_further(self):
        village = Village()
        village.supply["rotten_food"] = 50

        self.world._decay_village_food_supply(village)

        self.assertEqual(village.supply["rotten_food"], 50)

    def test_stochastic_rounding_can_avoid_loss_below_one_unit(self):
        village = Village()
        village.supply["raw_meat"] = 10  # expected_loss = 0.3

        with patch("engine.random.random", return_value=0.99):  # fails the round-up roll
            self.world._decay_village_food_supply(village)

        self.assertEqual(village.supply["raw_meat"], 10)
        self.assertNotIn("rotten_food", village.supply)

    def test_stochastic_rounding_can_cause_loss_below_one_unit(self):
        village = Village()
        village.supply["raw_meat"] = 10  # expected_loss = 0.3

        with patch("engine.random.random", return_value=0.0):  # succeeds the round-up roll
            self.world._decay_village_food_supply(village)

        self.assertEqual(village.supply["raw_meat"], 9)
        self.assertEqual(village.supply["rotten_food"], 1)

    def test_empty_supply_does_not_crash(self):
        village = Village()
        self.world._decay_village_food_supply(village)  # no exception
        self.assertEqual(village.supply, {})

    def test_unknown_item_key_is_ignored_safely(self):
        village = Village()
        village.supply["some_modded_item_not_in_definitions"] = 10

        self.world._decay_village_food_supply(village)

        self.assertEqual(village.supply["some_modded_item_not_in_definitions"], 10)

    def test_decay_never_removes_more_than_available(self):
        village = Village()
        village.supply["raw_meat"] = 1  # expected_loss = 0.03

        with patch("engine.random.random", return_value=0.0):
            self.world._decay_village_food_supply(village)

        self.assertNotIn("raw_meat", village.supply)
        self.assertEqual(village.supply["rotten_food"], 1)


class TestDecayWiredIntoDailyAbstractSimulation(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=89)

    def test_village_supply_decays_on_the_daily_abstract_simulation_tick(self):
        village = None
        for row in self.world.chunks:
            for chunk in row:
                if chunk.village:
                    village = chunk.village
                    break
            if village:
                break
        self.assertIsNotNone(village, "expected at least one generated village")

        village.supply["raw_meat"] = 100
        self.world.game_time = engine.DAY_LENGTH_TICKS * 5  # lands exactly on the daily gate

        self.world._update_abstract_simulation()

        self.assertLess(village.supply.get("raw_meat", 0), 100)


if __name__ == "__main__":
    unittest.main()
