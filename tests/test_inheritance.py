import unittest

import engine
from engine import NPC, World
from tests.world_cache import fresh_world


class TestMoneyInheritance(unittest.TestCase):
    """Quick fix #2: deceased.economic.money previously just vanished on
    death (only buildings transferred via _transfer_building_inheritance).
    Money should now follow the same primary-heir pattern buildings already
    use."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=123, pre_simulate=False)

    def _make_npc(self, name, age=30, money=0):
        npc = NPC(
            self.world.player.x,
            self.world.player.y,
            name=name,
            dialogue=["Hi"],
            personality="villager",
            player_id=self.world.player.id,
        )
        npc.age = age
        npc.economic.money = money
        self.world.village_npcs.append(npc)
        return npc

    def _marry(self, npc_a, npc_b):
        npc_a.social.family_ties["partner_id"] = npc_b.id
        npc_a.social.family_ties["spouse_id"] = npc_b.id
        npc_b.social.family_ties["partner_id"] = npc_a.id
        npc_b.social.family_ties["spouse_id"] = npc_a.id

    def test_money_transfers_to_primary_heir(self):
        deceased = self._make_npc("Deceased", money=500)
        heir = self._make_npc("Spouse", money=50)
        self._marry(deceased, heir)

        self.world._transfer_building_inheritance(deceased)

        self.assertEqual(heir.economic.money, 550)
        self.assertEqual(deceased.economic.money, 0)

    def test_money_lost_when_no_living_heir_exists(self):
        deceased = self._make_npc("Lonely Deceased", money=300)

        self.world._transfer_building_inheritance(deceased)

        self.assertEqual(deceased.economic.money, 0)
        # No heir exists, so there's nobody to have received it - just
        # confirming this doesn't error and the money doesn't materialize
        # anywhere else.

    def test_zero_money_is_a_no_op(self):
        deceased = self._make_npc("Poor Deceased", money=0)
        heir = self._make_npc("Heir", money=75)
        self._marry(deceased, heir)

        self.world._transfer_building_inheritance(deceased)

        self.assertEqual(heir.economic.money, 75)
        self.assertEqual(deceased.economic.money, 0)

    def test_heir_priority_matches_get_living_family_heirs(self):
        """Confirms money follows the exact same heir chosen for buildings
        (partner takes priority over children), rather than some separate
        selection."""
        deceased = self._make_npc("Deceased", money=1000, age=45)
        partner = self._make_npc("Partner", money=0, age=44)
        self._marry(deceased, partner)
        child = self._make_npc("Adult Child", money=0, age=20)
        deceased.social.family_ties["child_ids"] = [child.id]
        child.social.family_ties["mother_id"] = deceased.id

        heirs = self.world._get_living_family_heirs(deceased)
        self.assertEqual(heirs[0].id, partner.id)

        self.world._transfer_building_inheritance(deceased)

        self.assertEqual(partner.economic.money, 1000)
        self.assertEqual(child.economic.money, 0)

    def test_money_and_buildings_transfer_to_the_same_heir(self):
        from engine import Building

        deceased = self._make_npc("Deceased", money=200)
        heir = self._make_npc("Spouse", money=0)
        self._marry(deceased, heir)

        house = Building(0, 0, 5, 5, building_type="house", category="residential")
        house.owner_id = deceased.id
        self.world.buildings_by_id[house.id] = house

        self.world._transfer_building_inheritance(deceased)

        self.assertEqual(heir.economic.money, 200)
        self.assertEqual(house.owner_id, heir.id)

    def test_full_death_flow_transfers_money_via_handle_npc_death(self):
        """End-to-end through the real production death path, not just the
        isolated helper, to confirm it's actually wired into handle_npc_death."""
        deceased = self._make_npc("Elder", age=80, money=400)
        heir = self._make_npc("Spouse", age=75, money=10)
        self._marry(deceased, heir)
        self.world.npcs.append(deceased)

        deceased.physical.is_dead = True
        self.world.handle_npc_death(
            deceased,
            killer_id=None,
            description="{subject} died of old age.",
            cause_of_death="old_age",
        )

        self.assertEqual(heir.economic.money, 410)
        self.assertEqual(deceased.economic.money, 0)


if __name__ == "__main__":
    unittest.main()
