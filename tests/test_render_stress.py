"""The renderer survives the whole space it is actually asked to draw.

Drawing one frame, in one state, at one zoom proves very little: the buffer-order
crash this suite's TestConsoleBufferOrder pins only appeared past screen column
56, and lighting faults are invisible in daylight. This walks the combinations.

Consoles here come from main.create_console() rather than being built inline, so
the tests exercise the same row-major [y, x] buffers the game actually draws
into - an inline tcod Console with the wrong `order` would test a console the
game never uses.
"""

import random
import unittest

import main
from config import (
    DAY_LENGTH_TICKS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from engine import World
from rendering import console_renderer as cr

GAME_STATES = (
    "PLAYING",
    "LOOK_MODE",
    "INVENTORY_MENU",
    "INFO_MENU",
    "QUEST_MENU",
    "HELP_MENU",
    "CRAFTING_MENU",
    "BUILDING_MENU",
)


class TestRenderStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)
        cls.console = main.create_console()

    def _draw(self, **state):
        world = self.world
        world.zoom_index = state["zoom_index"]
        world.game_time = state["game_time"]
        # Setting game_time alone does not change the light level: the tick loop
        # calls _update_light_level_and_fov, and nothing else does. Without this
        # every case below rendered at whatever level the world was last left in
        # - which for a fresh world is DAY - so a test named "at every time of
        # day" spent its whole run in daylight, the one condition its own
        # docstring says hides lighting faults.
        world._update_light_level_and_fov()
        world.game_state = state["game_state"]
        world.mouse_x, world.mouse_y = state["mouse"]
        world._update_entity_position(world.player, *state["player"])
        if world.game_state == "LOOK_MODE":
            world.look_cursor_x, world.look_cursor_y = world.player.x, world.player.y
            world.look_focus_index = 0

        original = cr.is_visible
        try:
            if state["everything_visible"]:
                cr.is_visible = lambda *args, **kwargs: True
            camera_x, camera_y = main._get_camera_origin(world)
            self.console.clear()
            cr.draw(self.console, world, camera_x, camera_y, menu_fade_ratio=state["fade"])
        finally:
            cr.is_visible = original

    def test_every_zoom_level_at_every_time_of_day(self):
        for zoom_index in range(len(self.world.zoom_levels)):
            for eighth in range(8):
                with self.subTest(zoom_index=zoom_index, eighth=eighth):
                    self._draw(
                        zoom_index=zoom_index,
                        game_time=int(DAY_LENGTH_TICKS * eighth / 8) + 1,
                        game_state="PLAYING",
                        mouse=(10, 10),
                        player=(self.world.player.x, self.world.player.y),
                        everything_visible=True,
                        fade=1.0,
                    )

    def test_the_map_corners(self):
        """Camera clamping at the edges is where off-by-one bounds show up."""
        corners = [
            (0, 0),
            (WORLD_WIDTH - 1, 0),
            (0, WORLD_HEIGHT - 1),
            (WORLD_WIDTH - 1, WORLD_HEIGHT - 1),
        ]
        for zoom_index in range(len(self.world.zoom_levels)):
            for position in corners:
                with self.subTest(zoom_index=zoom_index, position=position):
                    self._draw(
                        zoom_index=zoom_index,
                        game_time=int(DAY_LENGTH_TICKS * 0.95),
                        game_state="PLAYING",
                        mouse=(10, 10),
                        player=position,
                        everything_visible=True,
                        fade=1.0,
                    )

    def test_the_time_of_day_cases_really_are_different_times_of_day(self):
        """Guards the harness itself.

        _draw used to set game_time and nothing else, and the light level only
        moves when _update_light_level_and_fov is called. Every case below ran in
        daylight while claiming to walk the clock, so the tints and the low-light
        paths were never rendered once.
        """
        seen = []
        for eighth in range(8):
            self._draw(
                zoom_index=0,
                game_time=int(DAY_LENGTH_TICKS * eighth / 8),
                game_state="PLAYING",
                mouse=(10, 10),
                player=(self.world.player.x, self.world.player.y),
                everything_visible=True,
                fade=1.0,
            )
            seen.append(self.world.current_light_level_name)

        self.assertGreaterEqual(
            len(set(seen)), 3,
            f"walking a whole day only ever produced these light levels: {set(seen)}",
        )
        self.assertIn("DAY", seen)
        self.assertTrue(
            {"NIGHT", "PITCH BLACK"} & set(seen),
            f"never got dark at any point in the day: {seen}",
        )

    def test_every_menu_state(self):
        for game_state in GAME_STATES:
            with self.subTest(game_state=game_state):
                self._draw(
                    zoom_index=2,
                    game_time=int(DAY_LENGTH_TICKS * 0.5),
                    game_state=game_state,
                    mouse=(40, 20),
                    player=(self.world.player.x, self.world.player.y),
                    everything_visible=False,
                    fade=1.0,
                )

    def test_a_spread_of_random_configurations(self):
        rng = random.Random(20240607)
        for trial in range(60):
            with self.subTest(trial=trial):
                self._draw(
                    zoom_index=rng.randrange(len(self.world.zoom_levels)),
                    game_time=rng.randrange(DAY_LENGTH_TICKS * 3),
                    game_state=rng.choice(GAME_STATES),
                    mouse=(rng.randrange(SCREEN_WIDTH), rng.randrange(SCREEN_HEIGHT)),
                    player=(rng.randrange(WORLD_WIDTH), rng.randrange(WORLD_HEIGHT)),
                    everything_visible=rng.random() < 0.5,
                    fade=rng.choice([0.3, 1.0]),
                )


