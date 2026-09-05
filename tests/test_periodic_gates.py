"""The same span of game time costs the same, however the clock got there.

Every system that runs on an interval shorter than a day used to ask
`game_time % interval == 0`, which tests for landing exactly on a boundary
rather than for time having passed. game_time does not only advance by one: a
player action costs its own ticks, and lying down to sleep advances a third of a
day in a single step.

Measured over 4800 ticks - eight hours - of game time, reached three ways:

    tick by tick                       hunger 15.0   thirst 35.0
    one 8-hour sleep                   hunger  0.0   thirst  7.0
    577-tick steps (never aligns)      hunger  0.0   thirst  0.0

Sleeping through the night was free, and a save whose clock had drifted off the
boundaries stopped making the player hungry at all. Survival is the core loop of
this game and it could be switched off by accident.

World.periods_elapsed returns a count rather than a boolean so callers apply what
was missed instead of dropping it, bounded by max_catch_up so a very large jump
cannot deliver hundreds of points of starvation damage in one tick.
"""

import unittest

from config import DAY_LENGTH_TICKS
from engine import World
from simulation.systems import survival
from tests.world_cache import fresh_world


class TestPeriodsElapsed(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=808, pre_simulate=False)
        self.world.game_time = 0

    def test_a_new_key_is_due_immediately(self):
        """The boundary test it replaces fired within one interval of anything
        becoming relevant, so deferring the first firing by a whole interval
        would itself be a behaviour change."""
        self.assertEqual(self.world.periods_elapsed("thing", 100), 1)

    def test_nothing_more_until_the_interval_has_passed(self):
        self.world.periods_elapsed("thing", 100)
        self.world.game_time += 99
        self.assertEqual(self.world.periods_elapsed("thing", 100), 0)

    def test_one_period_when_the_interval_passes(self):
        self.world.periods_elapsed("thing", 100)
        self.world.game_time += 100
        self.assertEqual(self.world.periods_elapsed("thing", 100), 1)

    def test_a_jump_reports_everything_it_skipped(self):
        self.world.periods_elapsed("thing", 100)
        self.world.game_time += 850
        self.assertEqual(self.world.periods_elapsed("thing", 100), 8)

    def test_a_jump_that_lands_off_the_boundary_still_counts(self):
        """The whole point: nothing here is ever a multiple of the interval."""
        self.world.game_time = 7
        self.world.periods_elapsed("thing", 100)
        self.world.game_time += 353
        self.assertEqual(self.world.periods_elapsed("thing", 100), 3)

    def test_the_remainder_is_carried_rather_than_lost(self):
        self.world.periods_elapsed("thing", 100)
        self.world.game_time += 150
        self.assertEqual(self.world.periods_elapsed("thing", 100), 1)
        self.world.game_time += 50
        self.assertEqual(self.world.periods_elapsed("thing", 100), 1)

    def test_catch_up_is_bounded(self):
        self.world.periods_elapsed("thing", 10)
        self.world.game_time += 100000
        self.assertEqual(self.world.periods_elapsed("thing", 10, max_catch_up=12), 12)

    def test_systems_do_not_consume_each_other_turns(self):
        self.world.periods_elapsed("hunger", 100)
        self.world.periods_elapsed("thirst", 100)
        self.world.game_time += 100
        self.assertEqual(self.world.periods_elapsed("hunger", 100), 1)
        self.assertEqual(self.world.periods_elapsed("thirst", 100), 1)

    def test_a_clock_that_goes_backwards_does_not_fire(self):
        self.world.game_time = 5000
        self.world.periods_elapsed("thing", 100)
        self.world.game_time = 100
        self.assertEqual(self.world.periods_elapsed("thing", 100), 0)

    def test_it_survives_a_world_saved_before_the_gate_existed(self):
        del self.world._periodic_gate_ticks
        self.assertEqual(self.world.periods_elapsed("thing", 100), 1)
        self.world.game_time += 100
        self.assertEqual(self.world.periods_elapsed("thing", 100), 1)


