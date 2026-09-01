"""The screen tells the player who they are, and the log tells them what happened.

Nothing on the main screen named the character - not the HUD, not the status
panel, not even the character sheet - and the message log was 90-odd percent
developer diagnostics, which pushed real events straight off a four-line panel.
"""

import unittest

import main
from config import SCREEN_HEIGHT, SCREEN_WIDTH
from engine import World
from presentation import message_log
from rendering import console_renderer
from tcod_compat import tcod


def _rendered_rows(console) -> list[str]:
    return [
        "".join(chr(console.ch[x, y]) if console.ch[x, y] else " " for x in range(SCREEN_WIDTH))
        for y in range(SCREEN_HEIGHT)
    ]


class TestPlayerIdentityIsVisible(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Aldric")
        cls.world._pre_simulate_world()
        main._ensure_zoom_state(cls.world)
        cls.first_name = "Aldric"

    def _draw_world(self):
        console = tcod.console.Console(SCREEN_WIDTH, SCREEN_HEIGHT, order="F")
        camera_x, camera_y = main._get_camera_origin(self.world)
        console_renderer.draw(console, self.world, camera_x, camera_y, menu_fade_ratio=1.0)
        return _rendered_rows(console)

    def test_the_player_is_named_on_the_main_screen(self):
        rows = self._draw_world()
        self.assertTrue(
            any(self.first_name in row for row in rows),
            "the player's name appears nowhere on the main screen",
        )

    def test_the_status_panel_shows_name_and_profession(self):
        rows = self._draw_world()
        panel = [row[console_renderer.MAP_WIDTH:] for row in rows]
        self.assertTrue(any(self.first_name in row for row in panel), "name missing from the panel")
        self.assertTrue(
            any(self.world.player.economic.profession in row for row in panel),
            "profession missing from the panel",
        )

    def test_the_character_sheet_leads_with_the_character(self):
        console = tcod.console.Console(SCREEN_WIDTH, SCREEN_HEIGHT, order="F")
        console_renderer.draw_info_menu(console, self.world)
        rows = _rendered_rows(console)
        for expected in ("Name", self.first_name, "Profession", "Coin"):
            self.assertTrue(
                any(expected in row for row in rows),
                f"{expected!r} missing from the character sheet",
            )


class TestControlsAreDiscoverable(unittest.TestCase):
    """The keys existed only in a help menu you had to know a key to open."""

    def test_the_status_legend_lists_the_main_keys(self):
        console = tcod.console.Console(SCREEN_WIDTH, SCREEN_HEIGHT, order="F")
        console_renderer._draw_status_legend(
            console, console_renderer.MAP_WIDTH, console_renderer.STATUS_PANEL_WIDTH
        )
        text = " ".join(_rendered_rows(console))
        for key in ("E act", "T talk", "I sheet", "U bag", "L look", "? help"):
            self.assertIn(key, text, f"{key!r} is not shown in the status legend")

    def test_the_legend_height_matches_its_contents(self):
        self.assertEqual(
            console_renderer.STATUS_LEGEND_ROWS,
            len(console_renderer.STATUS_LEGEND_ROWS_CONTENT) + 1,
        )


class TestLogHidesDeveloperDiagnostics(unittest.TestCase):
    def test_debug_entries_are_hidden_by_default(self):
        entries = []
        message_log.append_message(entries, "You pick up a loaf.", tick=1)
        message_log.append_message(
            entries, "Debug: someone is considering courting someone",
            category=message_log.DEBUG_CATEGORY, tick=1,
        )
        visible = message_log.visible_entries(entries)
        self.assertEqual([entry.text for entry in visible], ["You pick up a loaf."])

    def test_debug_entries_can_be_shown_on_request(self):
        entries = []
        message_log.append_message(
            entries, "Debug: something", category=message_log.DEBUG_CATEGORY, tick=1
        )
        self.assertEqual(len(message_log.visible_entries(entries, include_debug=True)), 1)

    def test_world_generation_chatter_is_filed_as_debug(self):
        world = World(player_first_name="Aldric")
        world._pre_simulate_world()
        visible = message_log.visible_entries(world.chat_log_entries)
        for entry in visible:
            self.assertNotIn("Generated Villager", entry.text)
            self.assertNotIn("Debug:", entry.text)
            self.assertNotIn("LLM failed", entry.text)

    def test_the_log_panel_honours_the_debug_flag(self):
        world = World(player_first_name="Aldric")
        world._pre_simulate_world()
        hidden = len(console_renderer._get_log_entries(world))
        world.show_debug_log = True
        shown = len(console_renderer._get_log_entries(world))
        self.assertGreater(shown, hidden, "the debug flag did not reveal anything")
        self.assertEqual(shown, len(world.chat_log_entries))


if __name__ == "__main__":
    unittest.main()
