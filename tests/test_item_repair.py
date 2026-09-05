import unittest
from unittest.mock import patch

import engine
from engine import NPC, World
from entities.items import ItemReference, REPAIR_DURABILITY_FLOOR_FRACTION, REPAIR_WEAR_PER_REPAIR_FRACTION
from simulation.careers import entity_has_capability
from tests.world_cache import fresh_world


class TestItemReferenceRepair(unittest.TestCase):
    """Ideation-audit item 5: item degradation was entirely one-way. Per
    Jason's finite-use design decision, ItemReference.repair() restores
    current_durability but permanently shaves max_durability down a bit
    each time, floored so an item is never fully unrepairable."""

    def _damaged_axe(self, durability=5):
        # axe_stone: max_durability=25, value=25 (data/items.py).
        axe = ItemReference("axe_stone", current_durability=durability)
        return axe

    def test_repair_restores_current_durability_to_ceiling(self):
        axe = self._damaged_axe(durability=5)
        result = axe.repair()

        self.assertTrue(result["repaired"])
        self.assertEqual(axe.current_durability, axe.max_durability)

    def test_repair_permanently_lowers_the_ceiling(self):
        axe = self._damaged_axe(durability=5)
        true_base = axe.true_base_max_durability  # 25

        axe.repair()

        self.assertLess(axe.max_durability, true_base)
        expected_wear = max(1, round(true_base * REPAIR_WEAR_PER_REPAIR_FRACTION))
        self.assertEqual(axe.max_durability, true_base - expected_wear)

    def test_repeated_repairs_approach_but_never_pass_the_floor(self):
        axe = self._damaged_axe(durability=1)
        true_base = axe.true_base_max_durability
        floor = max(1, round(true_base * REPAIR_DURABILITY_FLOOR_FRACTION))

        for _ in range(50):  # far more than enough to hit the floor
            axe.degrade(9999)
            axe.repair()

        self.assertEqual(axe.max_durability, floor)
        self.assertGreaterEqual(axe.max_durability, 1)

    def test_at_repair_limit_flag_reflects_reaching_the_floor(self):
        axe = self._damaged_axe(durability=1)
        result = None
        for _ in range(50):
            axe.degrade(9999)
            result = axe.repair()

        self.assertTrue(result["at_repair_limit"])

    def test_first_repair_is_not_at_limit(self):
        axe = self._damaged_axe(durability=5)
        result = axe.repair()
        self.assertFalse(result["at_repair_limit"])

    def test_item_with_no_max_durability_property_cannot_be_repaired(self):
        # raw_log has no max_durability property (data/items.py), so there
        # is no ceiling to restore and repair() must decline. This used to
        # name fur_cloak, which has since been given max_durability=80 -
        # pick a material rather than a wearable so the case can't quietly
        # stop testing anything if armour durability data changes again.
        log = ItemReference("raw_log")
        result = log.repair()
        self.assertFalse(result["repaired"])

    def test_repair_on_already_full_item_is_a_no_op_restore(self):
        axe = ItemReference("axe_stone")  # full durability by default
        result = axe.repair()
        # Still "repaired" (wear is applied regardless per the design:
        # repairing costs the item something even if it wasn't very
        # damaged), but current_durability stays at the (now slightly
        # lower) ceiling rather than exceeding it.
        self.assertTrue(result["repaired"])
        self.assertEqual(axe.current_durability, axe.max_durability)

    def test_repair_wear_field_survives_pickle_roundtrip_migration(self):
        """Regression test mirroring fix 1's save/load migration pattern:
        simulates an old save pickled before repair_wear existed by
        deleting it from __dict__ pre-pickle, then confirms unpickling and
        calling repair() doesn't crash."""
        import pickle

        axe = ItemReference("axe_stone", current_durability=5)
        del axe.__dict__["repair_wear"]
        data = pickle.dumps(axe)
        restored = pickle.loads(data)

        result = restored.repair()
        self.assertTrue(result["repaired"])


