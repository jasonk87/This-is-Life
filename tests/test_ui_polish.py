"""Tests for the shared UI layer added in the presentation pass:
theme/widgets, the structured message log, light sources, title art, and
menu mouse routing."""

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from runtime_compat import np

import config
import main
import rendering.console_renderer as console_renderer
from presentation import message_log
from rendering import lighting, title_art, widgets
from rendering import ui_theme as theme


class RecordingConsole:
    """Minimal console capturing draw calls, like the fakes in test_ui."""

    def __init__(self, width=100, height=56):
        self.width = width
        self.height = height
        self.print_calls = []
        self.frames = []

    def print(self, **kwargs):
        self.print_calls.append(kwargs)

    def print_box(self, **kwargs):
        self.print_calls.append(kwargs)

    def draw_frame(self, **kwargs):
        self.frames.append(kwargs)

    def strings(self):
        return [call.get("string", "") for call in self.print_calls]


class TestZoomLevels(unittest.TestCase):
    def test_zoom_levels_are_all_whole_numbers(self):
        """Fractional zoom produced screen rects no split sprite could fill,
        so those levels silently fell back to bare ASCII glyphs."""
        for level in config.ZOOM_LEVELS:
            self.assertEqual(level, int(level), f"{level} is not a whole-number zoom")

    def test_default_zoom_index_is_in_range(self):
        self.assertLess(config.DEFAULT_ZOOM_INDEX, len(config.ZOOM_LEVELS))
        self.assertEqual(config.ZOOM_LEVELS[config.DEFAULT_ZOOM_INDEX], 3.0)


class TestMeterWidget(unittest.TestCase):
    def test_meter_splits_fill_and_track_by_value(self):
        console = RecordingConsole()
        widgets.meter(console, 0, 0, 20, "HP", 5, 10, theme.METER_HP)

        fill_color, track_color = theme.METER_HP
        fill = [c for c in console.print_calls if c["fg"] == fill_color]
        track = [c for c in console.print_calls if c["fg"] == track_color]
        self.assertEqual(len(fill[0]["string"]), len(track[0]["string"]))

    def test_meter_keeps_one_filled_cell_when_nearly_empty(self):
        console = RecordingConsole()
        widgets.meter(console, 0, 0, 20, "HP", 1, 999, theme.METER_HP)

        fill_color, _ = theme.METER_HP
        fill = [c for c in console.print_calls if c["fg"] == fill_color]
        self.assertEqual(fill[0]["string"], theme.BAR_CELL)

    def test_meter_at_zero_draws_only_track(self):
        console = RecordingConsole()
        widgets.meter(console, 0, 0, 20, "HP", 0, 10, theme.METER_HP)

        fill_color, _ = theme.METER_HP
        self.assertEqual([c for c in console.print_calls if c["fg"] == fill_color], [])

    def test_meter_readout_stays_inside_its_width(self):
        console = RecordingConsole()
        widgets.meter(console, 4, 0, 20, "HP", 100, 100, theme.METER_HP)

        for call in console.print_calls:
            self.assertLessEqual(call["x"] + len(call["string"]), 4 + 20)


class TestListRegion(unittest.TestCase):
    def setUp(self):
        self.region = widgets.ListRegion(x=10, y=5, width=20, height=4)

    def test_index_at_maps_row_to_list_index_with_scroll(self):
        self.assertEqual(self.region.index_at(12, 5, 0, 10), 0)
        self.assertEqual(self.region.index_at(12, 7, 0, 10), 2)
        self.assertEqual(self.region.index_at(12, 5, 3, 10), 3)

    def test_index_at_returns_none_outside_the_region(self):
        self.assertIsNone(self.region.index_at(2, 6, 0, 10))
        self.assertIsNone(self.region.index_at(12, 99, 0, 10))

    def test_index_at_returns_none_past_the_end_of_a_short_list(self):
        """Clicking the empty padding below a short list must do nothing,
        not re-select the last entry."""
        self.assertIsNone(self.region.index_at(12, 8, 0, 2))

    def test_index_at_tolerates_missing_mouse_position(self):
        self.assertIsNone(self.region.index_at(None, None, 0, 10))


