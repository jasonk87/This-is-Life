"""Look Mode: a cursor the player can see, and a way through a crowded tile.

Look Mode reported a pair of world coordinates and nothing else, so there was no
way to tell which tile it was pointing at, and its one-line summary could only
ever describe the first thing standing there.
"""

import unittest

import main
from config import SCREEN_HEIGHT, SCREEN_WIDTH
from engine import World
from presentation.sensory_observation import (
    describe_focus_target,
    list_tile_focus_targets,
    observe_focus_target,
    short_entity_label,
)
from rendering import console_renderer
from tcod_compat import tcod


def _key(sym):
    return tcod.event.KeyDown(sym=sym, scancode=0, mod=0)


# Consoles here come from main.create_console(), never built inline.
#
# These tests used to construct tcod.console.Console(..., order="F") and then
# index the result as console.bg[y, x]. The game builds its console with
# order="C", where the buffers are shaped (height, width, 3) and [y, x] is
# correct; under order="F" they are shaped (width, height, 3) and the same
# subscript reads a different cell entirely. So the assertions were checking a
# transposed buffer against a console the game never uses, and whether they
# happened to hold depended on where the cursor was and what the world had
# generated - which is why they passed in isolation and failed about one full
# run in two.


class TestLookCursor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)

    def setUp(self):
        main.enter_look_mode(self.world)

    def test_look_mode_starts_on_the_player(self):
        self.assertEqual(self.world.game_state, "LOOK_MODE")
        self.assertEqual(
            (self.world.look_cursor_x, self.world.look_cursor_y),
            (self.world.player.x, self.world.player.y),
        )

    def test_cursor_cannot_leave_the_visible_view(self):
        world = self.world
        for sym in (
            tcod.event.KeySym.RIGHT,
            tcod.event.KeySym.LEFT,
            tcod.event.KeySym.UP,
            tcod.event.KeySym.DOWN,
        ):
            main.enter_look_mode(world)
            for _ in range(200):
                main.handle_look_mode_input(_key(sym), world)

            camera_x, camera_y = main._get_camera_origin(world)
            view_width, view_height = main._get_world_view_size(world)
            self.assertTrue(
                camera_x <= world.look_cursor_x <= camera_x + view_width - 1
                and camera_y <= world.look_cursor_y <= camera_y + view_height - 1,
                f"cursor at {(world.look_cursor_x, world.look_cursor_y)} left the view",
            )

    def test_cursor_always_has_somewhere_on_screen_to_be_drawn(self):
        world = self.world
        for _ in range(200):
            main.handle_look_mode_input(_key(tcod.event.KeySym.RIGHT), world)
            main.handle_look_mode_input(_key(tcod.event.KeySym.DOWN), world)
        camera_x, camera_y = main._get_camera_origin(world)
        self.assertIsNotNone(
            console_renderer._world_to_screen_rect(
                world, camera_x, camera_y, world.look_cursor_x, world.look_cursor_y
            )
        )

    def test_cursor_is_painted_onto_the_map(self):
        world = self.world
        console = main.create_console()
        camera_x, camera_y = main._get_camera_origin(world)
        rect = console_renderer._world_to_screen_rect(
            world, camera_x, camera_y, world.look_cursor_x, world.look_cursor_y
        )
        self.assertIsNotNone(rect)

        console_renderer.draw(console, world, camera_x, camera_y, menu_fade_ratio=1.0)
        x0, y0, _, _ = rect
        self.assertEqual(
            tuple(console.bg[y0, x0]),
            console_renderer.LOOK_CURSOR_BG,
            "the cursor tile is not highlighted",
        )

    def test_nothing_is_painted_when_not_looking(self):
        world = self.world
        world.game_state = "PLAYING"
        console = main.create_console()
        camera_x, camera_y = main._get_camera_origin(world)
        rect = console_renderer._world_to_screen_rect(
            world, camera_x, camera_y, world.look_cursor_x, world.look_cursor_y
        )
        console_renderer.draw(console, world, camera_x, camera_y, menu_fade_ratio=1.0)
        x0, y0, _, _ = rect
        self.assertNotEqual(tuple(console.bg[y0, x0]), console_renderer.LOOK_CURSOR_BG)


