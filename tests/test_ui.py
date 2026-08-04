import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import json
import math
import uuid
from runtime_compat import np

import engine
from engine import World
import main
from ui_requests import (
    CloseTradeRequest,
    OpenDialogueRequest,
    OpenTradeRequest,
    close_trade_request,
    coerce_ui_request,
    open_trade_request,
)
import rendering.console_renderer as console_renderer
from save_manager import save_game, load_game
from data.items import ITEM_DEFINITIONS
import config
from tcod_compat import tcod
import tile_types

class TestMainInputHelpers(unittest.TestCase):
    def test_normalize_player_first_name_keeps_short_clean_input(self):
        self.assertEqual(main.normalize_player_first_name("  Ada  "), "Ada")

    def test_normalize_player_first_name_falls_back_for_empty_or_invalid_input(self):
        self.assertEqual(main.normalize_player_first_name("  "), "Player")
        self.assertEqual(main.normalize_player_first_name("1234!!!"), "Player")

    def test_new_world_starts_at_configured_initial_time(self):
        world = World(seed=123)

        self.assertEqual(world.game_time, config.INITIAL_TIME_OF_DAY)

    def test_open_interaction_menu_skips_entities_without_actions(self):
        world = SimpleNamespace(
            interaction_context={},
            _get_interactables_at=lambda x, y: [
                {"name": "Plains", "type": "tile", "data": object()},
                {"name": "Book", "type": "item", "data": {"item_key": "book_test", "quantity": 1}},
            ],
            _get_actions_for_entity=lambda entity: [] if entity["name"] == "Plains" else ["Pick up", "Read"],
            add_message_to_chat_log=unittest.mock.Mock(),
        )

        main.open_interaction_menu(world, 3, 4)

        self.assertTrue(world.interaction_context["active"])
        self.assertEqual(world.interaction_context["target_entities"][0]["name"], "Book")
        self.assertEqual(world.interaction_context["available_actions"], ["Pick up", "Read"])
        world.add_message_to_chat_log.assert_not_called()

    def test_open_interaction_menu_reports_when_no_entity_has_actions(self):
        world = SimpleNamespace(
            interaction_context={"active": False},
            _get_interactables_at=lambda x, y: [{"name": "Plains", "type": "tile", "data": object()}],
            _get_actions_for_entity=lambda entity: [],
            add_message_to_chat_log=unittest.mock.Mock(),
        )

        main.open_interaction_menu(world, 1, 2)

        self.assertFalse(world.interaction_context["active"])
        world.add_message_to_chat_log.assert_called_once_with("There is nothing here you can interact with.")

    def test_handle_interaction_input_closes_empty_menu_safely(self):
        world = SimpleNamespace(
            interaction_context={"active": True, "available_actions": []},
            add_message_to_chat_log=unittest.mock.Mock(),
        )
        event = SimpleNamespace(sym=tcod.event.KeySym.RETURN)

        took_turn = main.handle_interaction_input(event, world, context_handler=SimpleNamespace())

        self.assertFalse(took_turn)
        self.assertFalse(world.interaction_context["active"])
        world.add_message_to_chat_log.assert_called_once_with("There is nothing here you can interact with.")

    def test_interact_uses_player_facing_direction_from_state(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.E)
        player = SimpleNamespace(x=10, y=20, state=SimpleNamespace(last_dx=1, last_dy=-1))
        world = SimpleNamespace(player=player)

        with patch("main.open_interaction_menu") as mock_open_menu:
            main.handle_playing_input(event, world, context_handler=SimpleNamespace())

        mock_open_menu.assert_called_once_with(world, 11, 19)

    def test_building_menu_uses_player_facing_direction_from_state(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.RETURN)
        player = SimpleNamespace(x=4, y=7, state=SimpleNamespace(last_dx=-1, last_dy=0))
        building_menu_context = {"all_recipes": ["wood_wall"], "selected_recipe_index": 0}
        world = SimpleNamespace(
            player=player,
            game_state="BUILDING_MENU",
            building_menu_context=building_menu_context,
            player_attempt_build=unittest.mock.Mock(),
        )

        main.handle_building_input(event, world)

        world.player_attempt_build.assert_called_once_with("wood_wall", 3, 7)

    def test_camera_origin_uses_zoomed_world_window_and_keeps_player_centered(self):
        world = SimpleNamespace(
            player=SimpleNamespace(x=100, y=80),
            zoom_levels=(1.0,),
            zoom_index=0,
        )

        camera_x, camera_y = main._get_camera_origin(world)
        view_width, view_height = main._get_world_view_size(world)

        self.assertEqual(camera_x, 100 - view_width // 2)
        self.assertEqual(camera_y, 80 - view_height // 2)
        self.assertEqual(view_width, config.MAP_WIDTH)
        self.assertEqual(view_height, config.MAP_HEIGHT)

    def test_screen_to_world_position_respects_zoom(self):
        world = SimpleNamespace(zoom_levels=(1.0,), zoom_index=0)

        world_x, world_y = main._screen_to_world_position(world, 50, 60, 10, 12)

        self.assertEqual((world_x, world_y), (60, 72))

    def test_handle_events_mouse_wheel_updates_zoom_index(self):
        class FakeMouseWheel:
            def __init__(self, y):
                self.y = y

        world = SimpleNamespace(
            game_state="PLAYING",
            player=SimpleNamespace(x=5, y=5, state=SimpleNamespace(current_path=[])),
            mouse_x=1,
            mouse_y=1,
            chat_ui_active=False,
            interaction_context={"active": False},
            ui_requests=[],
            zoom_levels=(1.0,),
            zoom_index=0,
        )
        context = SimpleNamespace(convert_event=lambda event: None)
        event = FakeMouseWheel(1)

        with patch("tcod.event.get", return_value=[event]), \
             patch("tcod.event.MouseWheel", new=FakeMouseWheel):
            turn_taken = main.handle_events(world, context)

        self.assertFalse(turn_taken)
        self.assertEqual(world.zoom_index, 0)

    def test_handle_noticeboard_menu_input_enter_claims_selected_task(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.RETURN)
        world = SimpleNamespace(
            game_state="NOTICEBOARD_MENU",
            noticeboard_menu_context={"mode": "browse", "task_ids": ["haul:task_1"], "selected_task_index": 0, "scroll_offset": 0},
            claim_noticeboard_task=unittest.mock.Mock(),
        )

        main.handle_noticeboard_menu_input(event, world)

        world.claim_noticeboard_task.assert_called_once_with("task_1")

    def test_handle_noticeboard_menu_input_escape_returns_to_playing(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.ESCAPE)
        world = SimpleNamespace(
            game_state="NOTICEBOARD_MENU",
            noticeboard_menu_context={"task_ids": [], "selected_task_index": 0, "scroll_offset": 0},
        )

        main.handle_noticeboard_menu_input(event, world)

        self.assertEqual(world.game_state, "PLAYING")

    def test_handle_noticeboard_menu_input_p_opens_job_posting(self):
        event = SimpleNamespace(sym=ord("p"))
        world = SimpleNamespace(
            game_state="NOTICEBOARD_MENU",
            noticeboard_menu_context={"mode": "browse", "task_ids": [], "selected_task_index": 0, "scroll_offset": 0},
            open_job_posting_menu=unittest.mock.Mock(),
        )

        main.handle_noticeboard_menu_input(event, world)

        world.open_job_posting_menu.assert_called_once_with()

    def test_handle_noticeboard_post_job_input_return_posts_selected_role(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.RETURN)
        building = object()
        world = SimpleNamespace(
            game_state="NOTICEBOARD_MENU",
            noticeboard_menu_context={
                "mode": "post_job",
                "posting_building_id": "shop_1",
                "selected_role_index": 1,
                "selected_wage_index": 2,
                "wage_options": [10, 15, 20],
            },
            _get_job_posting_building=unittest.mock.Mock(return_value=building),
            _get_job_posting_role_options=unittest.mock.Mock(return_value=["Merchant", "Scribe"]),
            _get_player_owned_buildings=unittest.mock.Mock(return_value=[building]),
            get_job_posting_wage=unittest.mock.Mock(return_value=20),
            post_employment_listing=unittest.mock.Mock(),
        )

        main.handle_noticeboard_menu_input(event, world)

        world.post_employment_listing.assert_called_once_with(building, "Scribe", 20)

    def test_handle_company_ledger_menu_input_return_executes_selected_transfer(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.RETURN)
        building = object()
        world = SimpleNamespace(
            game_state="COMPANY_LEDGER_MENU",
            company_ledger_menu_context={
                "building_id": "shop_1",
                "selected_action_index": 1,
                "selected_amount_index": 2,
                "amount_options": [1, 10, 50, 100],
            },
            get_company_ledger_building=unittest.mock.Mock(return_value=building),
            get_company_ledger_amount=unittest.mock.Mock(return_value=50),
            transfer_company_funds=unittest.mock.Mock(),
            add_message_to_chat_log=unittest.mock.Mock(),
        )

        main.handle_company_ledger_menu_input(event, world)

        world.transfer_company_funds.assert_called_once_with(building, 50, withdraw=True)

    def test_handle_company_ledger_menu_input_escape_returns_to_playing(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.ESCAPE)
        world = SimpleNamespace(
            game_state="COMPANY_LEDGER_MENU",
            company_ledger_menu_context={"selected_action_index": 0, "selected_amount_index": 0, "amount_options": [1, 10]},
        )

        main.handle_company_ledger_menu_input(event, world)

        self.assertEqual(world.game_state, "PLAYING")

    def test_find_nearest_npc_prefers_closest_living_npc_within_range(self):
        world = SimpleNamespace(
            player=SimpleNamespace(x=0, y=0),
            all_npcs=[
                SimpleNamespace(name="Far", x=4, y=4, is_dead=False),
                SimpleNamespace(name="Dead", x=1, y=0, is_dead=True),
                SimpleNamespace(name="Close", x=2, y=1, is_dead=False),
                SimpleNamespace(name="Too Far", x=6, y=0, is_dead=False),
            ],
        )

        nearest = main._find_nearest_npc_to_talk_to(world, max_distance=5)

        self.assertIsNotNone(nearest)
        self.assertEqual(nearest.name, "Close")

    def test_quest_menu_down_does_not_go_negative_when_no_quests_exist(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.DOWN)
        world = SimpleNamespace(
            game_state="QUEST_MENU",
            quest_menu_context={"selected_quest_index": 0},
            player=SimpleNamespace(knowledge=SimpleNamespace(active_quests={})),
        )

        main.handle_quest_menu_input(event, world)

        self.assertEqual(world.quest_menu_context["selected_quest_index"], 0)

    def test_quest_menu_clamps_selection_to_last_active_quest(self):
        event = SimpleNamespace(sym=tcod.event.KeySym.DOWN)
        world = SimpleNamespace(
            game_state="QUEST_MENU",
            quest_menu_context={"selected_quest_index": 0},
            player=SimpleNamespace(
                knowledge=SimpleNamespace(
                    active_quests={
                        "quest_1": {"title": "First"},
                        "quest_2": {"title": "Second"},
                    }
                )
            ),
        )

        main.handle_quest_menu_input(event, world)
        main.handle_quest_menu_input(event, world)
        main.handle_quest_menu_input(event, world)

        self.assertEqual(world.quest_menu_context["selected_quest_index"], 1)

    def test_start_trade_accepts_supported_non_merchant_professions(self):
        npc = SimpleNamespace(economic=SimpleNamespace(profession="Miller"))
        world = SimpleNamespace(
            game_state="PLAYING",
            trade_ui_npc_target=None,
            trade_ui_active=False,
            chat_ui_active=False,
            chat_ui_target_npc=None,
            needs_text_input=False,
            ui_requests=[],
            initialize_trade_session=unittest.mock.Mock(),
            add_message_to_chat_log=unittest.mock.Mock(),
            request_open_trade=lambda trade_npc: world.ui_requests.append(open_trade_request(trade_npc)),
        )

        main.start_trade(world, npc)

        self.assertIs(world.trade_ui_npc_target, npc)
        self.assertTrue(world.trade_ui_active)
        self.assertEqual(world.game_state, "TRADE_MENU")
        world.initialize_trade_session.assert_called_once_with()
        world.add_message_to_chat_log.assert_not_called()

    def test_handle_trade_menu_input_escape_closes_trade_state(self):
        trade_npc = object()
        world = SimpleNamespace(
            trade_ui_active=True,
            trade_ui_npc_target=trade_npc,
            chat_ui_active=False,
            chat_ui_target_npc=None,
            needs_text_input=False,
            game_state="TRADE_MENU",
            ui_requests=[],
            request_close_trade=lambda target_npc=None: world.ui_requests.append(close_trade_request(target_npc)),
        )
        event = SimpleNamespace(sym=tcod.event.KeySym.ESCAPE)

        main.handle_trade_menu_input(event, world)

        self.assertFalse(world.trade_ui_active)
        self.assertIsNone(world.trade_ui_npc_target)
        self.assertEqual(world.game_state, "PLAYING")

    def test_handle_trade_menu_input_enter_executes_trade_action(self):
        world = SimpleNamespace(
            trade_ui_active=True,
            trade_ui_npc_target=object(),
            game_state="TRADE_MENU",
            trade_ui_player_selling=True,
            trade_ui_player_inventory_snapshot=[("raw_log", 1, 5)],
            trade_ui_player_item_index=0,
            trade_ui_merchant_inventory_snapshot=[],
            trade_ui_merchant_item_index=0,
            handle_trade_action=unittest.mock.Mock(),
        )
        event = SimpleNamespace(sym=tcod.event.KeySym.RETURN)

        main.handle_trade_menu_input(event, world)

        world.handle_trade_action.assert_called_once_with()


    def test_apply_ui_requests_opens_dialogue_from_engine_request(self):
        npc = SimpleNamespace(name="Trader")
        context_handler = SimpleNamespace(
            start_text_input=unittest.mock.Mock(),
            stop_text_input=unittest.mock.Mock(),
        )
        world = SimpleNamespace(
            ui_requests=[OpenDialogueRequest(npc=npc, mode="talk")],
            game_state="PLAYING",
            chat_ui_target_npc=None,
            chat_ui_mode=None,
            chat_ui_active=False,
            trade_ui_active=True,
            trade_ui_npc_target=object(),
            needs_text_input=False,
            interaction_context={"active": True},
        )

        main.apply_ui_requests(world, context_handler)

        self.assertEqual(world.game_state, "DIALOGUE")
        self.assertIs(world.chat_ui_target_npc, npc)
        self.assertEqual(world.chat_ui_mode, "talk")
        self.assertTrue(world.chat_ui_active)
        self.assertFalse(world.trade_ui_active)
        self.assertIsNone(world.trade_ui_npc_target)
        self.assertFalse(world.interaction_context["active"])
        context_handler.start_text_input.assert_called_once_with()
        context_handler.stop_text_input.assert_not_called()
        self.assertEqual(world.ui_requests, [])

    def test_apply_ui_requests_closes_trade_and_stops_text_input(self):
        npc = SimpleNamespace(name="Trader")
        context_handler = SimpleNamespace(
            start_text_input=unittest.mock.Mock(),
            stop_text_input=unittest.mock.Mock(),
        )
        world = SimpleNamespace(
            ui_requests=[CloseTradeRequest(npc=npc)],
            game_state="TRADE_MENU",
            chat_ui_target_npc=None,
            chat_ui_mode=None,
            chat_ui_active=False,
            trade_ui_active=True,
            trade_ui_npc_target=npc,
            needs_text_input=True,
        )

        main.apply_ui_requests(world, context_handler)

        self.assertEqual(world.game_state, "PLAYING")
        self.assertFalse(world.trade_ui_active)
        self.assertIsNone(world.trade_ui_npc_target)
        self.assertFalse(world.needs_text_input)
        context_handler.stop_text_input.assert_called_once_with()
        context_handler.start_text_input.assert_not_called()
        self.assertEqual(world.ui_requests, [])

    def test_coerce_ui_request_converts_legacy_dict_payloads(self):
        npc = object()

        request = coerce_ui_request({"type": "open_trade", "npc": npc})

        self.assertEqual(request, OpenTradeRequest(npc=npc))

    def test_apply_ui_requests_rejects_unsupported_request_objects(self):
        world = SimpleNamespace(ui_requests=[{"type": "unknown", "npc": object()}])

        with self.assertRaisesRegex(TypeError, "Unsupported UI request"):
            main.apply_ui_requests(world)

        self.assertEqual(world.ui_requests, [])

    def test_handle_events_prioritizes_dialogue_over_stale_interaction_menu(self):
        world = SimpleNamespace(
            game_state="DIALOGUE",
            chat_ui_active=True,
            chat_ui_input_line="",
            interaction_context={"active": True},
            player=SimpleNamespace(state=SimpleNamespace(current_path=[])),
            ui_requests=[],
        )
        context = SimpleNamespace(convert_event=lambda event: event)
        original_get = tcod.event.get
        original_handle_dialogue_input = main.handle_dialogue_input
        original_handle_interaction_input = main.handle_interaction_input
        try:
            tcod.event.get = lambda: [tcod.event.KeyDown(scancode=0, sym=tcod.event.KeySym.A, mod=0)]
            main.handle_dialogue_input = unittest.mock.Mock()
            main.handle_interaction_input = unittest.mock.Mock(return_value=False)

            main.handle_events(world, context)

            main.handle_dialogue_input.assert_called_once()
            main.handle_interaction_input.assert_not_called()
        finally:
            tcod.event.get = original_get
            main.handle_dialogue_input = original_handle_dialogue_input
            main.handle_interaction_input = original_handle_interaction_input

    def test_dialogue_submit_passes_required_prompt_fields_to_continue(self):
        npc = SimpleNamespace(
            name="Villager",
            x=3,
            y=4,
            attitude_to_player="friendly",
            social=SimpleNamespace(personality="calm", relationships={}),
            knowledge=SimpleNamespace(long_term_memory=[]),
            schedule=SimpleNamespace(current_task="idle"),
        )
        world = SimpleNamespace(
            chat_ui_input_line="hello there",
            chat_ui_target_npc=npc,
            chat_ui_history=[],
            request_close_dialogue=unittest.mock.Mock(),
            continue_npc_dialogue=unittest.mock.Mock(),
            ui_requests=[],
        )
        event = tcod.event.KeyDown(scancode=0, sym=tcod.event.KeySym.RETURN, mod=0)

        main.handle_dialogue_input(event, world, SimpleNamespace())

        world.continue_npc_dialogue.assert_called_once_with(npc, "hello there")
        self.assertEqual(world.chat_ui_input_line, "")

    def test_world_goal_start_trade_emits_ui_request_instead_of_mutating_ui_state(self):
        world = object.__new__(engine.World)
        npc = SimpleNamespace(economic=SimpleNamespace(profession="Merchant"), name="Merchant")
        world.ui_requests = []
        world.add_message_to_chat_log = unittest.mock.Mock()
        world.chat_ui_active = True
        world.trade_ui_active = False
        world.game_state = "DIALOGUE"

        engine.World._handle_npc_goal(world, npc, "start_trade", "")

        self.assertEqual(world.ui_requests, [OpenTradeRequest(npc=npc)])
        self.assertTrue(world.chat_ui_active)
        self.assertFalse(world.trade_ui_active)
        self.assertEqual(world.game_state, "DIALOGUE")

    def test_execute_interaction_closes_menu_for_trade_actions(self):
        npc = SimpleNamespace(economic=SimpleNamespace(profession="Merchant"))
        world = SimpleNamespace(
            interaction_context={
                "active": True,
                "target_entities": [{"type": "npc", "data": npc, "name": "Merchant"}],
                "selected_entity_index": 0,
                "available_actions": ["Trade"],
                "selected_action_index": 0,
                "x": 0,
                "y": 0,
            },
            chat_ui_active=False,
            chat_ui_target_npc=None,
            trade_ui_active=False,
            trade_ui_npc_target=None,
            needs_text_input=False,
            ui_requests=[],
            game_state="PLAYING",
            initialize_trade_session=unittest.mock.Mock(),
            add_message_to_chat_log=unittest.mock.Mock(),
            request_open_trade=lambda trade_npc: world.ui_requests.append(open_trade_request(trade_npc)),
        )

        took_turn = main.execute_interaction(world, context_handler=SimpleNamespace())

        self.assertFalse(took_turn)
        self.assertFalse(world.interaction_context["active"])
        self.assertTrue(world.trade_ui_active)
        self.assertEqual(world.game_state, "TRADE_MENU")

    def test_execute_interaction_opens_social_menu_for_talk_action(self):
        npc = SimpleNamespace(name="Villager")
        world = SimpleNamespace(
            interaction_context={
                "active": True,
                "target_entities": [{"type": "npc", "data": npc, "name": "Villager"}],
                "selected_entity_index": 0,
                "available_actions": ["Talk"],
                "selected_action_index": 0,
                "x": 0,
                "y": 0,
            },
            chat_ui_active=False,
            trade_ui_active=False,
            ui_requests=[],
            game_state="PLAYING",
            open_social_menu=unittest.mock.Mock(return_value=True),
        )

        took_turn = main.execute_interaction(world, context_handler=SimpleNamespace())

        self.assertFalse(took_turn)
        world.open_social_menu.assert_called_once_with(npc)
        self.assertFalse(world.interaction_context["active"])

    def test_execute_interaction_opens_governance_menu_for_govern_action(self):
        building = SimpleNamespace(building_type="capital_hall")
        world = SimpleNamespace(
            interaction_context={
                "active": True,
                "target_entities": [{"type": "building", "data": building, "name": "capital_hall"}],
                "selected_entity_index": 0,
                "available_actions": ["Govern"],
                "selected_action_index": 0,
                "x": 0,
                "y": 0,
            },
            chat_ui_active=False,
            trade_ui_active=False,
            ui_requests=[],
            game_state="PLAYING",
            open_governance_menu=unittest.mock.Mock(return_value=True),
        )

        took_turn = main.execute_interaction(world, context_handler=SimpleNamespace())

        self.assertFalse(took_turn)
        world.open_governance_menu.assert_called_once_with(building)
        self.assertFalse(world.interaction_context["active"])

    def test_handle_social_menu_input_entering_gift_mode_and_escape(self):
        npc = SimpleNamespace(name="Villager")
        world = SimpleNamespace(
            social_menu_context={"mode": "root", "selected_action_index": 0, "selected_option_index": 0, "scroll_offset": 0},
            get_social_menu_target=lambda: npc,
            get_social_menu_actions=lambda: ["Give Gift", "Share Gossip", "Propose"],
            close_social_menu=unittest.mock.Mock(),
            player=SimpleNamespace(social=SimpleNamespace(family_ties={})),
        )

        main.handle_social_menu_input(SimpleNamespace(sym=tcod.event.KeySym.RETURN), world)
        self.assertEqual(world.social_menu_context["mode"], "gift")

        main.handle_social_menu_input(SimpleNamespace(sym=tcod.event.KeySym.ESCAPE), world)
        self.assertEqual(world.social_menu_context["mode"], "root")

    def test_handle_social_menu_input_propose_closes_on_acceptance(self):
        npc = SimpleNamespace(id=7, name="Beloved")
        world = SimpleNamespace(
            social_menu_context={"mode": "root", "selected_action_index": 2, "selected_option_index": 0, "scroll_offset": 0},
            get_social_menu_target=lambda: npc,
            get_social_menu_actions=lambda: ["Give Gift", "Share Gossip", "Propose"],
            player=SimpleNamespace(social=SimpleNamespace(family_ties={"partner_id": npc.id})),
            player_propose_to_npc=unittest.mock.Mock(return_value=True),
            close_social_menu=unittest.mock.Mock(),
        )

        main.handle_social_menu_input(SimpleNamespace(sym=tcod.event.KeySym.RETURN), world)

        world.player_propose_to_npc.assert_called_once_with(npc)
        world.close_social_menu.assert_called_once_with()

    def test_handle_governance_menu_input_adjusts_taxes_from_root(self):
        world = SimpleNamespace(
            governance_menu_context={"mode": "root", "selected_action_index": 0, "selected_target_index": 0, "scroll_offset": 0},
            get_governance_actions=lambda: ["Adjust Taxes", "Issue Bounty"],
            adjust_city_tax_rate=unittest.mock.Mock(return_value=True),
            close_governance_menu=unittest.mock.Mock(),
        )

        main.handle_governance_menu_input(SimpleNamespace(sym=tcod.event.KeySym.RIGHT), world)

        world.adjust_city_tax_rate.assert_called_once_with(0.01)

    def test_handle_governance_menu_input_issues_warrant_for_selected_target(self):
        target = SimpleNamespace(id=9, name="Target")
        world = SimpleNamespace(
            governance_menu_context={"mode": "target_select", "selected_action_index": 1, "selected_target_index": 0, "scroll_offset": 0, "pending_action": "Issue Bounty"},
            get_governance_targets=lambda: [target],
            issue_political_warrant=unittest.mock.Mock(return_value=True),
            close_governance_menu=unittest.mock.Mock(),
        )

        main.handle_governance_menu_input(SimpleNamespace(sym=tcod.event.KeySym.RETURN), world)

        world.issue_political_warrant.assert_called_once_with("bounty", target.id)
        self.assertEqual(world.governance_menu_context["mode"], "root")

    def test_handle_events_ignores_mouse_clicks_outside_playing_state(self):
        world = SimpleNamespace(
            game_state="TRADE_MENU",
            player=SimpleNamespace(x=5, y=5, state=SimpleNamespace(current_path=[])),
            mouse_x=1,
            mouse_y=1,
            chat_ui_active=False,
            interaction_context={"active": False},
            ui_requests=[],
        )
        context = SimpleNamespace(convert_event=lambda event: None)
        event = SimpleNamespace(button=tcod.event.MouseButton.RIGHT)

        with patch("tcod.event.get", return_value=[event]), \
             patch("main.open_interaction_menu") as mock_open_menu:
            turn_taken = main.handle_events(world, context)

        self.assertFalse(turn_taken)
        mock_open_menu.assert_not_called()



class TestConsoleRendererBuildingMenu(unittest.TestCase):
    def test_building_menu_uses_item_and_tile_display_names_for_materials(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []
            def draw_frame(self, *args, **kwargs):
                pass
            def print(self, **kwargs):
                self.print_calls.append(kwargs)
            def print_box(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace(
            player=SimpleNamespace(has_item=lambda key, qty: False),
            building_menu_context={"all_recipes": ["test_recipe"], "selected_recipe_index": 0, "scroll_offset": 0},
        )

        with patch.dict(console_renderer.CONSTRUCTION_RECIPES, {
            "test_recipe": {
                "name": "Test Recipe",
                "materials": {"axe_stone": 1, "plains": 2},
                "description": "desc",
            }
        }, clear=True):
            console_renderer.draw_building_menu(console, world)

        rendered_strings = [call.get("string", "") for call in console.print_calls]
        self.assertIn("- Stone Axe: 1", rendered_strings)
        self.assertIn("- Plains: 2", rendered_strings)




class TestConsoleRendererVisualEffects(unittest.TestCase):
    def test_renderer_draws_engine_visual_effects_without_effect_draw_methods(self):
        class FakeConsole:
            width = 20
            height = 20
            def __init__(self):
                self.print_calls = []
            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        engine_text_effect = engine.FloatingTextEffect(5, 6, "12", color=(1, 2, 3))
        engine_projectile_effect = engine.ProjectileEffect(1, 1, 5, 5, char='*', color=(4, 5, 6))

        self.assertEqual(engine_text_effect.effect_type, "floating_text")
        self.assertEqual(engine_projectile_effect.effect_type, "projectile")
        self.assertFalse(hasattr(engine_text_effect, "draw"))
        self.assertFalse(hasattr(engine_projectile_effect, "draw"))

        text_effect = SimpleNamespace(effect_type="floating_text", x=5, y=6, text="12", color=(1, 2, 3))
        projectile_effect = SimpleNamespace(effect_type="projectile", x=7, y=8, char='*', color=(4, 5, 6))

        world = SimpleNamespace(zoom_levels=(1.0,), zoom_index=0)

        console_renderer._draw_visual_effect(console, world, text_effect, 0, 0)
        console_renderer._draw_visual_effect(console, world, projectile_effect, 0, 0)

        rendered = [call["string"] for call in console.print_calls]
        self.assertIn("12", rendered)
        self.assertIn("*", rendered)


class TestConsoleRendererEntities(unittest.TestCase):
    def test_format_world_clock_uses_configured_day_length(self):
        self.assertEqual(console_renderer._format_world_clock(0), "Day 0, 00:00")
        self.assertEqual(console_renderer._format_world_clock(config.INITIAL_TIME_OF_DAY), "Day 0, 08:00")
        self.assertEqual(
            console_renderer._format_world_clock(config.DAY_LENGTH_TICKS + config.INITIAL_TIME_OF_DAY),
            "Day 1, 08:00",
        )

    def test_get_hover_inspect_returns_tile_coords_entity_and_building(self):
        tile = SimpleNamespace(name="Wood Floor")
        villager = {"type": "npc", "name": "Mira"}
        building = SimpleNamespace(building_type="town_house")
        world = SimpleNamespace(
            mouse_x=2,
            mouse_y=3,
            get_tile_at=lambda x, y: tile if (x, y) == (12, 23) else None,
            _get_interactables_at=lambda x, y: [villager] if (x, y) == (12, 23) else [],
            get_building_at=lambda x, y: building if (x, y) == (12, 23) else None,
        )

        with patch("rendering.console_renderer.is_visible", return_value=True):
            inspect = console_renderer._get_hover_inspect(world, 10, 20)

        self.assertEqual(inspect["coords"], (12, 23))
        self.assertEqual(inspect["tile"], "Wood Floor")
        self.assertEqual(inspect["entity"], "Mira")
        self.assertEqual(inspect["object"], "Town House")

    def test_get_hover_inspect_uses_feature_tile_as_object_when_no_other_object_exists(self):
        tile = SimpleNamespace(name="Wooden Chair")
        world = SimpleNamespace(
            mouse_x=1,
            mouse_y=1,
            get_tile_at=lambda x, y: tile,
            _get_interactables_at=lambda x, y: [],
            get_building_at=lambda x, y: None,
        )

        with patch("rendering.console_renderer.is_visible", return_value=True):
            inspect = console_renderer._get_hover_inspect(world, 0, 0)

        self.assertEqual(inspect["tile"], "Wooden Chair")
        self.assertEqual(inspect["object"], "Wooden Chair")

    def test_get_hover_inspect_returns_none_outside_viewport_or_unseen(self):
        world = SimpleNamespace(mouse_x=-1, mouse_y=0)
        self.assertIsNone(console_renderer._get_hover_inspect(world, 0, 0))

        world = SimpleNamespace(
            mouse_x=0,
            mouse_y=0,
            get_tile_at=lambda x, y: SimpleNamespace(name="Plains"),
            _get_interactables_at=lambda x, y: [],
            get_building_at=lambda x, y: None,
        )
        with patch("rendering.console_renderer.is_visible", return_value=False):
            self.assertIsNone(console_renderer._get_hover_inspect(world, 0, 0))

    def test_draw_hover_inspect_renders_compact_panel_section(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace()

        with patch("rendering.console_renderer._get_hover_inspect", return_value={
            "coords": (4, 5),
            "tile": "Wood Floor",
            "entity": "Mira",
            "object": "Town House",
        }):
            end_y = console_renderer._draw_hover_inspect(console, world, 0, 0, 60, 8, 20)

        rendered = [call["string"] for call in console.print_calls]
        self.assertEqual(rendered, ["Hover", "At: (4, 5)", "Tile: Wood Floor", "Entity: Mira", "Object: Town House"])
        self.assertEqual(end_y, 13)

    def test_entity_labels_only_show_when_close_or_focused(self):
        entity = SimpleNamespace(name="Villager")

        self.assertTrue(console_renderer._should_draw_entity_label(1, {"entity": None}, entity))
        self.assertFalse(console_renderer._should_draw_entity_label(4, {"entity": None}, entity))
        self.assertTrue(console_renderer._should_draw_entity_label(4, {"entity": entity}, entity))
        self.assertFalse(console_renderer._should_draw_entity_label(2, {"entity": None}, entity))

    def test_overhead_label_uses_first_name_for_known_entity(self):
        entity = SimpleNamespace(id=7, name="Elara Hart", is_identity_concealed=lambda: False)
        world = SimpleNamespace(
            player=SimpleNamespace(knowledge=SimpleNamespace(known_memories={
                "m1": SimpleNamespace(subject_id=7, target_id=None),
            })),
            get_entity_relationship_summary=lambda _entity: "",
        )

        label = console_renderer._get_entity_overhead_label(world, entity, {"entity": None}, hovered=False)

        self.assertEqual(label, "Elara")

    def test_overhead_label_uses_unknown_for_unfamiliar_entity(self):
        entity = SimpleNamespace(id=8, name="Mara Bennett", is_identity_concealed=lambda: False)
        world = SimpleNamespace(
            player=SimpleNamespace(knowledge=SimpleNamespace(known_memories={})),
            get_entity_relationship_summary=lambda _entity: "",
        )

        label = console_renderer._get_entity_overhead_label(world, entity, {"entity": None}, hovered=False)

        self.assertEqual(label, "Unknown")

    def test_overhead_label_expands_to_full_name_when_hovered(self):
        entity = SimpleNamespace(id=9, name="Clara Wilder", is_identity_concealed=lambda: False)
        world = SimpleNamespace(
            player=SimpleNamespace(knowledge=SimpleNamespace(known_memories={
                "m1": SimpleNamespace(subject_id=9, target_id=None),
            })),
            get_entity_relationship_summary=lambda _entity: "",
        )

        label = console_renderer._get_entity_overhead_label(world, entity, {"entity": None}, hovered=True)

        self.assertEqual(label, "Clara Wilder")

    def test_identity_concealment_forces_unknown_label(self):
        entity = SimpleNamespace(id=10, name="Hidden Person", is_identity_concealed=lambda: True)
        world = SimpleNamespace(
            player=SimpleNamespace(knowledge=SimpleNamespace(known_memories={
                "m1": SimpleNamespace(subject_id=10, target_id=None),
            })),
            get_entity_relationship_summary=lambda _entity: "friend",
        )

        label = console_renderer._get_entity_overhead_label(world, entity, {"entity": entity}, hovered=True)

        self.assertEqual(label, "Unknown")

    def test_wood_floor_colors_are_softened_without_changing_material(self):
        fg, bg = console_renderer._tune_floor_colors("wood_floor", (160, 82, 45), (64, 42, 22))

        self.assertLess(sum(fg), sum((160, 82, 45)))
        self.assertGreater(sum(bg), sum((64, 42, 22)))

    def test_draw_world_tile_keeps_furniture_as_single_centered_glyph_when_zoomed(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace(zoom_levels=(1.0,), zoom_index=0)
        chair_tile = SimpleNamespace(name="Wooden Chair", char=ord("c"), color=(180, 140, 90))

        console_renderer._draw_world_tile(console, world, 0, 0, 1, 1, chair_tile, (180, 140, 90), (50, 30, 20))

        glyph_calls = [call for call in console.print_calls if call["string"] == "c"]
        self.assertEqual(len(glyph_calls), 1)
        self.assertEqual((glyph_calls[0]["x"], glyph_calls[0]["y"]), (1, 1))

    def test_draw_world_tile_keeps_ground_tiles_zoom_filled(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace(zoom_levels=(1.0,), zoom_index=0)
        floor_tile = SimpleNamespace(name="Wood Floor", char=ord("."), color=(120, 80, 40))

        console_renderer._draw_world_tile(console, world, 0, 0, 1, 1, floor_tile, (120, 80, 40), (60, 40, 20))

        glyph_calls = [call for call in console.print_calls if call["string"] == "."]
        self.assertEqual(len(glyph_calls), 1)

    def test_draw_world_tile_uses_textured_fill_for_zoomed_terrain(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace(zoom_levels=(2.0,), zoom_index=0)
        floor_tile = SimpleNamespace(name="Wood Floor", char=ord("."), color=(120, 80, 40))

        with patch("rendering.console_renderer.zoomed_sprite_codepoint", side_effect=AssertionError("terrain should not stamp sprites")):
            console_renderer._draw_world_tile(console, world, 0, 0, 1, 1, floor_tile, (120, 80, 40), (60, 40, 20))

        self.assertEqual(len(console.print_calls), 4)
        self.assertTrue(all(call.get("bg") is not None for call in console.print_calls))

    def test_draw_world_tile_uses_zoomed_sprite_stamp_when_available(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace(zoom_levels=(2.0,), zoom_index=0)
        tile = SimpleNamespace(name="Tree", char=0xE000, color=(90, 180, 90))

        with patch("rendering.console_renderer.zoomed_sprite_codepoint", side_effect=lambda _base, _zoom, x, y: 0xF0000 + (y * 2) + x):
            console_renderer._draw_world_tile(console, world, 0, 0, 1, 1, tile, (90, 180, 90), (10, 30, 10))

        self.assertEqual(len(console.print_calls), 4)
        self.assertEqual(
            {call["string"] for call in console.print_calls},
            {chr(0xF0000), chr(0xF0001), chr(0xF0002), chr(0xF0003)},
        )
        self.assertTrue(all(call.get("bg") == (10, 30, 10) for call in console.print_calls))

    def test_draw_entities_uses_logical_visibility_not_stale_render_position(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []
                self.bg = np.zeros((3, 3, 3), dtype=np.uint8)

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        entity = SimpleNamespace(
            x=10,
            y=10,
            render_x=1.0,
            render_y=1.0,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=1),
            color=(120, 130, 140),
        )
        world = SimpleNamespace(
            npcs=[entity],
            village_npcs=[],
            player=SimpleNamespace(x=0, y=0, state=SimpleNamespace(is_riding=False)),
        )
        console = FakeConsole()

        with patch("rendering.console_renderer.is_visible", side_effect=lambda _world, x, y: (x, y) == (1, 1)), \
             patch("rendering.console_renderer.get_entity_sprite", return_value=ord("@")):
            console_renderer._draw_entities(console, world, 0, 0)

        self.assertEqual(console.print_calls, [])

    def test_entity_contrast_boosts_foreground_against_similar_background(self):
        adjusted = console_renderer._ensure_entity_contrast((90, 90, 90), (80, 80, 80))

        self.assertNotEqual(adjusted, (90, 90, 90))
        self.assertGreater(sum(adjusted), 270)

    def test_player_contrast_stays_strong_on_bright_floor(self):
        adjusted = console_renderer._ensure_player_contrast((220, 210, 180))

        self.assertNotEqual(adjusted, (255, 245, 140))
        self.assertLess(sum(adjusted), 220)

    def test_draw_entities_does_not_write_background_fill(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []
                self.bg = np.zeros((2, 2, 3), dtype=np.uint8)

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        player = SimpleNamespace(
            x=1,
            y=1,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=2),
        )
        npc = SimpleNamespace(
            x=0,
            y=0,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=1),
            color=(120, 130, 140),
        )
        world = SimpleNamespace(
            npcs=[npc],
            village_npcs=[],
            player=player,
        )

        with patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.get_entity_sprite", return_value=ord("@")):
            console_renderer._draw_entities(console, world, 0, 0)

        self.assertEqual(len(console.print_calls), 2)
        for call in console.print_calls:
            self.assertNotIn("bg", call)
            self.assertIn("fg", call)

    def test_draw_entities_renders_single_centered_sprite_when_zoomed_in(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []
                self.bg = np.zeros((6, 6, 3), dtype=np.uint8)

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        player = SimpleNamespace(
            x=1,
            y=1,
            render_x=1.0,
            render_y=1.0,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=2),
        )
        world = SimpleNamespace(
            npcs=[],
            village_npcs=[],
            player=player,
            zoom_levels=(1.0,),
            zoom_index=0,
        )
        console = FakeConsole()

        with patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.get_entity_sprite", return_value=ord("@")):
            console_renderer._draw_entities(console, world, 0, 0)

        self.assertEqual(len(console.print_calls), 1)
        self.assertEqual(console.print_calls[0]["string"], "@")
        self.assertEqual((console.print_calls[0]["x"], console.print_calls[0]["y"]), (1, 1))

    def test_draw_entities_uses_zoomed_sprite_stamp_when_available(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []
                self.bg = np.zeros((4, 4, 3), dtype=np.uint8)

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        player = SimpleNamespace(
            x=1,
            y=1,
            render_x=1.0,
            render_y=1.0,
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=2),
        )
        world = SimpleNamespace(
            npcs=[],
            village_npcs=[],
            player=player,
            zoom_levels=(2.0,),
            zoom_index=0,
        )
        console = FakeConsole()

        with patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.get_entity_sprite", return_value=0xE000), \
             patch("rendering.console_renderer.zoomed_sprite_codepoint", side_effect=lambda _base, _zoom, x, y: 0xF0100 + (y * 2) + x):
            console_renderer._draw_entities(console, world, 0, 0)

        self.assertEqual(len(console.print_calls), 4)
        self.assertEqual(
            {call["string"] for call in console.print_calls},
            {chr(0xF0100), chr(0xF0101), chr(0xF0102), chr(0xF0103)},
        )
        self.assertTrue(all("bg" not in call for call in console.print_calls))

    def test_entity_marker_skips_overlay_cell_outside_visibility(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        merchant = SimpleNamespace(
            x=5,
            y=5,
            is_sleeping=False,
            economic=SimpleNamespace(profession="Merchant"),
            combat=SimpleNamespace(is_hostile_to_player=False),
            physical=SimpleNamespace(is_dead=False),
        )
        world = SimpleNamespace(npcs=[merchant], village_npcs=[])
        console = FakeConsole()

        with patch("rendering.console_renderer.is_visible", side_effect=lambda _world, x, y: (x, y) == (5, 5)):
            console_renderer._draw_entity_markers(console, world, 0, 0, {"entity": merchant})

        self.assertEqual(console.print_calls, [])

    def test_draw_entity_markers_requires_focused_entity(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        merchant = SimpleNamespace(
            x=5,
            y=5,
            is_sleeping=False,
            economic=SimpleNamespace(profession="Merchant"),
            combat=SimpleNamespace(is_hostile_to_player=False),
            physical=SimpleNamespace(is_dead=False),
        )
        world = SimpleNamespace(npcs=[merchant], village_npcs=[])
        console = FakeConsole()

        with patch("rendering.console_renderer.is_visible", return_value=True):
            console_renderer._draw_entity_markers(console, world, 0, 0, {"entity": None})

        self.assertEqual(console.print_calls, [])

    def test_draw_orders_entities_after_world_lighting_and_before_overlays(self):
        class FakeConsole:
            def __init__(self):
                self.width = 1
                self.height = 1
                self.fg = np.zeros((1, 1, 3), dtype=np.uint8)
                self.bg = np.zeros((1, 1, 3), dtype=np.uint8)
                self.print_calls = []

            def clear(self):
                pass

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

            def draw_frame(self, *args, **kwargs):
                pass

        tile = SimpleNamespace(name="Plains", char=ord("."), color=(10, 20, 30), blocks_fov=False)
        chunk = SimpleNamespace(is_terrain_generated=True, tiles=[[tile]])
        player = SimpleNamespace(x=0, y=0, state=SimpleNamespace(current_path=[]))
        world = SimpleNamespace(
            explored_map=np.zeros((1, 1), dtype=bool),
            player_fov_map=np.ones((1, 1), dtype=bool),
            chunks=[[chunk]],
            _generate_chunk_detail=lambda *args, **kwargs: None,
            get_tile_at=lambda x, y: tile,
            visual_effects=[],
            npcs=[],
            village_npcs=[],
            player=player,
            items_on_map={},
            weather="clear",
            mouse_x=-1,
            mouse_y=-1,
            interaction_context={"active": False},
            game_state="PLAYING",
            game_time=0,
            chat_ui_active=False,
            trade_ui_active=False,
            chat_log=[],
        )
        console = FakeConsole()
        order = []

        with patch.object(console_renderer, "MAP_WIDTH", 1), \
             patch.object(console_renderer, "MAP_HEIGHT", 1), \
             patch.object(console_renderer, "WORLD_WIDTH", 1), \
             patch.object(console_renderer, "WORLD_HEIGHT", 1), \
             patch.object(console_renderer, "CHUNK_SIZE", 1), \
             patch("rendering.console_renderer._apply_lighting_and_depth", side_effect=lambda *args: order.append("lighting")), \
             patch("rendering.console_renderer._draw_entities", side_effect=lambda *args: order.append("entities")), \
             patch("rendering.console_renderer._draw_entity_markers", side_effect=lambda *args: order.append("entity_markers")), \
             patch("rendering.console_renderer._draw_world_markers", side_effect=lambda *args: order.append("world_markers")), \
             patch("rendering.console_renderer.draw_status_panel"), \
             patch("rendering.console_renderer.draw_cursor_info"), \
             patch("rendering.console_renderer._get_focus_target", return_value={"x": None, "y": None, "label": "", "actions": [], "source": "", "entity": None}), \
             patch("rendering.console_renderer._draw_focus_badge"), \
             patch("rendering.console_renderer.draw_weather_overlay"), \
             patch("rendering.console_renderer._get_visible_nearby_entities", return_value=[]):
            console_renderer.draw(console, world, 0, 0)

        self.assertEqual(order, ["lighting", "entities", "entity_markers", "world_markers"])

    def test_draw_skips_label_when_overlay_cell_is_not_visible(self):
        class FakeConsole:
            def __init__(self):
                self.width = 3
                self.height = 3
                self.fg = np.zeros((3, 3, 3), dtype=np.uint8)
                self.bg = np.zeros((3, 3, 3), dtype=np.uint8)
                self.print_calls = []

            def clear(self):
                pass

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

            def draw_frame(self, *args, **kwargs):
                pass

        tile = SimpleNamespace(name="Plains", char=ord("."), color=(10, 20, 30), blocks_fov=False)
        chunk = SimpleNamespace(is_terrain_generated=True, tiles=[[tile for _ in range(3)] for _ in range(3)])
        entity = SimpleNamespace(
            x=1,
            y=1,
            name="Villager",
            state=SimpleNamespace(is_riding=False),
            render_order=SimpleNamespace(value=1),
            color=(120, 130, 140),
            physical=SimpleNamespace(is_dead=False),
        )
        player = SimpleNamespace(x=0, y=0, state=SimpleNamespace(current_path=[]))
        world = SimpleNamespace(
            explored_map=np.ones((3, 3), dtype=bool),
            player_fov_map=np.ones((3, 3), dtype=bool),
            chunks=[[chunk, chunk, chunk], [chunk, chunk, chunk], [chunk, chunk, chunk]],
            _generate_chunk_detail=lambda *args, **kwargs: None,
            get_tile_at=lambda x, y: tile,
            visual_effects=[],
            npcs=[entity],
            village_npcs=[],
            player=player,
            items_on_map={},
            weather="clear",
            mouse_x=-1,
            mouse_y=-1,
            interaction_context={"active": False},
            game_state="PLAYING",
            game_time=0,
            chat_ui_active=False,
            trade_ui_active=False,
            chat_log=[],
            get_entity_display_name=lambda e: e.name,
        )
        console = FakeConsole()

        with patch.object(console_renderer, "MAP_WIDTH", 3), \
             patch.object(console_renderer, "MAP_HEIGHT", 3), \
             patch.object(console_renderer, "WORLD_WIDTH", 3), \
             patch.object(console_renderer, "WORLD_HEIGHT", 3), \
             patch.object(console_renderer, "CHUNK_SIZE", 1), \
             patch("rendering.console_renderer._apply_lighting_and_depth"), \
             patch("rendering.console_renderer._draw_entities"), \
             patch("rendering.console_renderer._draw_entity_markers"), \
             patch("rendering.console_renderer._draw_world_markers"), \
             patch("rendering.console_renderer.draw_status_panel"), \
             patch("rendering.console_renderer.draw_cursor_info"), \
             patch("rendering.console_renderer._get_focus_target", return_value={"x": None, "y": None, "label": "", "actions": [], "source": "", "entity": None}), \
             patch("rendering.console_renderer._draw_focus_badge"), \
             patch("rendering.console_renderer.draw_weather_overlay"), \
             patch("rendering.console_renderer._get_visible_nearby_entities", return_value=[(1, entity)]), \
             patch("rendering.console_renderer.is_visible", side_effect=lambda _world, x, y: (x, y) != (1, 0)):
            console_renderer.draw(console, world, 0, 0)

        label_calls = [call for call in console.print_calls if call.get("string") == "Villager"]
        self.assertEqual(label_calls, [])


class TestConsoleRendererLighting(unittest.TestCase):
    def test_apply_lighting_and_depth_respects_console_buffer_bounds(self):
        console = SimpleNamespace(
            width=65,
            height=40,
            fg=np.zeros((40, 65, 3), dtype=np.uint8),
            bg=np.zeros((40, 65, 3), dtype=np.uint8),
        )
        world = SimpleNamespace(
            player=SimpleNamespace(x=1, y=1),
            current_light_level_name="DAY",
            get_tile_at=lambda x, y: SimpleNamespace(blocks_fov=True),
        )

        with patch("rendering.console_renderer.is_visible", return_value=True):
            console_renderer._apply_lighting_and_depth(console, world, 0, 0)


class TestConsoleRendererFocusBadge(unittest.TestCase):
    def test_focus_badge_does_not_pulse_plain_tile_focus(self):
        class FakeConsole:
            def __init__(self):
                self.bg = np.zeros((3, 3, 3), dtype=np.uint8)
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace(game_time=0)
        focus = {"x": 1, "y": 1, "label": "Facing Plains", "entity": None}

        console_renderer._draw_focus_badge(console, world, focus, 0, 0)

        self.assertEqual(console.print_calls, [])
        # In our shim, bg is just a nested list representing the 3D array
        has_color = any(val > 0 for row in console.bg for pixel in row for val in pixel)
        self.assertFalse(has_color)

    def test_focus_badge_pulses_and_prints_for_visible_entity_focus(self):
        class FakeConsole:
            def __init__(self):
                self.bg = np.zeros((3, 3, 3), dtype=np.uint8)
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        entity = SimpleNamespace(physical=SimpleNamespace(is_dead=False))
        world = SimpleNamespace(game_time=0)
        focus = {"x": 1, "y": 1, "label": "Merchant", "entity": entity}

        with patch("rendering.console_renderer.is_visible", return_value=True):
            console_renderer._draw_focus_badge(console, world, focus, 0, 0)

        self.assertEqual(len(console.print_calls), 1)
        # In our shim, check the specific pixel modified
        self.assertGreater(sum(console.bg[1][1]), 0)


class TestWeatherOverlayShelter(unittest.TestCase):
    def test_weather_overlay_draws_on_exposed_outdoor_tiles(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        world = SimpleNamespace(
            weather="rain",
            game_time=0,
            get_building_at=lambda x, y: None,
        )

        with patch.object(console_renderer, "MAP_WIDTH", 1), \
             patch.object(console_renderer, "MAP_HEIGHT", 1), \
             patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.hash", return_value=0):
            console_renderer.draw_weather_overlay(console, world, 0, 0)

        self.assertEqual(len(console.print_calls), 1)

    def test_weather_overlay_skips_visible_building_interior_tiles(self):
        class FakeConsole:
            def __init__(self):
                self.print_calls = []

            def print(self, **kwargs):
                self.print_calls.append(kwargs)

        console = FakeConsole()
        building = SimpleNamespace(global_origin_x=10, global_origin_y=10, width=7, height=6)
        world = SimpleNamespace(
            weather="rain",
            game_time=0,
            get_building_at=lambda x, y: building if (x, y) == (12, 12) else None,
        )

        with patch.object(console_renderer, "MAP_WIDTH", 1), \
             patch.object(console_renderer, "MAP_HEIGHT", 1), \
             patch("rendering.console_renderer.is_visible", return_value=True), \
             patch("rendering.console_renderer.hash", return_value=0):
            console_renderer.draw_weather_overlay(console, world, 12, 12)

        self.assertEqual(console.print_calls, [])



class TestDialogueStateRegression(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC",
            "personality": "neutral",
            "dialogue": ["..."],
        })
        self.world = World(seed=11)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_continue_npc_conversation_uses_nested_social_and_knowledge_state(self):
        speaker = engine.NPC(10, 10, name="Speaker")
        listener = engine.NPC(11, 10, name="Listener")
        speaker.social.personality = "gregarious"
        listener.social.personality = "reserved"
        speaker.social.relationships[listener.id] = 77
        speaker.knowledge.known_events["storm"] = SimpleNamespace(description="A storm rolled in.")
        self.world.player.x = 10
        self.world.player.y = 10
        self.world.player.physical = SimpleNamespace(hearing_radius=12)
        speaker.speech_volume = 12
        self.mock_call_llm.return_value = "Nice weather we're having."

        self.world._continue_npc_conversation(speaker, listener)

        prompt = self.mock_call_llm.call_args.args[0]
        self.assertIn("gregarious", prompt)
        self.assertIn("reserved", prompt)
        self.assertIn("77", prompt)
        self.assertIn("A storm rolled in.", prompt)

    def test_continue_npc_dialogue_share_location_updates_nested_relationships(self):
        npc_target = engine.NPC(10, 10, name="Villager")
        building = SimpleNamespace(id="smithy_1", building_type="blacksmith_shop")
        self.world.buildings_by_id[building.id] = building
        self.world.player.knowledge.known_locations[building.id] = (4, 5)

        self.world.continue_npc_dialogue(npc_target, "I know where the blacksmith shop is")

        self.assertEqual(npc_target.knowledge.known_locations["blacksmith shop"], (4, 5))
        self.assertEqual(npc_target.social.relationships[self.world.player.id], 60)
        self.assertFalse(hasattr(npc_target, "relationships"))

    def test_continue_npc_dialogue_gossip_uses_nested_known_events_and_titles(self):
        npc_target = engine.NPC(10, 10, name="Villager")
        self.world.player.social.title = "the Bold"
        npc_target.knowledge.known_events["news_1"] = SimpleNamespace(
            subject_id=self.world.player.id,
            target_id=None,
            description="{subject} defeated a beast.",
        )
        self.mock_call_llm.return_value = "I heard a remarkable tale."

        self.world.continue_npc_dialogue(npc_target, "Any gossip?")

        prompt = self.mock_call_llm.call_args.args[0]
        self.assertIn("the Bold", prompt)
        self.assertIn("defeated a beast", prompt)
        self.assertEqual(self.world.chat_ui_history[-1], ("Villager", "I heard a remarkable tale."))

    def test_family_display_name_prefers_relationship_for_placeholder_names(self):
        npc_target = engine.NPC(
            10, 10,
            name="Mother Family_9990",
            family_ties={"relation_to_player": "mother"},
            player_id=self.world.player.id,
        )

        self.assertEqual(self.world.get_entity_display_name(npc_target), "Mother")
        self.assertEqual(self.world.get_entity_display_name(npc_target, include_relationship=True), "Mother")

    def test_entity_display_name_appends_profession_title(self):
        npc_target = engine.NPC(10, 10, name="Ada Graves")
        npc_target.economic.profession = "Farmer"

        self.assertEqual(self.world.get_entity_display_name(npc_target), "Ada Graves (Farmer)")
        self.assertEqual(npc_target.get_display_name(viewer=self.world.player), "Ada Graves (Farmer)")

    def test_family_display_name_keeps_relationship_and_adds_profession_title(self):
        npc_target = engine.NPC(
            10, 10,
            name="Mother Family_9990",
            family_ties={"relation_to_player": "mother"},
            player_id=self.world.player.id,
        )
        npc_target.economic.profession = "Farmer"

        self.assertEqual(self.world.get_entity_display_name(npc_target), "Mother (Farmer)")
        self.assertEqual(self.world.get_entity_display_name(npc_target, include_relationship=True), "Mother (Farmer)")
        self.assertEqual(npc_target.get_display_name(viewer=self.world.player, include_relationship=True), "Mother (Farmer)")

    def test_world_assigns_player_family_last_name_to_full_name(self):
        world = World(seed=11, player_first_name="Ada")

        self.assertTrue(world.player.name.startswith("Ada "))
        self.assertEqual(world.player.name.split()[-1], world.player.social.family_ties["last_name"])

    def test_start_npc_dialogue_fallback_uses_relationship_context(self):
        npc_target = engine.NPC(
            10, 10,
            name="Mother Family_9990",
            family_ties={"relation_to_player": "mother"},
            player_id=self.world.player.id,
        )
        self.mock_call_llm.return_value = ""

        self.world.start_npc_dialogue(npc_target)

        prompt = self.mock_call_llm.call_args.args[0]
        self.assertIn("You are the player's mother.", prompt)
        self.assertEqual(self.world.chat_ui_history[-1][0], "Mother")
        self.assertIn("fed", self.world.chat_ui_history[-1][1].lower())

    def test_continue_npc_dialogue_parses_fenced_json_without_dumping_payload(self):
        npc_target = engine.NPC(10, 10, name="Theo Fletcher")
        npc_target.economic.profession = "Farmer"
        self.mock_call_llm.return_value = """```json
{"response":"I'm doing alright, all things considered.","goal":"continue_conversation"}
```"""

        self.world.continue_npc_dialogue(npc_target, "how are you doing?")

        self.assertEqual(self.world.chat_ui_history[-1], ("Theo Fletcher (Farmer)", "I'm doing alright, all things considered."))

    def test_start_npc_dialogue_rejects_placeholder_player_name_output(self):
        npc_target = engine.NPC(
            10, 10,
            name="Ada Graves",
            family_ties={"relation_to_player": "sister"},
            player_id=self.world.player.id,
        )
        npc_target.economic.profession = "Farmer"
        self.mock_call_llm.return_value = "Oh, [Player Name]! What are you doing out this late?"

        self.world.start_npc_dialogue(npc_target)

        self.assertEqual(self.world.chat_ui_history[-1], ("Ada Graves (Farmer)", "Hey. What do you need?"))

    def test_continue_npc_dialogue_rejects_placeholder_player_name_output(self):
        npc_target = engine.NPC(10, 10, name="Ada Graves")
        npc_target.economic.profession = "Farmer"
        self.mock_call_llm.return_value = json.dumps({
            "response": "Of course, [Player Name].",
            "goal": "continue_conversation",
        })

        self.world.continue_npc_dialogue(npc_target, "how are you?")

        self.assertEqual(self.world.chat_ui_history[-1], ("Ada Graves (Farmer)", "I've been alright."))

    def test_npc_conversation_publishes_ambient_speech_and_applies_social_goal(self):
        speaker = engine.NPC(10, 10, name="A")
        listener = engine.NPC(11, 10, name="B")
        speaker.schedule.home_building_id = "home_1"
        self.world.buildings_by_id["home_1"] = SimpleNamespace(global_center_x=4, global_center_y=5)
        self.world.player.x = 10
        self.world.player.y = 10
        self.world.player.physical = SimpleNamespace(hearing_radius=12)
        speaker.speech_volume = 12

        task_key = ("npc_conversation", speaker.id, listener.id)
        future = unittest.mock.Mock()
        future.done.return_value = True
        future.result.return_value = json.dumps({"response": "Come by later.", "goal": "go_home"})
        self.world._background_llm_tasks[task_key] = future

        self.world._continue_npc_conversation(speaker, listener)

        self.assertEqual(speaker.schedule.current_task, "going_home")
        self.assertEqual(self.world.active_ambient_speech[-1].text, "Come by later.")
        self.assertNotEqual(self.world.chat_log[-1], "You overhear A tell B: Come by later.")

    def test_distant_npc_conversation_uses_fallback_without_llm_task(self):
        speaker = engine.NPC(40, 40, name="A")
        listener = engine.NPC(41, 40, name="B")
        self.world.player.x = 0
        self.world.player.y = 0
        self.world.player.physical = SimpleNamespace(hearing_radius=3)
        speaker.speech_volume = 3
        listener.speech_volume = 3
        prior_log_count = len(self.world.chat_log)

        self.world._continue_npc_conversation(speaker, listener)

        self.assertFalse(self.world._background_llm_tasks)
        self.assertTrue(speaker.current_conversation)
        self.assertEqual(len(self.world.chat_log), prior_log_count)

    def test_distant_ambient_speech_does_not_submit_llm_task(self):
        npc = engine.NPC(30, 30, name="Far Villager")
        npc.last_speech_time = 0
        npc.speech_volume = 3
        self.world.npcs = [npc]
        self.world.village_npcs = []
        self.world.player.x = 0
        self.world.player.y = 0
        self.world.player.physical = SimpleNamespace(hearing_radius=3)

        with patch("engine.time.time", return_value=100.0), \
             patch("engine.random.randint", return_value=10):
            self.world._handle_npc_speech()

        self.assertFalse(self.world._background_llm_tasks)

    def test_update_entity_titles_writes_social_title(self):
        npc = engine.NPC(10, 10, name="Legend")
        npc.social.fame = 60
        self.world.village_npcs.append(npc)
        self.world.game_time = 100
        self.mock_call_llm.return_value = json.dumps({"title": "the Bold"})

        self.world._update_entity_titles()
        self.world._update_entity_titles()

        self.assertEqual(npc.social.title, "the Bold")
        self.assertFalse(hasattr(npc, "title"))
