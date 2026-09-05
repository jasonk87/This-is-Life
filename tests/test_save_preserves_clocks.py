"""Loading a save does not rewind the world's daily clocks.

Two pieces of state were added to World for the daily systems, and both have to
survive a save or loading turns into a way of cheating time:

* `_daily_gate_days` - the day number each daily system last ran for. It replaced
  a test for game_time landing exactly on midnight, which silently skipped whole
  days whenever the player slept or took a costly action. If it did not persist,
  every load would re-run a day that had already happened: another round of
  births, another day of production, another pass of the labour market.

* `_last_aging_year` - which calendar year everyone has already had a birthday
  for. If it did not persist, the first ageing pass after a load would see a
  world with no recorded year and either age everybody again or, worse, do it on
  every single load.

Both live in World.__dict__ and so ride along with the pickle. These tests are
here because that is an implementation detail that a future __getstate__ tidy-up
could quietly drop.
"""

import os
import unittest

from config import DAY_LENGTH_TICKS
from engine import World
from save_manager import load_game, save_game
from simulation.systems import aging
from tests.world_cache import fresh_world


class TestDailyClocksSurviveASave(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=4242, pre_simulate=False)
        self.save_name = "test_clock_save.sav"

    def tearDown(self):
        path = os.path.join("saves", self.save_name)
        if os.path.exists(path):
            os.remove(path)

    def _round_trip(self):
        self.assertTrue(save_game(self.world, self.save_name), "the world did not save")
        loaded = load_game(self.save_name)
        self.assertIsNotNone(loaded, "the world did not load back")
        return loaded

    def test_a_day_already_run_is_not_run_again_after_loading(self):
        self.world.game_time = DAY_LENGTH_TICKS * 5
        self.assertTrue(self.world.begin_new_day("payroll"))

        loaded = self._round_trip()

        self.assertFalse(
            loaded.begin_new_day("payroll"),
            "loading the save let an already-simulated day run a second time",
        )

    def test_the_next_day_still_runs_after_loading(self):
        """The gate has to still open - persisting it must not freeze it."""
        self.world.game_time = DAY_LENGTH_TICKS * 5
        self.world.begin_new_day("payroll")

        loaded = self._round_trip()
        loaded.game_time = DAY_LENGTH_TICKS * 6

        self.assertTrue(loaded.begin_new_day("payroll"))

    def test_each_system_keeps_its_own_place(self):
        self.world.game_time = DAY_LENGTH_TICKS * 5
        self.world.begin_new_day("payroll")

        loaded = self._round_trip()

        self.assertFalse(loaded.begin_new_day("payroll"))
        self.assertTrue(
            loaded.begin_new_day("harvest"),
            "a system that had never run was treated as though it had",
        )

    def test_nobody_has_a_birthday_just_for_loading_the_game(self):
        self.world.game_time = DAY_LENGTH_TICKS * 5
        self.world._update_npc_ages()
        ages_before = {npc.id: npc.age for npc in self.world.all_npcs}

        loaded = self._round_trip()
        loaded.game_time = DAY_LENGTH_TICKS * 6
        loaded._update_npc_ages()

        unchanged = [
            npc for npc in loaded.all_npcs
            if npc.id in ages_before and npc.age != ages_before[npc.id]
        ]
        self.assertEqual(
            unchanged, [],
            f"{len(unchanged)} entities aged a year purely from saving and loading",
        )

    def test_the_year_still_turns_over_after_loading(self):
        self.world.game_time = DAY_LENGTH_TICKS * 5
        self.world._update_npc_ages()
        ages_before = {npc.id: npc.age for npc in self.world.all_npcs}

        loaded = self._round_trip()
        loaded.game_time = DAY_LENGTH_TICKS * (aging.DAYS_PER_YEAR + 5)
        loaded._update_npc_ages()

        aged = [
            npc for npc in loaded.all_npcs
            if npc.id in ages_before and npc.age == ages_before[npc.id] + 1
        ]
        self.assertTrue(aged, "a year passed across a save and nobody got any older")


if __name__ == "__main__":
    unittest.main()
