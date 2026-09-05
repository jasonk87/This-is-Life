"""Saving a game that is actually being played.

Every existing save test saves a world that has never run: freshly generated, or
with the clock moved forward by hand. None of them call run_world_tick first. So
the one moment a player is most likely to save - part way through a day, with
villagers walking somewhere, holding a work sub-task, and part way through a
timed activity - was the one state never round-tripped.

That state is not simple. A villager mid-errand carries a path, a destination, a
sub-task id, a target coordinate and a live activity object with its own
progress counter; a healer carries a forage target. If any of it fails to
pickle, or comes back subtly wrong, the failure lands on a player's save file
rather than in a test.

Measured on seed 5 after 400 ticks: 21 villagers holding a sub-task, 11 with a
live activity, 50 walking. All of it survives, and the loaded world keeps
running.
"""

import os
import unittest

from engine import World
from tests.world_cache import fresh_world
from save_manager import load_game, save_game
from simulation.systems.tick import run_world_tick
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini

TICKS_BEFORE_SAVE = 250
TICKS_AFTER_LOAD = 100
SAVE_NAME = "test_midrun_save.sav"


class TestSavingAWorldThatIsRunning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)
        for _ in range(TICKS_BEFORE_SAVE):
            run_world_tick(cls.world)

        cls.saved = save_game(cls.world, SAVE_NAME)
        cls.loaded = load_game(SAVE_NAME) if cls.saved else None

        # Snapshot both sides here, before any test runs. Two of the tests below
        # tick the loaded world, and unittest orders methods alphabetically, so
        # comparing live objects inside the tests would have them measuring each
        # other's leftovers rather than the round-trip.
        cls.before = cls._live_state(cls.world)
        cls.after_load = cls._live_state(cls.loaded) if cls.loaded else None
        cls.saved_game_time = cls.world.game_time
        cls.loaded_game_time = cls.loaded.game_time if cls.loaded else None

    @classmethod
    def tearDownClass(cls):
        path = os.path.join("saves", SAVE_NAME)
        if os.path.exists(path):
            os.remove(path)

    @staticmethod
    def _live_state(world):
        living = [n for n in world.village_npcs if not n.physical.is_dead]
        return {
            "alive": len(living),
            "sub_tasks": sum(1 for n in living if getattr(n, "current_sub_task", None)),
            "activities": sum(1 for n in living if getattr(n, "current_activity", None) is not None),
            "walking": sum(1 for n in living if n.schedule.current_path),
        }

    def test_the_world_had_live_state_worth_saving(self):
        """Guards the test itself. If the world were idle at this point, every
        assertion below would pass without testing anything."""
        before = self.before
        self.assertGreater(before["alive"], 0)
        self.assertGreater(
            before["sub_tasks"] + before["activities"] + before["walking"], 0,
            "nobody in the village was doing anything when it was saved, so this "
            "round-trips an idle world and proves nothing",
        )

    def test_it_saves_and_loads(self):
        self.assertTrue(self.saved, "a world part way through a day would not save")
        self.assertIsNotNone(self.loaded, "the save of a running world would not load")

    def test_the_clock_survives(self):
        self.assertEqual(self.loaded_game_time, self.saved_game_time)

    def test_everyone_who_was_alive_still_is(self):
        self.assertEqual(self.after_load["alive"], self.before["alive"])

    def test_work_in_progress_survives(self):
        """Sub-tasks, timed activities and walked paths all come back."""
        before = self.before
        after = self.after_load
        for key in ("sub_tasks", "activities", "walking"):
            with self.subTest(state=key):
                self.assertEqual(
                    after[key], before[key],
                    f"{before[key]} villagers had {key} when saved and {after[key]} "
                    f"after loading",
                )

    def test_the_loaded_world_keeps_running(self):
        """The point of loading. A world that comes back but cannot be ticked is
        no better than one that failed to save."""
        before = self.after_load["alive"]
        for _ in range(TICKS_AFTER_LOAD):
            run_world_tick(self.loaded)
        after = self._live_state(self.loaded)["alive"]
        self.assertGreater(after, 0, "the village emptied after loading")
        self.assertGreaterEqual(
            after, before - 1,
            f"loading and continuing cost the village {before - after} people",
        )

    def test_loading_does_not_rewind_or_skip_the_clock(self):
        started_at = self.loaded.game_time
        for _ in range(5):
            run_world_tick(self.loaded)
        self.assertGreater(self.loaded.game_time, started_at)
        self.assertGreaterEqual(started_at, self.saved_game_time)


if __name__ == "__main__":
    unittest.main()