class TestLookFocusCycling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)

    def setUp(self):
        main.enter_look_mode(self.world)
        # A tile with several things on it: two item stacks over whatever the
        # player's own square already holds.
        self.tile = (self.world.player.x, self.world.player.y)
        self.world.drop_item_on_map("bread", 3, *self.tile)
        self.world.drop_item_on_map("axe_stone", 1, *self.tile)
        self.world.look_cursor_x, self.world.look_cursor_y = self.tile
        self.world.look_focus_index = 0

    def test_each_item_stack_is_its_own_target(self):
        labels = [
            describe_focus_target(self.world, target)
            for target in main.get_look_focus_targets(self.world)
            if target["type"] == "item"
        ]
        self.assertIn("[3x Bread]", labels)
        self.assertIn("[1x Stone Axe]", labels)

    def test_tab_cycles_through_everything_and_wraps(self):
        world = self.world
        targets = main.get_look_focus_targets(world)
        self.assertGreater(len(targets), 1, "test tile is not shared")

        seen = []
        for _ in range(len(targets)):
            seen.append(main.get_look_focus_target(world))
            main.handle_look_mode_input(_key(tcod.event.KeySym.TAB), world)

        self.assertEqual(len(seen), len(targets))
        self.assertEqual([t["name"] for t in seen], [t["name"] for t in targets])
        # One more Tab is back where it started.
        self.assertEqual(main.get_look_focus_target(world)["name"], targets[0]["name"])

    def test_moving_the_cursor_resets_the_focus(self):
        world = self.world
        main.handle_look_mode_input(_key(tcod.event.KeySym.TAB), world)
        self.assertNotEqual(world.look_focus_index, 0)
        main.handle_look_mode_input(_key(tcod.event.KeySym.RIGHT), world)
        self.assertEqual(world.look_focus_index, 0)

    def test_the_ground_itself_is_focused_last(self):
        targets = main.get_look_focus_targets(self.world)
        self.assertEqual(targets[-1]["type"], "tile")

    def test_every_target_can_be_examined(self):
        for index in range(len(main.get_look_focus_targets(self.world))):
            self.world.look_focus_index = index
            target = main.get_look_focus_target(self.world)
            detail = observe_focus_target(self.world, target)
            self.assertTrue(detail and detail.strip(), f"{target['type']} examined to nothing")


class TestHelpMenu(unittest.TestCase):
    """Look Mode was unreachable by anyone who did not already know the key."""

    def test_look_mode_is_documented(self):
        controls = dict(console_renderer.HELP_CONTROLS)
        self.assertIn("Look Around", controls)
        self.assertEqual(controls["Look Around"], "L")

    def test_the_panel_is_tall_enough_for_every_control(self):
        console = main.create_console()
        console_renderer.draw_help_menu(console)

        rendered = set()
        for y in range(SCREEN_HEIGHT):
            # [y, x]: create_console builds order="C" buffers, shaped
            # (height, width). This read [x, y] back when the console here was
            # built inline as order="F", which was right for that console and is
            # wrong for the one the game actually draws into.
            row = "".join(
                chr(console.ch[y, x]) if console.ch[y, x] else " " for x in range(SCREEN_WIDTH)
            )
            rendered.add(row.strip())
        for action, key in console_renderer.HELP_CONTROLS:
            self.assertTrue(
                any(action in row for row in rendered),
                f"{action!r} does not fit in the help panel",
            )


class TestEntityLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def test_animals_are_named_by_species(self):
        animals = [
            npc
            for npc in self.world.npcs
            if getattr(npc, "animal_type", None) and not npc.physical.is_dead
        ]
        self.assertGreater(len(animals), 0, "generated world has no wildlife")
        for animal in animals:
            label = short_entity_label(self.world, animal)
            self.assertIn(
                animal.animal_type.replace("_", " ").title(),
                label,
                f"a {animal.animal_type} is labelled {label!r}",
            )
            # Regression: animals used to fall through the person-describing
            # branch and come out as anonymous strangers.
            self.assertNotIn("Stranger", label)

    def test_empty_tile_focus_reports_nothing_rather_than_failing(self):
        self.assertEqual(describe_focus_target(self.world, None), "[Nothing of note]")
        self.assertEqual(
            observe_focus_target(self.world, None), "There is nothing here to examine."
        )

    def test_focus_targets_off_the_map_are_empty(self):
        self.assertEqual(list_tile_focus_targets(self.world, -5, -5), [])


if __name__ == "__main__":
    unittest.main()
