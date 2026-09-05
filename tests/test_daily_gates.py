"""A day that passes is a day that gets simulated.

Every daily system in the game used to ask the same question - is game_time
exactly a multiple of DAY_LENGTH_TICKS - which tests for landing precisely on
midnight rather than for a day having gone by. game_time does not only advance
by one. A player action costs its own ticks (simulation/systems/tick.py and
main.py both add `action_cost - 1`) and lying down to sleep jumps a third of a
day in a single step.

Measured over twenty simulated days, counting how many village-days of macro
simulation actually ran out of eighty:

    stepping one tick at a time          80
    sleeping in exact eight-hour jumps   80   (a third of a day still divides a day)
    alternating play and sleep           28
    sleeping, then one action             0

The last row is the one that matters. Once game_time carries an offset that is
not a multiple, it never becomes one again, so births, deaths, ageing, the
economy, trade caravans, diplomacy and governance stop happening for the rest of
that save, with nothing said about it.
"""

import random
import unittest

from config import DAY_LENGTH_TICKS
from engine import World
from tests.world_cache import fresh_world
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini


class TestBeginNewDay(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=11, pre_simulate=False)
        self.world.game_time = 0

    def test_it_fires_once_per_day(self):
        self.world.game_time = DAY_LENGTH_TICKS
        self.assertTrue(self.world.begin_new_day("thing"))
        self.assertFalse(self.world.begin_new_day("thing"))
        self.assertFalse(self.world.begin_new_day("thing"))

    def test_the_next_day_fires_again(self):
        self.world.game_time = DAY_LENGTH_TICKS
        self.assertTrue(self.world.begin_new_day("thing"))
        self.world.game_time = DAY_LENGTH_TICKS * 2
        self.assertTrue(self.world.begin_new_day("thing"))

    def test_a_jump_clean_over_midnight_still_counts(self):
        """The whole point. Nothing here ever lands on a multiple."""
        self.world.game_time = DAY_LENGTH_TICKS + 7
        self.assertTrue(self.world.begin_new_day("thing"))
        self.world.game_time = (DAY_LENGTH_TICKS * 2) + 3
        self.assertTrue(self.world.begin_new_day("thing"))

    def test_several_days_skipped_at_once_still_only_fires_once(self):
        self.world.game_time = DAY_LENGTH_TICKS
        self.assertTrue(self.world.begin_new_day("thing"))
        self.world.game_time = DAY_LENGTH_TICKS * 9 + 11
        self.assertTrue(self.world.begin_new_day("thing"))
        self.assertFalse(self.world.begin_new_day("thing"))

    def test_systems_do_not_consume_each_other_turns(self):
        self.world.game_time = DAY_LENGTH_TICKS
        self.assertTrue(self.world.begin_new_day("births"))
        self.assertTrue(self.world.begin_new_day("ageing"))
        self.assertFalse(self.world.begin_new_day("births"))

    def test_the_first_day_is_skipped_by_default(self):
        self.world.game_time = 0
        self.assertFalse(self.world.begin_new_day("thing"))

    def test_callers_that_want_day_zero_can_have_it(self):
        self.world.game_time = 0
        self.assertTrue(self.world.begin_new_day("thing", skip_first_day=False))
        self.assertFalse(self.world.begin_new_day("thing", skip_first_day=False))

    def test_it_survives_a_world_saved_before_the_gate_existed(self):
        del self.world._daily_gate_days
        self.world.game_time = DAY_LENGTH_TICKS
        self.assertTrue(self.world.begin_new_day("thing"))
        self.assertFalse(self.world.begin_new_day("thing"))


def _village_days_simulated(step_pattern, days=12):
    """How many village-days of macro simulation run over `days` of game time."""
    random.seed(5)
    world = World(player_first_name="Sleeper")
    world._pre_simulate_world()
    world.game_time = 0

    runs = []
    original = World._simulate_village_population_lifecycle

    def counting(self, *args, **kwargs):
        runs.append(1)
        return original(self, *args, **kwargs)

    World._simulate_village_population_lifecycle = counting
    try:
        target = days * DAY_LENGTH_TICKS
        index = 0
        while world.game_time < target:
            world.game_time += step_pattern[index % len(step_pattern)]
            index += 1
            world._update_abstract_simulation()
    finally:
        World._simulate_village_population_lifecycle = original

    villages = sum(
        1 for row in world.chunks for chunk in row
        if getattr(chunk, "village", None) is not None
    )
    return len(runs), villages, days


class TestTheWorldKeepsRunningHoweverTimePasses(unittest.TestCase):
    """Slower than the unit tests above - each builds a world - so this checks
    the two patterns that actually broke rather than every combination."""

    def _assert_all_days_ran(self, pattern, label):
        ran, villages, days = _village_days_simulated(pattern)
        self.assertGreaterEqual(
            ran, villages * days,
            f"{label}: only {ran} village-days simulated, expected at least "
            f"{villages * days}",
        )

    def test_playing_tick_by_tick(self):
        self._assert_all_days_ran([1], "tick by tick")

    def test_alternating_ordinary_play_and_sleep(self):
        self._assert_all_days_ran(
            [600, 600, 600, DAY_LENGTH_TICKS // 3], "mixed play and sleep",
        )

    def test_sleeping_and_then_doing_one_thing(self):
        """This one simulated nothing at all before."""
        self._assert_all_days_ran(
            [DAY_LENGTH_TICKS // 3, 1], "sleep then one tick",
        )


if __name__ == "__main__":
    unittest.main()
