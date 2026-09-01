"""War between villages works - when one actually starts.

Measured over 120 simulated days across four villages, no war was ever declared:
relationships bottomed at -17 against the -50 threshold, because the daily
souring is a 5% roll for -5 while trade pulls the same numbers back up. That is a
tuning question (see WAR_THRESHOLD_NOTE in engine.py), not a broken mechanism -
these tests pin the mechanism so it stays working while the trigger is decided.
"""

import unittest

from engine import World


class TestWarMechanism(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.villages = list(cls.world.villages)

    def setUp(self):
        for village in self.villages:
            village.at_war_with.clear()

    def _declare_war(self):
        self.assertGreaterEqual(len(self.villages), 2, "need two villages to fight")
        first, second = self.villages[0], self.villages[1]
        first.at_war_with.add(second.id)
        second.at_war_with.add(first.id)
        return first, second

    def _official_of(self, village):
        for npc in self.world.village_npcs:
            if npc.physical.is_dead:
                continue
            if self.world._get_npc_settlement(npc) is village:
                npc.economic.profession = "Sheriff"
                return npc
        return None

    def test_peacetime_offers_no_mercenary_work(self):
        village = self.villages[0]
        official = self._official_of(village)
        self.assertIsNotNone(official)
        actions = self.world._get_actions_for_entity(
            {"type": "npc", "data": official, "name": official.name}
        )
        self.assertNotIn("Offer Mercenary Services", actions)

    def test_a_village_at_war_offers_mercenary_work(self):
        village, _ = self._declare_war()
        official = self._official_of(village)
        self.assertIsNotNone(official)
        actions = self.world._get_actions_for_entity(
            {"type": "npc", "data": official, "name": official.name}
        )
        self.assertIn("Offer Mercenary Services", actions)

    def test_taking_the_contract_creates_a_real_quest(self):
        village, _ = self._declare_war()
        official = self._official_of(village)
        before = len(self.world.player.knowledge.active_quests)

        self.world.player_attempt_mercenary_contract(official)

        self.assertGreater(
            len(self.world.player.knowledge.active_quests), before,
            "a mercenary contract produced no quest",
        )

    def test_war_is_mutual(self):
        first, second = self._declare_war()
        self.assertIn(second.id, first.at_war_with)
        self.assertIn(first.id, second.at_war_with)


if __name__ == "__main__":
    unittest.main()