class TestClampScroll(unittest.TestCase):
    def test_scrolls_up_to_reveal_selection_above_the_window(self):
        self.assertEqual(widgets.clamp_scroll(2, 5, 4), 2)

    def test_scrolls_down_to_reveal_selection_below_the_window(self):
        self.assertEqual(widgets.clamp_scroll(9, 0, 4), 6)

    def test_leaves_offset_alone_when_selection_already_visible(self):
        self.assertEqual(widgets.clamp_scroll(3, 2, 4), 2)


class TestListView(unittest.TestCase):
    def test_scroll_only_list_keeps_its_offset(self):
        """A list with no selection (the inventory readout) must not be
        snapped back to the top every frame."""
        console = RecordingConsole()
        region = widgets.ListRegion(x=0, y=0, width=20, height=3)
        rows = [widgets.Row(text=f"row {i}") for i in range(10)]

        offset = widgets.list_view(console, region, rows, selected_index=None, scroll_offset=4)

        self.assertEqual(offset, 4)
        self.assertIn("row 4", console.strings())

    def test_selection_color_wins_over_hover(self):
        console = RecordingConsole()
        region = widgets.ListRegion(x=0, y=0, width=20, height=3)
        rows = [widgets.Row(text=f"row {i}") for i in range(3)]

        widgets.list_view(console, region, rows, selected_index=0, hovered_index=1)

        by_text = {c["string"]: c["fg"] for c in console.print_calls if c["string"].startswith("row")}
        self.assertEqual(by_text["row 0"], theme.SELECTION)
        self.assertEqual(by_text["row 1"], theme.HOVER)
        self.assertEqual(by_text["row 2"], theme.TEXT)

    def test_disabled_rows_are_greyed(self):
        console = RecordingConsole()
        region = widgets.ListRegion(x=0, y=0, width=20, height=2)
        rows = [widgets.Row(text="cannot", enabled=False)]

        widgets.list_view(console, region, rows, selected_index=None)

        by_text = {c["string"]: c["fg"] for c in console.print_calls}
        self.assertEqual(by_text["cannot"], theme.TEXT_DISABLED)


class TestMessageLog(unittest.TestCase):
    def test_repeated_message_collapses_into_a_count(self):
        entries = []
        for _ in range(3):
            message_log.append_message(entries, "You pick up 1x Wheat.", tick=10)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].count, 3)
        self.assertIn("(x3)", entries[0].display_text())

    def test_different_messages_do_not_collapse(self):
        entries = []
        message_log.append_message(entries, "A", tick=1)
        message_log.append_message(entries, "B", tick=2)
        message_log.append_message(entries, "A", tick=3)

        self.assertEqual([e.text for e in entries], ["A", "B", "A"])

    def test_explicit_category_beats_keyword_inference(self):
        entries = []
        message_log.append_message(entries, "You stop attacking.", category="social", tick=0)

        self.assertEqual(entries[0].category, "social")

    def test_inferred_category_is_stored_once(self):
        entries = []
        message_log.append_message(entries, "Quest accepted: find the goat.", tick=0)

        self.assertEqual(entries[0].category, "quest")

    def test_entries_are_capped(self):
        entries = []
        for i in range(message_log.MAX_LOG_ENTRIES + 25):
            message_log.append_message(entries, f"line {i}", tick=i)

        self.assertEqual(len(entries), message_log.MAX_LOG_ENTRIES)

    def test_fade_ratio_decays_with_age_but_never_to_zero(self):
        entry = message_log.LogEntry(text="x", tick=0)

        fresh = message_log.fade_ratio(entry, 0)
        old = message_log.fade_ratio(entry, message_log.FADE_WINDOW_TICKS * 4)

        self.assertAlmostEqual(fresh, 1.0, places=5)
        self.assertEqual(old, message_log.FADE_FLOOR)
        self.assertGreater(old, 0.0)

    def test_repeat_refreshes_the_fade_timer(self):
        entries = []
        message_log.append_message(entries, "drip", tick=0)
        message_log.append_message(entries, "drip", tick=500)

        self.assertEqual(entries[0].tick, 500)