class TestPlayerArmorRepair(unittest.TestCase):
    """Player-armor-dict counterpart to ItemReference.repair(), since
    player equipped_armor isn't ItemReference-backed (see
    Player._degrade_equipped_armor_slot's docstring)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=5001, pre_simulate=False)
        self.player = self.world.player
        self.player.world_ref = self.world

    def test_repair_restores_slot_durability_to_ceiling(self):
        self.player.equip_armor("iron_helmet")  # max_durability=70
        self.player.equipment.equipped_armor_durability["head"] = 5

        result = self.player._repair_equipped_armor_slot("head")

        self.assertTrue(result["repaired"])
        self.assertEqual(
            self.player.equipment.equipped_armor_durability["head"],
            self.player.equipment.equipped_armor_max_durability["head"],
        )

    def test_repair_permanently_lowers_slot_ceiling(self):
        self.player.equip_armor("iron_helmet")
        true_base = 70

        self.player._repair_equipped_armor_slot("head")

        self.assertLess(self.player.equipment.equipped_armor_max_durability["head"], true_base)

    def test_repeated_repairs_approach_but_never_pass_the_floor(self):
        # Degrade by a small amount so the helmet survives each cycle. This
        # used to pass amount=9999, which broke the helmet every iteration;
        # breaking clears equipped_armor_max_durability (the item is gone,
        # so its repair history goes with it) and re-equipping reseeded a
        # fresh 70, pinning the ceiling at 63 forever. The erosion this
        # test is about only accumulates on an item that stays equipped.
        self.player.equip_armor("iron_helmet")
        floor = max(1, round(70 * REPAIR_DURABILITY_FLOOR_FRACTION))

        for _ in range(50):
            self.player._degrade_equipped_armor_slot("head", amount=1, world=self.world)
            self.player._repair_equipped_armor_slot("head")

        self.assertIsNotNone(self.player.equipment.equipped_armor.get("head"))
        self.assertEqual(self.player.equipment.equipped_armor_max_durability["head"], floor)

    def test_breaking_armor_clears_its_accumulated_repair_wear(self):
        """A destroyed item takes its repair history with it - a
        replacement is a different object and starts from the full
        ceiling."""
        self.player.equip_armor("iron_helmet")
        self.player._repair_equipped_armor_slot("head")
        self.assertLess(self.player.equipment.equipped_armor_max_durability["head"], 70)

        self.player._degrade_equipped_armor_slot("head", amount=9999, world=self.world)

        self.assertIsNone(self.player.equipment.equipped_armor.get("head"))
        self.assertNotIn("head", self.player.equipment.equipped_armor_max_durability)

    def test_empty_slot_does_not_crash(self):
        result = self.player._repair_equipped_armor_slot("body")
        self.assertFalse(result["repaired"])

    def test_swapping_armor_does_not_inherit_previous_items_repair_wear(self):
        self.player.equip_armor("iron_helmet")
        self.player._repair_equipped_armor_slot("head")
        worn_ceiling = self.player.equipment.equipped_armor_max_durability["head"]
        self.assertLess(worn_ceiling, 70)

        self.player.equip_armor("hooded_cowl")  # different head item

        self.assertNotIn("head", self.player.equipment.equipped_armor_max_durability)


class TestRepairInteractionEndToEnd(unittest.TestCase):
    """World.player_attempt_repair_gear - the Blacksmith-gated interaction
    that ties the two repair representations together."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=5002, pre_simulate=False)
        self.player = self.world.player
        self.player.world_ref = self.world
        self.blacksmith = NPC(
            self.player.x, self.player.y, name="Smith", dialogue=["Hi"], personality="villager", player_id=self.player.id
        )
        self.blacksmith.economic.profession = "Blacksmith"

    def test_blacksmith_has_repair_capability(self):
        self.assertTrue(entity_has_capability(self.blacksmith, "repair"))

    def test_non_blacksmith_cannot_repair(self):
        farmer = NPC(0, 0, name="Farmer", dialogue=["Hi"], personality="villager", player_id=self.player.id)
        farmer.economic.profession = "Farmer"
        self.player.add_item("axe_stone", 1)
        self.player.get_item_reference("axe_stone").current_durability = 1

        self.world.player_attempt_repair_gear(farmer)

        self.assertEqual(self.player.get_item_reference("axe_stone").current_durability, 1)
        self.assertIn("doesn't know how to repair gear", " ".join(self.world.chat_log))

    def test_no_damaged_gear_gives_clear_message(self):
        self.world.player_attempt_repair_gear(self.blacksmith)
        self.assertIn("nothing that needs repairing", " ".join(self.world.chat_log))

    def test_successful_repair_deducts_money_and_material_and_restores_item(self):
        self.player.add_item("axe_stone", 1)
        axe = self.player.get_item_reference("axe_stone")
        axe.current_durability = 1  # heavily damaged -> near-max cost
        self.player.economic.money = 100
        self.player.add_item("iron_ingot", 10)
        starting_money = self.player.economic.money
        starting_iron = self.player.economic.inventory.get("iron_ingot", 0)

        self.world.player_attempt_repair_gear(self.blacksmith)

        self.assertEqual(axe.current_durability, axe.max_durability)
        self.assertLess(self.player.economic.money, starting_money)
        self.assertLess(self.player.economic.inventory.get("iron_ingot", 0), starting_iron)
        self.assertIn("repairs your", " ".join(self.world.chat_log))

    def test_insufficient_money_blocks_repair(self):
        self.player.add_item("axe_stone", 1)
        axe = self.player.get_item_reference("axe_stone")
        axe.current_durability = 1
        self.player.economic.money = 0
        self.player.add_item("iron_ingot", 10)

        self.world.player_attempt_repair_gear(self.blacksmith)

        self.assertEqual(axe.current_durability, 1)
        self.assertIn("don't have enough", " ".join(self.world.chat_log))

    def test_insufficient_material_blocks_repair(self):
        self.player.add_item("axe_stone", 1)
        axe = self.player.get_item_reference("axe_stone")
        axe.current_durability = 1
        self.player.economic.money = 1000
        # No iron_ingot at all.

        self.world.player_attempt_repair_gear(self.blacksmith)

        self.assertEqual(axe.current_durability, 1)
        self.assertIn("don't have enough", " ".join(self.world.chat_log))

    def test_repairs_the_most_damaged_candidate_first(self):
        self.player.economic.money = 1000
        self.player.add_item("iron_ingot", 20)

        self.player.add_item("axe_stone", 1)
        axe = self.player.get_item_reference("axe_stone")
        axe.current_durability = 20  # lightly damaged (25 max)

        self.player.equip_armor("iron_helmet")  # 70 max
        self.player.equipment.equipped_armor_durability["head"] = 1  # heavily damaged

        self.world.player_attempt_repair_gear(self.blacksmith)

        # The helmet (far more damaged) should have been repaired, not the axe.
        self.assertEqual(
            self.player.equipment.equipped_armor_durability["head"],
            self.player.equipment.equipped_armor_max_durability["head"],
        )
        self.assertEqual(axe.current_durability, 20)  # untouched this call

    def test_at_repair_limit_produces_distinct_message(self):
        self.player.economic.money = 100000
        self.player.add_item("iron_ingot", 1000)
        self.player.add_item("axe_stone", 1)
        axe = self.player.get_item_reference("axe_stone")

        # Drive it to the repair floor first.
        for _ in range(50):
            axe.degrade(9999)
            axe.repair()
        axe.degrade(9999)
        self.world.chat_log.clear()

        self.world.player_attempt_repair_gear(self.blacksmith)

        self.assertIn("won't hold up like it used to", " ".join(self.world.chat_log))


if __name__ == "__main__":
    unittest.main()
