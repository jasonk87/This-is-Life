"""A healer can restock. Before this, no remedy was ever made anywhere.

Herbs are the only input to both remedies - healing_salve for a broken leg,
herbal_remedy for illness - and the only way anyone gets herbs is a Healer
foraging for them. That never produced a single herb, for two separate reasons.

First, the walk was interrupted. medical.py sent the healer out to a random spot
ten to twenty tiles away; a few ticks later update_npc_daily_goal_policy saw
someone outside their workplace during work hours and overwrote the task with
GOING_TO_WORK; medical.py then re-picked a *fresh random* destination and the
walk started over. _run_humanoid_schedule_logic already excluded the other
medical states from that policy - seeking_healer, waiting_for_treatment,
resting_in_bed, treating_patient - and the healer's own supply loop was simply
left off the list.

Second, and the reason it produced nothing even when the walk did finish: the
payout was keyed on catching the task in flight, `current_task ==
"foraging_for_herbs" and len(current_path) <= 1`. Movement consumes that last
step and sets the task to IDLE itself, and it runs first, so that window never
occurred. Traced on a healer: twenty tiles walked, arrival, idle, herb count
still zero, and straight back out to a new random spot.

With both fixed, the loop closes - measured on seed 5, herbs 0 -> 4 on arrival,
then crafting, then a healing_salve made and two herbs spent.
"""

import unittest

from engine import World
from tests.world_cache import fresh_world
from entities.items import Inventory
from simulation.systems.medical import update_npc_medical_state
from simulation.systems.tick import run_world_tick
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini

TICKS = 600


class TestTheForagePaysOutOnArrival(unittest.TestCase):
    """The off-by-one that made foraging free of charge and free of reward."""

    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)

    def _a_healer(self):
        npc = next(
            n for n in self.world.village_npcs
            if not n.physical.is_dead
        )
        npc.economic.profession = "Healer"
        npc.is_sleeping = False
        npc.economic.npc_inventory = Inventory({})
        return npc

    def test_arriving_with_the_task_already_cleared_still_pays(self):
        """Exactly the state movement leaves behind: standing on the spot, task
        no longer 'foraging_for_herbs'."""
        healer = self._a_healer()
        healer.forage_target_coords = (healer.x, healer.y)
        healer.schedule.current_task = "idle"
        healer.schedule.current_path = []

        update_npc_medical_state(self.world, healer)

        self.assertGreater(
            healer.economic.npc_inventory.get("medicinal_herb", 0), 0,
            "a healer standing on the spot they walked to came back empty-handed",
        )

    def test_the_target_is_cleared_so_it_pays_once(self):
        healer = self._a_healer()
        healer.forage_target_coords = (healer.x, healer.y)
        healer.schedule.current_task = "idle"
        healer.schedule.current_path = []

        update_npc_medical_state(self.world, healer)
        first = healer.economic.npc_inventory.get("medicinal_herb", 0)
        self.assertIsNone(getattr(healer, "forage_target_coords", None))

        healer.schedule.current_task = "idle"
        update_npc_medical_state(self.world, healer)

        self.assertGreaterEqual(
            healer.economic.npc_inventory.get("medicinal_herb", 0), first,
            "the herb count went backwards",
        )

    def test_a_healer_who_has_not_gone_anywhere_gets_nothing(self):
        """No target set means no forage in progress."""
        healer = self._a_healer()
        healer.forage_target_coords = None
        healer.schedule.current_task = "treating_patient"
        healer.schedule.current_path = []
        before = healer.economic.npc_inventory.get("medicinal_herb", 0)

        update_npc_medical_state(self.world, healer)

        self.assertEqual(healer.economic.npc_inventory.get("medicinal_herb", 0), before)


class TestTheSupplyLoopIsNotInterrupted(unittest.TestCase):
    """The scheduling half, stated as the exclusion it relies on."""

    def test_the_healers_supply_tasks_are_excluded_from_the_work_hours_check(self):
        import inspect

        import engine

        source = inspect.getsource(engine.World._run_humanoid_schedule_logic)
        for task in ("foraging_for_herbs", "crafting_medical_supplies"):
            with self.subTest(task=task):
                self.assertIn(
                    task, source,
                    f"{task} is no longer protected from the work-hours check, so "
                    f"the healer's walk will be overwritten part-way again",
                )


class TestRemediesGetMade(unittest.TestCase):
    """The supply loop end to end, against a running world.

    The healer's profession is re-asserted every tick, and that is deliberate.
    Writing this test three times taught what it is actually measuring:

    * following one healer for 400 ticks failed when an unrelated change to the
      mining chain shifted that individual's trajectory;
    * following everyone whose profession was "Healer" at tick zero failed too,
      because the careers system re-employed the village's only awake healer as
      a blacksmith partway through - the list being watched no longer contained
      anybody who forages;
    * measuring village-wide stock failed for the same reason, and only
      intermittently, which is worse: whether any healer survives as a healer
      long enough to forage was down to a coin flip.

    Whether the careers system reassigns people is its own behaviour and its own
    business. This test is about whether a healer who stays a healer gathers
    herbs and turns them into remedies, so it holds that one variable still.
    """

    TICKS = 400

    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)
        cls.healer = next(
            (n for n in cls.world.village_npcs
             if not n.physical.is_dead
             and not getattr(n, "is_sleeping", False)
             and n.economic.profession == "Healer"),
            None,
        )
        if cls.healer is None:
            return

        inventory = cls.healer.economic.npc_inventory
        cls.start_herbs = inventory.get("medicinal_herb", 0)
        cls.start_remedies = (
            inventory.get("healing_salve", 0) + inventory.get("herbal_remedy", 0)
        )
        cls.peak_herbs = cls.start_herbs
        cls.peak_remedies = cls.start_remedies

        for _ in range(cls.TICKS):
            # Hold the one variable this test is not about.
            cls.healer.economic.profession = "Healer"
            run_world_tick(cls.world)
            inventory = cls.healer.economic.npc_inventory
            cls.peak_herbs = max(cls.peak_herbs, inventory.get("medicinal_herb", 0))
            cls.peak_remedies = max(
                cls.peak_remedies,
                inventory.get("healing_salve", 0) + inventory.get("herbal_remedy", 0),
            )

    def setUp(self):
        if self.healer is None:
            self.skipTest("no awake healer in this world")

    def test_the_healer_gathers_herbs(self):
        self.assertGreater(
            self.peak_herbs, self.start_herbs,
            f"{self.TICKS} ticks of foraging never raised the healer's herb count "
            f"above its starting {self.start_herbs}",
        )

    def test_the_healer_turns_herbs_into_a_remedy(self):
        self.assertGreater(
            self.peak_remedies, self.start_remedies,
            "the healer gathered herbs and never made a salve or remedy from them",
        )


if __name__ == "__main__":
    unittest.main()