class TestChatLogIntegration(unittest.TestCase):
    def test_world_records_categories_alongside_the_plain_log(self):
        world = SimpleNamespace(chat_log=[], chat_log_entries=[], game_time=42, chat_log_scroll=3)

        from engine import World
        World.add_message_to_chat_log(world, "You gain a level.", category="gain")

        self.assertEqual(world.chat_log, ["You gain a level."])
        self.assertEqual(world.chat_log_entries[0].category, "gain")
        self.assertEqual(world.chat_log_entries[0].tick, 42)

    def test_new_message_snaps_the_log_view_back_to_the_newest_line(self):
        world = SimpleNamespace(chat_log=[], chat_log_entries=[], game_time=0, chat_log_scroll=7)

        from engine import World
        World.add_message_to_chat_log(world, "Something happened.")

        self.assertEqual(world.chat_log_scroll, 0)

    def test_log_panel_colors_lines_by_stored_category(self):
        console = RecordingConsole()
        world = SimpleNamespace(
            game_time=0,
            chat_log=[],
            chat_log_scroll=0,
            chat_log_entries=[
                message_log.LogEntry(text="A blow lands.", category="combat", tick=0),
                message_log.LogEntry(text="Quest updated.", category="quest", tick=0),
            ],
            player=SimpleNamespace(x=0, y=0),
        )

        with patch("rendering.console_renderer._draw_chatter_panel", return_value=0):
            console_renderer._draw_log_panel(console, world)

        by_text = {c["string"]: c["fg"] for c in console.print_calls}
        self.assertEqual(by_text["A blow lands."], theme.log_color("combat"))
        self.assertEqual(by_text["Quest updated."], theme.log_color("quest"))

    def test_log_panel_falls_back_to_a_plain_string_log(self):
        """Older saves have chat_log but no entries; the panel must still
        render rather than showing nothing."""
        console = RecordingConsole()
        world = SimpleNamespace(
            game_time=0,
            chat_log=["Legacy line."],
            chat_log_scroll=0,
            player=SimpleNamespace(x=0, y=0),
        )

        with patch("rendering.console_renderer._draw_chatter_panel", return_value=0):
            console_renderer._draw_log_panel(console, world)

        self.assertIn("Legacy line.", console.strings())


class TestScrollMessageLog(unittest.TestCase):
    def _world(self, count):
        entries = [message_log.LogEntry(text=f"line {i}", tick=i) for i in range(count)]
        return SimpleNamespace(chat_log_entries=entries, chat_log_scroll=0)

    def test_scrolling_back_is_capped_by_history_length(self):
        world = self._world(10)

        main._scroll_message_log(world, 999)

        self.assertEqual(world.chat_log_scroll, 10 - console_renderer.LOG_VISIBLE_LINES)

    def test_cannot_scroll_forward_past_the_newest_line(self):
        world = self._world(10)

        main._scroll_message_log(world, -5)

        self.assertEqual(world.chat_log_scroll, 0)

    def test_short_history_cannot_scroll_at_all(self):
        world = self._world(2)

        main._scroll_message_log(world, 4)

        self.assertEqual(world.chat_log_scroll, 0)


