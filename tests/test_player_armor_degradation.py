import unittest

import engine
from engine import World
from data.items import ITEM_DEFINITIONS


class TestPlayerArmorDegradation(unittest.TestCase):
    """Bug-hunt audit item 5: player-equipped armor never degraded when
    hit, while NPC armor does via degrade_equipped_item. Confirmed live
    before this fix (equipping leather_jerkin and taking repeated damage
    never reduced any durability value - there wasn't even a durability
    value tracked for player armor at all). Player.take_damage now mirrors
    NPC.take_damage's blocked_damage -> degrade_equipped_item behavior via
    Player._degrade_equipped_armor_slot."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=1001)
        self.player = self.world.player
        self.player.world_ref = self.world

    def test_equipping_armor_starts_with_no_durability_entry(self):
        self.player.equip_armor("leather_jerkin")
        self.assertNotIn("body", self.player.equipment.equipped_armor_durability)

    def test_taking_a_blocked_hit_seeds_and_decrements_durability(self):
        self.player.equip_armor("leather_jerkin")
        max_durability = ITEM_DEFINITIONS["leather_jerkin"]["properties"]["max_durability"]

        self.player.take_damage(5, self.world)

        self.assertEqual(
            self.player.equipment.equipped_armor_durability.get("body"),
            max_durability - 1,
        )
        # Still equipped - one hit shouldn't break 60 durability.
        self.assertEqual(self.player.equipment.equipped_armor.get("body"), "leather_jerkin")

    def test_repeated_hits_eventually_break_and_unequip_the_armor(self):
        self.player.equip_armor("leather_jerkin")
        max_durability = ITEM_DEFINITIONS["leather_jerkin"]["properties"]["max_durability"]

        for _ in range(max_durability):
            self.player.take_damage(5, self.world)

        self.assertIsNone(self.player.equipment.equipped_armor.get("body"))
        self.assertNotIn("body", self.player.equipment.equipped_armor_durability)
        self.assertIn("Your Leather Jerkin broke!", self.world.chat_log)

    def test_breaking_armor_removes_its_defense_bonus_from_future_hits(self):
        self.player.equip_armor("leather_jerkin")
        max_durability = ITEM_DEFINITIONS["leather_jerkin"]["properties"]["max_durability"]
        for _ in range(max_durability):
            self.player.take_damage(5, self.world)
        self.assertEqual(self.player.combat.defense_bonus, 0)

        dealt = self.player.take_damage(5, self.world)
        self.assertEqual(dealt, 5)  # no more armor to absorb any of it

    def test_only_the_slot_that_actually_blocked_damage_degrades(self):
        """Head (iron_helmet, defense_bonus 1) contributes to blocking;
        body (fur_cloak, defense_bonus 0) doesn't - only head should wear
        down."""
        self.assertEqual(ITEM_DEFINITIONS["fur_cloak"]["properties"]["defense_bonus"], 0)
        self.player.equip_armor("iron_helmet")
        self.player.equip_armor("fur_cloak")

        self.player.take_damage(5, self.world)

        self.assertIn("head", self.player.equipment.equipped_armor_durability)
        self.assertNotIn("body", self.player.equipment.equipped_armor_durability)

    def test_armor_with_no_max_durability_property_never_degrades(self):
        """Mirrors ItemReference.degrade()'s no-op-when-durability-is-None
        behavior for the equivalent NPC case - an armor piece with no
        max_durability property (synthesized here since every real
        defense_bonus>0 item in data/items.py happens to define one) should
        never wear down or break, no matter how many hits it blocks."""
        ITEM_DEFINITIONS["_test_indestructible_vest"] = {
            "name": "Indestructible Test Vest",
            "item_type_tags": ["armor", "body"],
            "equip_slot": "body",
            "properties": {"defense_bonus": 3},
        }
        try:
            self.player.equip_armor("_test_indestructible_vest")
            for _ in range(50):
                self.player.take_damage(5, self.world)
            self.assertEqual(
                self.player.equipment.equipped_armor.get("body"),
                "_test_indestructible_vest",
            )
            self.assertNotIn("body", self.player.equipment.equipped_armor_durability)
        finally:
            del ITEM_DEFINITIONS["_test_indestructible_vest"]

    def test_swapping_armor_after_partial_wear_does_not_inherit_stale_durability(self):
        """Equip leather_jerkin, wear it down partway, unequip, then equip
        iron_breastplate into the same 'body' slot - the new item must
        start fresh from its own max_durability, not silently inherit the
        old item's remaining wear (a bug this fix's own durability dict
        could easily have introduced via a stale leftover 'body' entry)."""
        self.player.equip_armor("leather_jerkin")
        self.player.take_damage(5, self.world)
        self.assertIn("body", self.player.equipment.equipped_armor_durability)

        self.player.equip_armor("iron_breastplate")

        self.assertNotIn("body", self.player.equipment.equipped_armor_durability)
        self.player.take_damage(5, self.world)
        expected = ITEM_DEFINITIONS["iron_breastplate"]["properties"]["max_durability"] - 1
        self.assertEqual(self.player.equipment.equipped_armor_durability.get("body"), expected)

    def test_unarmored_player_take_damage_is_unaffected(self):
        """Baseline: no armor equipped at all shouldn't touch the
        durability dict or crash."""
        dealt = self.player.take_damage(5, self.world)
        self.assertEqual(dealt, 5)
        self.assertEqual(self.player.equipment.equipped_armor_durability, {})


if __name__ == "__main__":
    unittest.main()
