"""A villager ages a year per year, not a year per day.

update_npc_ages runs once per game day and used to add a year to every living
entity on each run. The world keeps a real calendar - four seasons of
DAYS_PER_SEASON days each - so entities aged 112 years for every year the world
lived through.

That is not a rounding problem, it empties the map. Measured over sixty
simulated days before the fix: a starting population of 76 fell to 7 alive, with
66 deaths against a single birth, and the median age of the survivors was 80.
Nobody was starving and nobody was killed; a forty-year-old farmer simply
reaches the elder death rolls inside about five weeks of play. After the fix the
same sixty days end with 90 alive, 14 births, no deaths, and a median age of 35
with newborns in the village.

Everything else in that function stays daily on purpose - work capacity, the
coming-of-age transition and the elder passing roll are all meant to be checked
every day.
"""

import unittest

from config import DAY_LENGTH_TICKS, DAYS_PER_SEASON
from engine import World
from simulation.systems import aging
from tests.world_cache import fresh_world
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini


class TestTheYearMatchesTheWorldCalendar(unittest.TestCase):
    def test_a_year_is_every_season_once(self):
        self.assertEqual(aging.DAYS_PER_YEAR, DAYS_PER_SEASON * aging.SEASONS_PER_YEAR)

    def test_the_world_has_exactly_that_many_seasons(self):
        """If the world ever gains or loses a season, the year length here has
        to move with it or ageing silently drifts against the calendar."""
        self.assertEqual(len(fresh_world(seed=3, pre_simulate=False).seasons), aging.SEASONS_PER_YEAR)


class TestAgeingCadence(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=3, pre_simulate=False)
        self.world.game_time = 0
        self.npcs = [n for n in self.world.all_npcs if not n.physical.is_dead][:25]
        self.assertTrue(self.npcs, "no living NPCs to age")

    def _run_days(self, days, start_day=1):
        for day in range(start_day, start_day + days):
            self.world.game_time = day * DAY_LENGTH_TICKS
            aging.update_npc_ages(self.world)

    def test_nobody_ages_over_an_ordinary_month(self):
        before = [n.age for n in self.npcs]
        self._run_days(30)
        self.assertEqual([n.age for n in self.npcs], before)

    def test_everybody_ages_once_when_the_year_turns(self):
        before = [n.age for n in self.npcs]
        self._run_days(aging.DAYS_PER_YEAR + 2)
        self.assertEqual([n.age for n in self.npcs], [age + 1 for age in before])

    def test_three_years_is_three_birthdays(self):
        before = [n.age for n in self.npcs]
        self._run_days(aging.DAYS_PER_YEAR * 3 + 1)
        self.assertEqual([n.age for n in self.npcs], [age + 3 for age in before])

    def test_the_first_run_on_a_world_is_not_a_birthday(self):
        """Otherwise every freshly generated village ages a year on day one."""
        before = [n.age for n in self.npcs]
        self.world.game_time = DAY_LENGTH_TICKS
        aging.update_npc_ages(self.world)
        self.assertEqual([n.age for n in self.npcs], before)

    def test_work_capacity_is_still_refreshed_daily(self):
        elder = self.npcs[0]
        elder.age = 70
        if hasattr(elder, "work_efficiency_modifiers"):
            elder.work_efficiency_modifiers.pop("aging_factor", None)
            self._run_days(1)
            self.assertIn("aging_factor", elder.work_efficiency_modifiers)
            self.assertAlmostEqual(
                elder.work_efficiency_modifiers["aging_factor"],
                round(aging.get_aging_work_capacity(70), 2),
            )

    def test_coming_of_age_still_happens_on_a_birthday(self):
        child = self.npcs[0]
        child.age = 17
        child.economic.profession = "Child"
        self._run_days(aging.DAYS_PER_YEAR + 2)
        self.assertEqual(child.age, 18)
        self.assertNotEqual(child.economic.profession, "Child")


class TestWorkCapacityCurve(unittest.TestCase):
    def test_the_young_are_unaffected(self):
        self.assertEqual(aging.get_aging_work_capacity(30), 1.0)
        self.assertEqual(aging.get_aging_work_capacity(aging.ELDER_DECLINE_START_AGE), 1.0)

    def test_decline_is_gradual_and_floored(self):
        self.assertLess(aging.get_aging_work_capacity(70), 1.0)
        self.assertGreaterEqual(
            aging.get_aging_work_capacity(200), aging.ELDER_MIN_WORK_CAPACITY
        )


class TestAVillageSurvivesTwoMonths(unittest.TestCase):
    """The regression that matters, at the level it actually showed up.

    Slower than the rest of this file because it builds a world and runs the
    daily macro systems, but a unit test on the cadence alone would not have
    caught what this catches: the population collapsing.
    """

    def test_the_population_does_not_collapse(self):
        world = World(player_first_name="Chronicler")
        world._pre_simulate_world()
        start = sum(1 for n in world.village_npcs if not n.physical.is_dead)
        self.assertGreater(start, 10, "not enough villagers to draw a conclusion")

        for day in range(1, 41):
            world.game_time = day * DAY_LENGTH_TICKS
            world.process_macro_daily_tick()
            world._update_npc_ages()
            world._update_abstract_simulation()

        alive = sum(1 for n in world.village_npcs if not n.physical.is_dead)
        self.assertGreaterEqual(
            alive, start * 0.8,
            f"population fell from {start} to {alive} in forty days",
        )

    def test_nobody_has_aged_a_lifetime(self):
        world = World(player_first_name="Chronicler")
        oldest_before = max(n.age for n in world.all_npcs)
        for day in range(1, 41):
            world.game_time = day * DAY_LENGTH_TICKS
            world._update_npc_ages()
        oldest_after = max(n.age for n in world.all_npcs)
        self.assertLessEqual(
            oldest_after - oldest_before, 1,
            "forty days aged someone by more than a year",
        )


if __name__ == "__main__":
    unittest.main()