class TestLighting(unittest.TestCase):
    def test_daylight_needs_no_local_light(self):
        self.assertEqual(lighting.ambient_for_light_level("DAY"), 1.0)

    def test_night_is_darker_than_dusk(self):
        self.assertLess(
            lighting.ambient_for_light_level("NIGHT"),
            lighting.ambient_for_light_level("DUSK"),
        )

    def test_lit_campfire_is_collected_as_a_light_source(self):
        world = SimpleNamespace(
            game_time=0,
            player=None,
            campfires_by_id={
                "a": SimpleNamespace(x=5, y=5, lit=True, warmth_radius=4),
                "b": SimpleNamespace(x=6, y=6, lit=False, warmth_radius=4),
            },
            all_npcs=[],
        )

        sources = lighting.collect_light_sources(world, (0, 0, 20, 20))

        self.assertEqual([(s.x, s.y) for s in sources], [(5, 5)])
        self.assertEqual(sources[0].color, lighting.FIRELIGHT)

    def test_unlit_player_light_brightens_without_tinting(self):
        """Dark-adapted eyes let you see nearby ground; they must not wash
        the time-of-day tint out of it."""
        world = SimpleNamespace(
            game_time=0,
            player=SimpleNamespace(x=1, y=1, equipment=SimpleNamespace(
                equipped_light_item_key=None, current_personal_light_radius=0)),
            campfires_by_id={},
            all_npcs=[],
        )

        sources = lighting.collect_light_sources(world, (0, 0, 10, 10))

        self.assertEqual(len(sources), 1)
        self.assertFalse(sources[0].tints)

    def test_lit_torch_makes_the_player_a_tinting_source(self):
        world = SimpleNamespace(
            game_time=0,
            player=SimpleNamespace(x=1, y=1, equipment=SimpleNamespace(
                equipped_light_item_key="torch_lit", current_personal_light_radius=10)),
            campfires_by_id={},
            all_npcs=[],
        )

        sources = lighting.collect_light_sources(world, (0, 0, 10, 10))

        self.assertTrue(sources[0].tints)
        self.assertEqual(sources[0].radius, 10)

    def test_light_map_is_brightest_at_the_source_and_fades_outward(self):
        source = lighting.LightSource(x=5, y=0, radius=5, color=lighting.FIRELIGHT)
        map_x = np.arange(11)
        map_y = np.arange(1)

        strength, warm, _tint = lighting.build_light_map([source], map_x, map_y, ambient=0.3)

        self.assertAlmostEqual(float(strength[0, 5]), 1.0, places=5)
        self.assertGreater(strength[0, 6], strength[0, 8])
        self.assertEqual(float(strength[0, 0]), 0.0)
        self.assertGreater(float(warm[0, 5]), 0.0)

    def test_light_map_is_empty_in_full_daylight(self):
        source = lighting.LightSource(x=0, y=0, radius=5, color=lighting.FIRELIGHT)

        strength, _warm, _tint = lighting.build_light_map(
            [source], np.arange(4), np.arange(4), ambient=1.0
        )

        self.assertFalse(strength.any())

    def test_firelight_leaves_a_night_cell_warmer_and_brighter(self):
        """The end-to-end payoff: at night, a cell beside a lit campfire
        should read warm and lit, not just marginally less dark."""
        def run(with_fire):
            console = SimpleNamespace(
                width=1, height=1,
                fg=np.full((1, 1, 3), 200, dtype=np.uint8),
                bg=np.full((1, 1, 3), 200, dtype=np.uint8),
            )
            world = SimpleNamespace(
                game_time=0,
                current_light_level_name="NIGHT",
                player=SimpleNamespace(x=40, y=40, equipment=SimpleNamespace(
                    equipped_light_item_key=None, current_personal_light_radius=0)),
                campfires_by_id=(
                    {"a": SimpleNamespace(x=0, y=0, lit=True, warmth_radius=4)} if with_fire else {}
                ),
                all_npcs=[],
                get_tile_at=lambda x, y: SimpleNamespace(blocks_fov=False, name="Plains"),
            )
            with patch("rendering.console_renderer.is_visible", return_value=True):
                console_renderer._apply_lighting_and_depth(console, world, 0, 0)
            return tuple(int(v) for v in console.fg[0, 0])

        dark = run(False)
        firelit = run(True)

        self.assertGreater(sum(firelit), sum(dark))
        # Warm means red gains on blue relative to the unlit night cell.
        self.assertGreater(firelit[0] - firelit[2], dark[0] - dark[2])

    def test_lighting_leaves_cells_outside_the_fov_untouched(self):
        console = SimpleNamespace(
            width=2, height=1,
            fg=np.full((1, 2, 3), 200, dtype=np.uint8),
            bg=np.full((1, 2, 3), 200, dtype=np.uint8),
        )
        world = SimpleNamespace(
            game_time=0,
            current_light_level_name="NIGHT",
            player=SimpleNamespace(x=0, y=0, equipment=SimpleNamespace(
                equipped_light_item_key=None, current_personal_light_radius=0)),
            campfires_by_id={},
            all_npcs=[],
            get_tile_at=lambda x, y: SimpleNamespace(blocks_fov=False, name="Plains"),
        )

        with patch("rendering.console_renderer.is_visible",
                   side_effect=lambda _w, x, y: x == 0):
            console_renderer._apply_lighting_and_depth(console, world, 0, 0)

        self.assertLess(int(console.fg[0, 0].sum()), 600)
        self.assertEqual(int(console.fg[0, 1].sum()), 600)


