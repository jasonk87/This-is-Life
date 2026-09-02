"""A month in the life of a village, checked for signs of collapse.

Every one of the worst bugs found in this codebase was invisible to unit tests
and obvious after a few simulated weeks:

* daily systems gated on the clock landing exactly on midnight, so a player who
  slept skipped whole days of births, economy, trade and governance - and once
  the clock drifted off the boundary, forever;
* entities ageing a year per day, which emptied a village of 76 down to 7 inside
  sixty days;
* taxes never collected, because governance wanted one exact tick of the day;
* survival needs that stopped accruing, so sleeping through the night was free.

None of those break a unit test. They break a village, slowly. This runs one and
looks for the shapes of collapse: a population that empties, an economy that
stops moving, money that goes negative, a town that never collects a penny.

Deliberately loose. It is a smoke alarm, not a golden file - the numbers here
have wide margins so that ordinary balance changes do not trip it, and only a
system that has actually stopped working will. The seed is fixed and the
simulation is reproducible (see test_simulation_determinism), so a failure here
can be replayed exactly.
"""

import unittest

from config import DAY_LENGTH_TICKS
from engine import World

DAYS = 30
SEED = 8675309


class TestAVillageSurvivesAMonth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        world = World(seed=SEED)
        world._pre_simulate_world()
        cls.start = cls._snapshot(world)

        for day in range(1, DAYS + 1):
            for _ in range(24):
                world.game_time += DAY_LENGTH_TICKS // 24
                world.process_abstract_simulation()
                world.process_macro_daily_tick()
            world._update_economy()
            world._run_daily_governance()
            world._update_npc_ages()
            world._update_npc_careers()
            world._update_abstract_simulation()

        cls.world = world
        cls.end = cls._snapshot(world)

    @staticmethod
    def _snapshot(world):
        alive = [n for n in world.village_npcs if not n.physical.is_dead]
        hall = world.get_town_hall_building()
        supply = 0
        for row in world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is not None:
                    supply += sum(
                        int(q) for q in (getattr(village, "supply", {}) or {}).values()
                        if isinstance(q, int)
                    )
        return {
            "alive": len(alive),
            "unemployed": sum(1 for n in alive if n.economic.profession == "Unemployed"),
            "money": sum(int(getattr(n.economic, "money", 0) or 0) for n in alive),
            "treasury": int(hall.building_inventory.get("money", 0) or 0) if hall else 0,
            "supply": supply,
            "oldest": max((n.age for n in alive), default=0),
        }

    def test_the_village_is_still_populated(self):
        self.assertGreaterEqual(
            self.end["alive"], self.start["alive"] * 0.75,
            f"population fell from {self.start['alive']} to {self.end['alive']} "
            f"in {DAYS} days",
        )

    def test_nobody_aged_a_lifetime(self):
        """A month is not a generation. This is the shape of the ageing bug: a
        year of life per day of play."""
        self.assertLessEqual(
            self.end["oldest"] - self.start["oldest"], 1,
            f"the oldest villager went from {self.start['oldest']} to "
            f"{self.end['oldest']} in {DAYS} days",
        )

    def test_people_found_work(self):
        self.assertLessEqual(
            self.end["unemployed"], self.start["unemployed"],
            f"unemployment rose from {self.start['unemployed']} to "
            f"{self.end['unemployed']}",
        )

    def test_the_economy_moved(self):
        """Villagers earn and villages accumulate stock. If both are flat, the
        work chains or the abstract economy have stopped running."""
        self.assertGreater(
            self.end["money"] + self.end["supply"],
            self.start["money"] + self.start["supply"],
            "a month passed and the village neither earned nor produced anything",
        )

    def test_the_town_collected_taxes(self):
        """The shape of the governance bug: it wanted one exact tick of the day
        and a jumping clock never landed on it."""
        if self.world.get_town_hall_building() is None:
            self.skipTest("this world generated no town hall")
        self.assertGreater(
            self.end["treasury"], self.start["treasury"],
            "the treasury did not grow in a month, so governance never ran",
        )

    def test_nobody_is_in_debt(self):
        debtors = [
            n for n in self.world.village_npcs
            if not n.physical.is_dead and int(getattr(n.economic, "money", 0) or 0) < 0
        ]
        self.assertEqual(
            debtors, [], f"{len(debtors)} villagers ended the month with negative money"
        )

    def test_children_were_born(self):
        """Not a rate check - just that the birth path is reachable at all. It
        was not, for as long as the daily systems were gated on an exact tick."""
        from simulation.history import BirthRecord

        births = [e for e in self.world.history.events if isinstance(e, BirthRecord)]
        youngest = min(
            (n.age for n in self.world.village_npcs if not n.physical.is_dead),
            default=99,
        )
        self.assertTrue(
            births or youngest < 5,
            f"no child was born in {DAYS} days and the youngest villager is "
            f"{youngest}",
        )


if __name__ == "__main__":
    unittest.main()