def _needs_after(step, total_ticks=DAY_LENGTH_TICKS // 3):
    """Player hunger and thirst after `total_ticks` of game time, taken in `step`s."""
    world = fresh_world(seed=808, pre_simulate=False)
    world.game_time = 0
    world.player.physical.hunger = 0
    world.player.physical.thirst = 0
    survival.update_player_needs(world)  # the game ticks before the player sleeps
    elapsed = 0
    while elapsed < total_ticks:
        world.game_time += step
        elapsed += step
        survival.update_player_needs(world)
    return world.player.physical.hunger, world.player.physical.thirst


class TestSleepingThroughTheNightIsNotFree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = _needs_after(1)

    def test_the_baseline_actually_moves(self):
        hunger, thirst = self.baseline
        self.assertGreater(hunger, 0, "eight hours of ticking made the player no hungrier")
        self.assertGreater(thirst, 0)

    def test_one_long_sleep_costs_the_same_as_ticking_through_it(self):
        self.assertEqual(_needs_after(DAY_LENGTH_TICKS // 3), self.baseline)

    def test_costly_actions_cost_the_same(self):
        self.assertEqual(_needs_after(600), self.baseline)

    def test_a_clock_that_never_lands_on_a_boundary_still_costs(self):
        """577 shares no factor with the hunger or thirst intervals, so under the
        old boundary test this player never got hungry or thirsty at all."""
        self.assertEqual(_needs_after(577, total_ticks=(DAY_LENGTH_TICKS // 3))[0],
                         self.baseline[0])


class TestStarvationStillBites(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=808, pre_simulate=False)
        self.world.game_time = 0
        self.player = self.world.player
        self.player.physical.hunger = self.player.physical.max_hunger
        survival.update_player_needs(self.world)

    def test_a_starving_player_takes_damage_across_a_sleep(self):
        hp_before = self.player.combat.hp
        self.world.game_time += DAY_LENGTH_TICKS // 3
        survival.update_player_needs(self.world)
        self.assertLess(
            self.player.combat.hp, hp_before,
            "sleeping eight hours while starving cost no health at all",
        )

    def test_the_damage_is_bounded_by_the_catch_up_cap(self):
        """A very large jump must not deliver a lifetime of starvation at once."""
        hp_before = self.player.combat.hp
        self.world.game_time += DAY_LENGTH_TICKS * 40
        survival.update_player_needs(self.world)
        self.assertGreaterEqual(
            hp_before - self.player.combat.hp, 1,
            "forty days of starvation did nothing",
        )
        # Forty days is 800 starvation intervals. Bounded, it lands in the low
        # teens; the exact number is not the point and depends on how many times
        # the gate was touched on the way, so this asserts the property rather
        # than an arithmetic identity.
        self.assertLess(
            hp_before - self.player.combat.hp, 50,
            "forty days of starvation was applied all at once, unbounded",
        )


class TestTheRestOfTheWorldKeepsItsCadence(unittest.TestCase):
    """The other systems that ran on a boundary test rather than on elapsed time.

    Each of these accumulates something - money, water, regrowth - so missing a
    period is not a dropped frame, it is a day the town collected no taxes or a
    night the forest did not grow back.
    """

    def setUp(self):
        self.world = World(player_first_name="Gov")
        self.world._pre_simulate_world()
        self.world.game_time = 0

    def test_governance_runs_once_a_day_even_on_a_clock_that_never_lands_on_it(self):
        """DAILY_GOVERNANCE_TICK_OFFSET says *when* in the day, not "only on that
        exact tick". Jumps here are a third of a day plus one, so the clock never
        hits the offset."""
        self.world.politics.last_governance_day = -1
        if self.world.get_town_hall_building() is None:
            self.skipTest("this world generated no town hall to govern from")

        runs = 0
        for _ in range(10 * 3):
            self.world.game_time += DAY_LENGTH_TICKS // 3 + 1
            before = self.world.politics.last_governance_day
            self.world._run_daily_governance()
            if self.world.politics.last_governance_day != before:
                runs += 1

        self.assertGreaterEqual(runs, 9, f"governance ran {runs} times in ten days")
        self.assertLessEqual(runs, 11, f"governance ran {runs} times in ten days")

    def _stocked_region(self):
        """A region with its resource stocks initialised.

        Worth knowing while reading these two: nothing in the game currently
        calls get_resource_availability or consume_resource, so
        EcologyManager.regional_resources is empty in a real world and this
        regrowth never runs. The gate it used was wrong in the same way as all
        the others and is fixed for consistency, but the system it belongs to is
        not wired up to anything - a Woodcutter does not draw down regional wood.
        These initialise a region by hand so the mechanism is still covered.
        """
        ecology = getattr(self.world, "ecology", None)
        regions = getattr(getattr(self.world, "atlas", None), "regions_by_id", {})
        if ecology is None or not regions:
            self.skipTest("this world has no regions")
        region_id = next(iter(regions))
        ecology.get_resource_availability(self.world, region_id, "wood")
        self.assertIn(
            region_id, ecology.regional_resources,
            "asking for a region's resources did not initialise them",
        )
        return ecology, region_id

    def test_the_forest_grows_back_across_a_night_of_sleep(self):
        ecology, region_id = self._stocked_region()
        ecology.regional_resources[region_id]["wood"] = 0

        ecology.process_tick(self.world)          # establishes the baseline
        self.world.game_time += 5000              # never a multiple of 1000 from here
        self.world.game_time += 1
        ecology.process_tick(self.world)

        self.assertGreater(
            ecology.regional_resources[region_id]["wood"], 0,
            "five thousand ticks passed and the forest grew nothing back",
        )

    def test_regrowth_is_bounded_after_an_enormous_jump(self):
        ecology, region_id = self._stocked_region()
        ecology.regional_resources[region_id]["wood"] = 0

        ecology.process_tick(self.world)
        self.world.game_time += 10_000_000
        ecology.process_tick(self.world)

        # Ten million ticks is ten thousand regrowth periods, which unbounded
        # would be 50,000 wood. Bounded it lands near 5 * max_catch_up; the exact
        # figure depends on how many times the gate was touched getting there, so
        # this asserts the property rather than an arithmetic identity.
        self.assertLess(
            ecology.regional_resources[region_id]["wood"], 1000,
            "a huge jump regrew an unbounded amount of wood in one tick",
        )


if __name__ == "__main__":
    unittest.main()