class TestTitleArt(unittest.TestCase):
    def test_renders_fixed_height_block_letters(self):
        lines = title_art.render_lines("LIFE")

        self.assertEqual(len(lines), title_art.GLYPH_HEIGHT)
        self.assertEqual(len({len(line) for line in lines}), 1)
        self.assertIn(theme.BAR_CELL, lines[0])

    def test_unknown_characters_render_as_blank_not_an_error(self):
        lines = title_art.render_lines("Z")

        self.assertEqual(len(lines), title_art.GLYPH_HEIGHT)
        self.assertEqual(lines[0].strip(), "")

    def test_draw_centers_the_block_text(self):
        console = RecordingConsole()

        title_art.draw(console, 50, 2, "LIFE")

        width = title_art.measure("LIFE")
        xs = {call["x"] for call in console.print_calls}
        self.assertEqual(xs, {50 - width // 2})


class TestSaveMetadata(unittest.TestCase):
    def test_summary_round_trips_beside_the_save(self):
        import save_manager

        world = SimpleNamespace(
            player=SimpleNamespace(name="Ada Quill"),
            game_time=12345,
            seasons=["Spring", "Summer"],
            current_season_index=1,
            weather="light_rain",
        )

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(save_manager, "SAVE_DIR", tmp):
                os.makedirs(tmp, exist_ok=True)
                with open(save_manager._metadata_path("run.sav"), "w", encoding="utf-8") as f:
                    import json
                    json.dump(save_manager._build_save_metadata(world), f)

                loaded = save_manager.load_save_metadata("run.sav")

        self.assertEqual(loaded["player_name"], "Ada Quill")
        self.assertEqual(loaded["game_time"], 12345)
        self.assertEqual(loaded["season"], "Summer")

    def test_missing_summary_reads_as_none(self):
        import save_manager

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(save_manager, "SAVE_DIR", tmp):
                self.assertIsNone(save_manager.load_save_metadata("nope.sav"))

    def test_describe_save_falls_back_to_the_filename(self):
        with patch("main.load_save_metadata", return_value=None):
            title, detail = main._describe_save("old.sav")

        self.assertEqual(title, "old.sav")
        self.assertIn("no summary", detail)


class TestMenuMouseRouting(unittest.TestCase):
    def _world(self, **kwargs):
        base = dict(
            game_state="PLAYING",
            interaction_context={"active": False},
            mouse_x=0,
            mouse_y=0,
            menu_hit_regions={},
        )
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_click_outside_any_menu_is_not_consumed(self):
        world = self._world()
        event = SimpleNamespace(button=1)

        self.assertFalse(main.handle_menu_mouse_click(event, world, context=None))

    def test_left_click_selects_and_confirms_the_row(self):
        region = widgets.ListRegion(x=0, y=0, width=10, height=4)
        world = self._world(
            game_state="CRAFTING_MENU",
            crafting_menu_context={"all_recipes": ["a", "b", "c"], "selected_recipe_index": 0},
            mouse_x=2,
            mouse_y=2,
            menu_hit_regions={
                "CRAFTING_MENU": console_renderer.MenuHitRegion(region=region, scroll_offset=0, total=3),
            },
        )
        event = SimpleNamespace(button=main.tcod.event.MouseButton.LEFT)

        with patch("main.handle_crafting_input") as confirm:
            consumed = main.handle_menu_mouse_click(event, world, context=None)

        self.assertTrue(consumed)
        self.assertEqual(world.crafting_menu_context["selected_recipe_index"], 2)
        confirm.assert_called_once()

    def test_right_click_selects_without_confirming(self):
        region = widgets.ListRegion(x=0, y=0, width=10, height=4)
        world = self._world(
            game_state="CRAFTING_MENU",
            crafting_menu_context={"all_recipes": ["a", "b", "c"], "selected_recipe_index": 0},
            mouse_x=2,
            mouse_y=1,
            menu_hit_regions={
                "CRAFTING_MENU": console_renderer.MenuHitRegion(region=region, scroll_offset=0, total=3),
            },
        )
        event = SimpleNamespace(button=main.tcod.event.MouseButton.RIGHT)

        with patch("main.handle_crafting_input") as confirm:
            consumed = main.handle_menu_mouse_click(event, world, context=None)

        self.assertTrue(consumed)
        self.assertEqual(world.crafting_menu_context["selected_recipe_index"], 1)
        confirm.assert_not_called()

    def test_click_in_menu_padding_is_ignored(self):
        region = widgets.ListRegion(x=0, y=0, width=10, height=6)
        world = self._world(
            game_state="CRAFTING_MENU",
            crafting_menu_context={"all_recipes": ["a"], "selected_recipe_index": 0},
            mouse_x=2,
            mouse_y=5,  # below the single row
            menu_hit_regions={
                "CRAFTING_MENU": console_renderer.MenuHitRegion(region=region, scroll_offset=0, total=1),
            },
        )
        event = SimpleNamespace(button=main.tcod.event.MouseButton.LEFT)

        with patch("main.handle_crafting_input") as confirm:
            consumed = main.handle_menu_mouse_click(event, world, context=None)

        self.assertFalse(consumed)
        confirm.assert_not_called()

    def test_social_menu_routes_to_the_field_for_its_current_mode(self):
        region = widgets.ListRegion(x=0, y=0, width=10, height=4)
        world = self._world(
            game_state="SOCIAL_MENU",
            social_menu_context={"mode": "gift", "selected_option_index": 0, "selected_action_index": 0},
            mouse_x=1,
            mouse_y=1,
            menu_hit_regions={
                "SOCIAL_MENU": console_renderer.MenuHitRegion(region=region, scroll_offset=0, total=4),
            },
        )
        event = SimpleNamespace(button=main.tcod.event.MouseButton.RIGHT)

        main.handle_menu_mouse_click(event, world, context=None)

        self.assertEqual(world.social_menu_context["selected_option_index"], 1)
        self.assertEqual(world.social_menu_context["selected_action_index"], 0)


class TestConsoleBufferOrder(unittest.TestCase):
    """The root console must expose fg/bg as [y, x].

    The renderer indexes those buffers [y, x] everywhere. Building the
    console with tcod's order="F" flips them to [x, y], which doesn't fail
    loudly - it just means `console.bg[y, x]` silently reads the wrong cell,
    and throws IndexError once a screen column exceeds the console height.
    With a 78-wide map and a 56-tall console that meant the game died as
    soon as any entity was drawn in the right-hand third of the view.
    """

    class BufferConsole:
        """Console stand-in whose fg/bg follow tcod's ordering rules."""

        def __init__(self, width, height, order):
            self.width = width
            self.height = height
            shape = (width, height, 3) if order == "F" else (height, width, 3)
            self.fg = np.zeros(shape, dtype=np.uint8)
            self.bg = np.zeros(shape, dtype=np.uint8)
            self.print_calls = []

        def print(self, **kwargs):
            self.print_calls.append(kwargs)

    def _draw_entity_at_screen_column(self, order, column):
        console = self.BufferConsole(config.SCREEN_WIDTH, config.SCREEN_HEIGHT, order)
        entity = SimpleNamespace(
            x=column, y=1,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=1),
            color=(120, 130, 140),
        )
        world = SimpleNamespace(
            npcs=[entity],
            village_npcs=[],
            player=SimpleNamespace(x=0, y=0, state=SimpleNamespace(is_riding=False)),
            zoom_levels=(1.0,),
            zoom_index=0,
        )
        with patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.get_entity_sprite", return_value=ord("@")):
            console_renderer._draw_entities(console, world, 0, 0)
        return console

    def test_entity_in_the_right_hand_map_columns_draws_without_error(self):
        console = self._draw_entity_at_screen_column("C", config.MAP_WIDTH - 2)

        self.assertTrue(console.print_calls)

    def test_f_order_buffers_are_what_used_to_crash(self):
        """Pins the diagnosis: the same draw against [x, y] buffers raises."""
        with self.assertRaises(IndexError):
            self._draw_entity_at_screen_column("F", config.MAP_WIDTH - 2)

    def test_create_console_exposes_row_major_buffers(self):
        console = main.create_console()

        # The tcod_compat stub has no buffers; only assert when they exist.
        if not hasattr(console, "fg"):
            self.skipTest("tcod is not installed; console is the compat stub")
        self.assertEqual(console.fg.shape[0], config.SCREEN_HEIGHT)
        self.assertEqual(console.fg.shape[1], config.SCREEN_WIDTH)


class TestRenderBackendGuard(unittest.TestCase):
    """A missing renderer must stop the game with a clear message.

    Without tcod, tcod_compat substitutes a shim whose Console discards
    every draw call and whose event queue is always empty, so the game ran
    a windowless busy-loop forever - announced only as a warning from the
    tileset loader about a missing 'set_tile' attribute, which reads like a
    sprite-sheet problem rather than "there is no renderer".
    """

    def test_backend_check_passes_when_tcod_is_installed(self):
        with patch.object(main, "TCOD_AVAILABLE", True):
            self.assertTrue(main.require_render_backend())

    def test_backend_check_fails_with_an_actionable_message(self):
        import io

        stderr = io.StringIO()
        with patch.object(main, "TCOD_AVAILABLE", False), \
             patch("sys.stderr", stderr):
            result = main.require_render_backend()

        self.assertFalse(result)
        message = stderr.getvalue()
        self.assertIn("pip install tcod", message)
        self.assertIn("--headless", message)

    def test_main_exits_non_zero_without_a_renderer(self):
        args = SimpleNamespace(headless=False, ticks=None)
        with patch.object(main, "TCOD_AVAILABLE", False), \
             patch("argparse.ArgumentParser.parse_args", return_value=args), \
             patch("sys.stderr", new_callable=lambda: __import__("io").StringIO()), \
             patch.object(main, "load_custom_tileset") as load_tileset:
            exit_code = main.main()

        self.assertEqual(exit_code, 1)
        # It must bail before trying to build a tileset it cannot use.
        load_tileset.assert_not_called()

    def test_headless_still_runs_without_a_renderer(self):
        """Simulation-only runs don't need a window, so --headless must
        still work - just with a warning that terrain will be flat."""
        args = SimpleNamespace(headless=True, ticks=1)
        with patch.object(main, "TCOD_AVAILABLE", False), \
             patch("argparse.ArgumentParser.parse_args", return_value=args), \
             patch.object(main, "World") as world_cls, \
             patch.object(main, "run_headless") as run_headless:
            main.main()

        world_cls.assert_called_once()
        run_headless.assert_called_once()


class TestStatusPanelBudget(unittest.TestCase):
    def test_sections_stop_before_the_pinned_legend(self):
        """A frame with many alerts and nearby entities used to draw
        straight through the bottom-docked legend."""
        console = RecordingConsole()
        cursor = console_renderer._PanelCursor(console, x=0, y=0, width=20, limit=3)

        for index in range(10):
            cursor.line(f"line {index}")

        self.assertEqual(len(console.print_calls), 3)
        self.assertEqual(cursor.y, 3)

    def test_cursor_reports_when_a_section_will_not_fit(self):
        console = RecordingConsole()
        cursor = console_renderer._PanelCursor(console, x=0, y=0, width=20, limit=2)

        self.assertTrue(cursor.fits(2))
        self.assertFalse(cursor.fits(3))


if __name__ == "__main__":
    unittest.main()
