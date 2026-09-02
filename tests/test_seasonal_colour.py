"""Winter looks like winter.

The seasons are load-bearing in the simulation. They set the base temperature
every entity is measured against (simulation/systems/survival.py), decide which
weather is possible at all (World._update_weather), scale what a Farmer harvests
from 2 in spring to 15 at the autumn harvest, and gate animal mating. But the
only place a season ever reached the player was one word in the HUD, so a winter
that can kill you looked exactly like a summer afternoon.

The wash is composed into the existing time-of-day tint rather than added as a
second pass over the buffers, so firelight still overrides both - a hearth in
January should read as a hearth.

Asserted as relationships between channels, not as exact colours: the point is
that winter is colder-looking than summer and autumn warmer, and pinning the
literal RGB would break on any future tuning of the palette without telling us
anything about whether the seasons are still legible.
"""

import unittest

import numpy as np

import main
from config import DAY_LENGTH_TICKS, MAP_HEIGHT, MAP_WIDTH
from engine import World
from rendering import console_renderer as cr


def _warmth(frame):
    """Red minus blue, averaged. Higher is warmer."""
    channels = frame.reshape(-1, 3).mean(axis=0)
    return float(channels[0] - channels[2])


def _greenness(frame):
    channels = frame.reshape(-1, 3).mean(axis=0)
    return float(channels[1] - (channels[0] + channels[2]) / 2.0)


class TestSeasonTintHelpers(unittest.TestCase):
    def test_an_unknown_season_washes_nothing(self):
        np.testing.assert_array_equal(cr._season_tint_array("Harvest"), np.ones(3))
        np.testing.assert_array_equal(cr._season_tint_array(""), np.ones(3))

    def test_every_season_the_world_defines_has_a_tint(self):
        for season in World(player_first_name="Probe").seasons:
            self.assertIn(
                season, cr.SEASON_TINTS,
                f"the world can be in {season} and the renderer has no wash for it",
            )

    def test_a_world_without_seasons_is_handled(self):
        """The renderer is called with stand-in worlds in other tests, and an
        unguarded read here would fail them for an unrelated reason."""
        self.assertEqual(cr.current_season_name(object()), "")

    def test_an_out_of_range_index_is_handled(self):
        class Stub:
            seasons = ["Spring", "Summer"]
            current_season_index = 9
        self.assertEqual(cr.current_season_name(Stub()), "")

    def test_it_reads_the_season_the_world_is_in(self):
        class Stub:
            seasons = ["Spring", "Summer", "Autumn", "Winter"]
            current_season_index = 2
        self.assertEqual(cr.current_season_name(Stub()), "Autumn")


class TestTheMapChangesWithTheSeason(unittest.TestCase):
    """One world, four frames, captured once and only read afterwards.

    Rendered at midday so the time-of-day wash is neutral and what is left is
    the season alone.
    """

    @classmethod
    def setUpClass(cls):
        world = World(player_first_name="Tester")
        world._pre_simulate_world()
        main._ensure_zoom_state(world)
        console = main.create_console()

        original = cr.is_visible
        cr.is_visible = lambda *args, **kwargs: True
        cls.frames = {}
        cls.full_frames = {}
        try:
            for index, name in enumerate(world.seasons):
                world.current_season_index = index
                world.game_time = int(DAY_LENGTH_TICKS * 0.5)
                # Midday is only actually DAY once the light level is recomputed;
                # game_time on its own does not move it.
                world._update_light_level_and_fov()
                self_check = getattr(world, "current_light_level_name", None)
                assert self_check == "DAY", f"expected midday to be DAY, got {self_check}"
                world.game_state = "PLAYING"
                camera_x, camera_y = main._get_camera_origin(world)
                console.clear()
                cr.draw(console, world, camera_x, camera_y, menu_fade_ratio=1.0)
                cls.frames[name] = console.fg[:MAP_HEIGHT, :MAP_WIDTH].copy().astype(int)
                cls.full_frames[name] = console.fg.copy().astype(int)
        finally:
            cr.is_visible = original

    def test_the_view_actually_changes(self):
        summer = self.frames["Summer"]
        for name in ("Spring", "Autumn", "Winter"):
            changed = int((np.abs(self.frames[name] - summer).sum(axis=2) > 0).sum())
            self.assertGreater(
                changed, MAP_HEIGHT * MAP_WIDTH // 2,
                f"{name} redrew fewer than half the map cells differently from Summer",
            )

    def test_winter_is_colder_looking_than_summer(self):
        self.assertLess(
            _warmth(self.frames["Winter"]), _warmth(self.frames["Summer"]),
            "winter did not read as cooler than summer",
        )

    def test_autumn_is_warmer_looking_than_summer(self):
        self.assertGreater(
            _warmth(self.frames["Autumn"]), _warmth(self.frames["Summer"]),
            "autumn did not read as warmer than summer",
        )

    def test_winter_is_the_coldest_and_autumn_the_warmest(self):
        by_warmth = sorted(self.frames, key=lambda n: _warmth(self.frames[n]))
        self.assertEqual(by_warmth[0], "Winter")
        self.assertEqual(by_warmth[-1], "Autumn")

    def test_spring_is_the_greenest(self):
        greenest = max(self.frames, key=lambda n: _greenness(self.frames[n]))
        self.assertEqual(greenest, "Spring")

    def test_the_wash_stays_inside_the_map(self):
        """The panels report the season in words; they should not be tinted by
        it. _apply_lighting_and_depth writes only the map area, and this is what
        would catch that changing."""
        summer = self.full_frames["Summer"]
        for name in ("Spring", "Autumn", "Winter"):
            outside = np.abs(self.full_frames[name] - summer)
            outside[:MAP_HEIGHT, :MAP_WIDTH] = 0
            self.assertEqual(
                int(outside.sum()), 0,
                f"{name} changed pixels outside the map view",
            )


if __name__ == "__main__":
    unittest.main()
