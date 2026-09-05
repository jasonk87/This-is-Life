"""A healer can spend their last remedy without crashing the game.

Inventory drops a key the moment its quantity reaches zero. The treatment code
decremented a remedy and then read the same key back to decide whether to remove
it - so the healer's *last* salve took the key away and the read raised
KeyError, in the middle of the tick that treated the patient.

The identical fault was fixed once before in World._produce_sub_task_output, for
the same reason: a bakery baking its last sack of flour. This copy was never
reachable, because generation put no clinic in any village and so no world had a
Healer with a remedy to spend. Adding the clinic back made it reachable and it
turned up within a few hundred ticks of ordinary simulation.

Worth remembering as a pattern rather than two isolated bugs: with this Inventory,
`inv[key] -= 1` followed by `inv[key]` is a crash waiting for the quantity to
reach zero. Read it back with .get.
"""

import unittest

from engine import World
from tests.world_cache import fresh_world
from entities.items import Inventory
from simulation.systems.illness import SICK_STATUS_EFFECT
from simulation.systems.medical import update_npc_medical_state


class TestTheInventoryContract(unittest.TestCase):
    """The behaviour both bugs were written against."""

    def test_a_key_disappears_when_it_reaches_zero(self):
        inventory = Inventory({"healing_salve": 1})
        inventory["healing_salve"] -= 1
        self.assertNotIn("healing_salve", inventory)

    def test_get_still_answers_after_it_is_gone(self):
        inventory = Inventory({"healing_salve": 1})
        inventory["healing_salve"] -= 1
        self.assertEqual(inventory.get("healing_salve", 0), 0)


class TestSpendingTheLastRemedy(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=5)
        living = [n for n in self.world.village_npcs if not n.physical.is_dead]
        self.assertGreaterEqual(len(living), 2, "not enough villagers to treat anyone")
        self.healer, self.patient = living[0], living[1]

        self.healer.economic.profession = "Healer"
        self.healer.is_sleeping = False
        self.healer.economic.npc_inventory = Inventory({"healing_salve": 1})

        self.patient.is_sleeping = False
        self.patient.economic.money = 0  # forces payment in kind, which is the path
        self.patient.physical.status_effects.append("broken_leg")
        self.world._update_entity_position(
            self.patient, self.healer.x, self.healer.y
        )

    def test_treating_with_the_last_salve_does_not_raise(self):
        for _ in range(40):
            update_npc_medical_state(self.world, self.healer)
            update_npc_medical_state(self.world, self.patient)

    def test_the_healer_is_not_left_holding_a_phantom_remedy(self):
        for _ in range(40):
            update_npc_medical_state(self.world, self.healer)
            update_npc_medical_state(self.world, self.patient)
        self.assertGreaterEqual(
            self.healer.economic.npc_inventory.get("healing_salve", 0), 0,
            "the remedy count went negative",
        )


class TestAVillageCanTreatIllness(unittest.TestCase):
    """The subsystem this unblocked, end to end at the level that matters."""

    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)

    def test_a_clinic_exists_to_work_from(self):
        clinics = [
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "clinic"
        ]
        self.assertTrue(clinics, "no clinic was generated, so no Healer can be hired")

    def test_the_clinic_has_the_station_remedies_are_made_at(self):
        clinic = next(
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "clinic"
        )
        self.assertIn("alchemy_station", clinic.work_zone_tiles)
        self.assertTrue(clinic.work_zone_tiles["alchemy_station"])

    def test_illness_still_clears_with_rest_for_anyone_a_healer_never_reaches(self):
        """Treatment is the fast path, not the only one - measured while the
        clinic was missing entirely, and it must stay true now it is back."""
        from simulation.systems import illness

        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.physical.sickness = 60
        if SICK_STATUS_EFFECT not in npc.physical.status_effects:
            npc.physical.status_effects.append(SICK_STATUS_EFFECT)
        npc.schedule.current_task = "resting_in_bed"

        for _ in range(4000):
            self.world.game_time += 1
            illness.update_entity_illness(self.world, npc)

        self.assertEqual(npc.physical.sickness, 0)


if __name__ == "__main__":
    unittest.main()
