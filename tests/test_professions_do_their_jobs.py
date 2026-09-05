"""Every trade with a workplace has work, and can get on with it.

Three separate faults let villagers stand at their workplaces doing nothing, and
none of them raised so much as a warning. What they had in common is that each
piece worked in isolation and the combination did not.

* A change of trade left the old trade's step in place. Work is looked up as
  get_sub_task_data(profession, step), so a step belonging to a previous job
  resolves to nothing and the worker stalls holding it. Traced on a villager the
  careers system moved from Blacksmith to Woodcutter: profession Woodcutter,
  workplace the lumber mill, and their whole shift spent pursuing "fetch_ore"
  toward the mine.

* Woodcutters chose trees they could not reach. A tree is impassable and is
  felled from the square beside it, and the search returned the nearest one
  without asking whether there was anywhere to stand. In woodland the nearest
  tree is usually hemmed in, so the work system pathed at an unreachable tile,
  gave up, waited twenty ticks, and chose the very same tree again. Logged as
  "path_unreachable chop_trees" over and over for an entire shift.

* The guard that keeps a worker from being marched back to their workplace
  compared the destination to the sub-task target exactly. For a station nobody
  can stand on - a tree again - the work system paths to a neighbouring square,
  so that test said "not working" for every woodcutter alive.

* And Lumber Mill Foreman simply had no work defined at all.

The static half of this catches the last of those in milliseconds. The running
half catches the others, by asserting the two things that were false while the
game looked fine: that the trades which turn raw materials into goods actually
complete steps, and that nobody is stuck in a retry loop.

Deliberately loose on which trades: professions come and go as the careers
system re-employs people, so this asserts that the production economy as a whole
is working rather than pinning named individuals. Pinning individuals is how
three earlier versions of a different test managed to fail while the code was
fine.
"""

import collections
import unittest

from data.professions import PROFESSIONS, get_sub_task_data
from simulation.systems.tick import run_world_tick
from tests.world_cache import fresh_world
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini

# These legitimately have no sub-task sequence. A traveling merchant is driven
# by its own policy and the unemployed are looking for work, not doing it.
NO_WORK_EXPECTED = {"Traveling Merchant", "Unemployed"}

# Trades that turn something into something else. If none of these complete a
# step over a working day's worth of ticks, the production economy has stopped.
PRODUCTION_TRADES = {
    "Miner", "Blacksmith", "Baker", "Miller", "Farmer", "Woodcutter",
    "Butcher", "Lumber Mill Foreman", "Carpenter",
}

TICKS = 1500
# An NPC that abandons the same step more than this many times is not unlucky,
# it is looping. The woodcutter fault produced one every twenty ticks forever.
MAX_ABANDONS_PER_STEP = 6


class TestEveryTradeHasWorkDefined(unittest.TestCase):
    """Static, and therefore instant."""

    def test_a_profession_with_a_workplace_has_something_to_do_there(self):
        for name, data in PROFESSIONS.items():
            if name in NO_WORK_EXPECTED:
                continue
            if not data.get("work_building_categories"):
                continue
            with self.subTest(profession=name):
                self.assertTrue(
                    data.get("default_sub_task_sequence"),
                    f"{name} is employed at {data['work_building_categories']} and has "
                    f"no work sequence, so they will stand there indefinitely",
                )

    def test_every_step_in_a_sequence_is_defined(self):
        for name, data in PROFESSIONS.items():
            defined = {step["id"] for step in data.get("sub_tasks", [])}
            for step in data.get("default_sub_task_sequence", []):
                with self.subTest(profession=name, step=step):
                    self.assertIn(
                        step, defined,
                        f"{name}'s sequence names {step!r}, which the profession does "
                        f"not define - the work loop skips it every time",
                    )

    def test_every_step_can_be_looked_up_the_way_the_work_loop_looks_it_up(self):
        """The work loop resolves steps through get_sub_task_data. A step the
        profession lists but that lookup cannot find is a step never run."""
        for name, data in PROFESSIONS.items():
            for step in data.get("default_sub_task_sequence", []):
                with self.subTest(profession=name, step=step):
                    self.assertIsNotNone(get_sub_task_data(name, step))

    def test_the_trades_that_had_no_work_still_have_some(self):
        for name in ("Lumber Mill Foreman", "Woodcutter", "Blacksmith", "Miner"):
            with self.subTest(profession=name):
                self.assertTrue(PROFESSIONS[name]["default_sub_task_sequence"])


class TestTheProductionEconomyRuns(unittest.TestCase):
    """The running half: work is not merely defined, it completes."""

    @classmethod
    def setUpClass(cls):
        world = fresh_world(seed=5)
        cls.completed = collections.Counter()
        cls.abandoned = collections.Counter()

        original_work = world._execute_completed_work_sub_task

        def counting(npc, building, sub_task_id, data, *args, **kwargs):
            cls.completed[npc.economic.profession] += 1
            return original_work(npc, building, sub_task_id, data, *args, **kwargs)

        world._execute_completed_work_sub_task = counting

        from simulation.systems import work as work_module

        original_abandon = work_module._abandon_invalid_task

        def watching(w, npc, reason=None, sub_task_data=None, metadata=None, **kwargs):
            step = (sub_task_data or {}).get("id")
            cls.abandoned[(getattr(npc, "id", None), step)] += 1
            return original_abandon(
                w, npc, reason=reason, sub_task_data=sub_task_data,
                metadata=metadata, **kwargs,
            )

        work_module._abandon_invalid_task = watching
        try:
            for _ in range(TICKS):
                run_world_tick(world)
        finally:
            work_module._abandon_invalid_task = original_abandon
        cls.world = world

    def test_work_is_being_completed_at_all(self):
        self.assertTrue(
            self.completed,
            f"not one work step of any kind completed in {TICKS} ticks",
        )

    def test_the_production_trades_are_working(self):
        working = PRODUCTION_TRADES & set(self.completed)
        self.assertGreaterEqual(
            len(working), 3,
            f"only {sorted(working)} of the production trades completed any work in "
            f"{TICKS} ticks. Everything completed: {dict(self.completed)}",
        )

    def test_nobody_is_stuck_in_a_retry_loop(self):
        """The shape of the woodcutter fault: the same worker abandoning the
        same step again and again, forever, while looking busy."""
        looping = {
            key: count for key, count in self.abandoned.items()
            if count > MAX_ABANDONS_PER_STEP
        }
        self.assertEqual(
            looping, {},
            "workers are abandoning the same step repeatedly, which means they "
            f"are looping rather than working: "
            f"{[(step, count) for (_, step), count in list(looping.items())[:5]]}",
        )


if __name__ == "__main__":
    unittest.main()