class TestRenderInvariants(unittest.TestCase):
    """Things that must hold in every frame, whatever the state."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)
        cls.console = main.create_console()

    def _frame(self, rng):
        world = self.world
        world.zoom_index = rng.randrange(len(world.zoom_levels))
        world.game_time = rng.randrange(DAY_LENGTH_TICKS)
        world.update()
        # The real loop animates every frame before drawing; render_x/render_y
        # is where an entity is actually drawn, and it lags world x/y until it
        # does. A harness that skips this reports the player as missing.
        world.update_animations(0.5)
        camera_x, camera_y = main._get_camera_origin(world)
        self.console.clear()
        cr.draw(self.console, world, camera_x, camera_y, menu_fade_ratio=1.0)
        return camera_x, camera_y

    def test_the_player_is_always_drawn(self):
        rng = random.Random(4242)
        for frame in range(12):
            with self.subTest(frame=frame):
                camera_x, camera_y = self._frame(rng)
                world = self.world
                draw_x = int(round(getattr(world.player, "render_x", world.player.x)))
                draw_y = int(round(getattr(world.player, "render_y", world.player.y)))
                rect = cr._world_to_screen_rect(world, camera_x, camera_y, draw_x, draw_y)
                self.assertIsNotNone(rect, "the player is off their own screen")
                x0, y0, x1, y1 = rect
                block = self.console.ch[y0:y1 + 1, x0:x1 + 1]
                self.assertTrue(
                    (block != ord(" ")).any(),
                    "the player's own cell is blank - they are invisible",
                )

    def test_the_entity_pass_stays_inside_the_map(self):
        """The status column and the log sit outside it and must not be scribbled on."""
        world = self.world
        camera_x, camera_y = main._get_camera_origin(world)
        self.console.clear()
        cr._draw_entities(self.console, world, camera_x, camera_y)

        status_column = self.console.ch[:, cr.MAP_WIDTH:]
        log_strip = self.console.ch[cr.MAP_HEIGHT:, :cr.MAP_WIDTH]
        self.assertEqual(int((status_column != ord(" ")).sum()), 0, "entities drew over the status panel")
        self.assertEqual(int((log_strip != ord(" ")).sum()), 0, "entities drew over the message log")


class TestEntitiesAcrossTheView(unittest.TestCase):
    """An entity anywhere in the view has to be drawable."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)

    def test_an_entity_at_every_column_of_the_view(self):
        world = self.world
        world.zoom_index = 0
        console = main.create_console()
        camera_x, camera_y = main._get_camera_origin(world)
        npc = next(n for n in world.all_npcs if not n.physical.is_dead)
        npc.is_sleeping = False

        original = cr.is_visible
        try:
            cr.is_visible = lambda *args, **kwargs: True
            for screen_x in range(0, cr.MAP_WIDTH, 7):
                with self.subTest(screen_x=screen_x):
                    world._update_entity_position(npc, camera_x + screen_x, camera_y + 8)
                    npc.render_x, npc.render_y = float(npc.x), float(npc.y)
                    console.clear()
                    cr.draw(console, world, camera_x, camera_y, menu_fade_ratio=1.0)
        finally:
            cr.is_visible = original


if __name__ == "__main__":
    unittest.main()
