"""The world keeps rendering while it is running.

Nothing in the suite advanced the world and drew it. Three files call
run_world_tick and none of them render; test_render_stress renders hard - every
zoom, every menu, every corner - but always draws a world that has just been
generated and never ticked.

That gap is the exact shape of the two faults that started this work: a crash on
startup and a crash on right-click, both of them the live world handing the UI
something it could not deal with. A renderer only ever pointed at a fresh world
never meets a corpse on the ground, a newborn with no job, a merchant halfway
between villages, dusk turning into night, or an inventory that has spoiled.

So this ticks the world for real and draws frames as it goes. It is deliberately
slower than a unit test and deliberately shallow on assertions: the point is that
nothing raises and the view keeps having something in it, across states no
fixture would think to construct.
"""

import unittest

import numpy as np

import main
from config import MAP_HEIGHT, MAP_WIDTH
from engine import World
from rendering import console_renderer as cr
from simulation.systems.tick import run_world_tick

TICKS = 900
DRAW_EVERY = 60
ZOOMS = (0, 1, 2)


class TestTickingWorldStillDraws(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Runner")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)
        cls.console = main.create_console()

        cls.frames = []
        cls.failures = []
        for tick in range(TICKS):
            run_world_tick(cls.world)
            if tick % DRAW_EVERY:
                continue
            cls.world.zoom_index = ZOOMS[(tick // DRAW_EVERY) % len(ZOOMS)]
            cls.world.game_state = "PLAYING"
            camera_x, camera_y = main._get_camera_origin(cls.world)
            cls.console.clear()
            try:
                cr.draw(cls.console, cls.world, camera_x, camera_y, menu_fade_ratio=1.0)
            except Exception as exc:  # noqa: BLE001 - the whole point is to catch any
                cls.failures.append((tick, repr(exc)))
                continue
            cls.frames.append({
                "tick": tick,
                "light": getattr(cls.world, "current_light_level_name", "?"),
                "season": cr.current_season_name(cls.world),
                "weather": getattr(cls.world, "weather", "?"),
                "glyphs": int((cls.console.ch[:MAP_HEIGHT, :MAP_WIDTH] != 32).sum()),
                "fg_sum": int(cls.console.fg[:MAP_HEIGHT, :MAP_WIDTH].sum()),
                "alive": sum(1 for n in cls.world.village_npcs if not n.physical.is_dead),
            })

    def test_nothing_raised_while_drawing_a_running_world(self):
        self.assertEqual(
            self.failures, [],
            "drawing a world that had been ticked raised: "
            + "; ".join(f"tick {t}: {e}" for t, e in self.failures),
        )

    def test_frames_were_actually_drawn(self):
        self.assertGreaterEqual(len(self.frames), TICKS // DRAW_EVERY - 1)

    def test_the_view_is_never_empty(self):
        """A frame with nothing in it is the failure mode a try/except would
        otherwise hide - no exception, no picture."""
        for frame in self.frames:
            self.assertGreater(
                frame["glyphs"], 0,
                f"the map had no glyphs at all at tick {frame['tick']}",
            )
            self.assertGreater(
                frame["fg_sum"], 0,
                f"the map was entirely black at tick {frame['tick']}",
            )

    def test_the_world_moved_while_being_drawn(self):
        """Guards the harness: if the world were static, this would be
        test_render_stress again with extra steps."""
        clock = {frame["tick"] for frame in self.frames}
        self.assertGreater(len(clock), 1)
        self.assertGreater(
            self.world.game_time, TICKS - 1,
            "the tick loop did not advance the clock",
        )

    def test_the_population_survived_being_watched(self):
        alive = [frame["alive"] for frame in self.frames]
        self.assertTrue(alive)
        self.assertGreater(alive[-1], 0, "everyone died during the run")


class TestDrawingAWorldWithTheDead(unittest.TestCase):
    """A corpse on the floor is a state a freshly generated world never has."""

    def setUp(self):
        self.world = World(player_first_name="Runner")
        self.world._pre_simulate_world()
        main._ensure_zoom_state(self.world)
        self.console = main.create_console()

    def _draw(self):
        camera_x, camera_y = main._get_camera_origin(self.world)
        self.console.clear()
        cr.draw(self.console, self.world, camera_x, camera_y, menu_fade_ratio=1.0)

    def test_a_body_next_to_the_player_draws(self):
        player = self.world.player
        victim = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        victim.is_sleeping = False
        self.world._update_entity_position(victim, player.x, player.y)
        victim.physical.is_dead = True
        victim.combat.hp = 0

        self._draw()

        self.assertGreater(int((self.console.ch[:MAP_HEIGHT, :MAP_WIDTH] != 32).sum()), 0)

    def test_a_newborn_next_to_the_player_draws(self):
        """Births only started happening once the daily systems were fixed, so a
        child with no job, no home and an age of zero is genuinely new state for
        the renderer to meet."""
        player = self.world.player
        child = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        child.is_sleeping = False
        child.age = 0
        child.economic.profession = "Child"
        child.schedule.work_building_id = None
        child.schedule.home_building_id = None
        self.world._update_entity_position(child, player.x, player.y)

        self._draw()

        self.assertGreater(int(np.asarray(self.console.fg).sum()), 0)


if __name__ == "__main__":
    unittest.main()
