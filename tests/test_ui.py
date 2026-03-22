import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import json
import math
import uuid
import numpy as np

import engine
from engine import World
import main
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
            request_open_trade=lambda trade_npc: world.ui_requests.append({"type": "open_trade", "npc": trade_npc}),
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
            request_close_trade=lambda target_npc=None: world.ui_requests.append({"type": "close_trade", "npc": target_npc}),
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
            ui_requests=[{"type": "open_dialogue", "npc": npc, "mode": "talk"}],
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
            ui_requests=[{"type": "close_trade", "npc": npc}],
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
            tcod.event.get = lambda: [tcod.event.KeyDown(0, tcod.event.KeySym.A, 0)]
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
        event = tcod.event.KeyDown(0, tcod.event.KeySym.RETURN, 0)

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

        self.assertEqual(world.ui_requests, [{"type": "open_trade", "npc": npc}])
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
            request_open_trade=lambda trade_npc: world.ui_requests.append({"type": "open_trade", "npc": trade_npc}),
        )

        took_turn = main.execute_interaction(world, context_handler=SimpleNamespace())

        self.assertFalse(took_turn)
        self.assertFalse(world.interaction_context["active"])
        self.assertTrue(world.trade_ui_active)
        self.assertEqual(world.game_state, "TRADE_MENU")

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

        console_renderer._draw_visual_effect(console, text_effect, 0, 0)
        console_renderer._draw_visual_effect(console, projectile_effect, 0, 0)

        rendered = [call["string"] for call in console.print_calls]
        self.assertIn("12", rendered)
        self.assertIn("*", rendered)


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
        self.assertEqual(self.world.chat_ui_history[-1], (npc_target.name, "I heard a remarkable tale."))

    def test_family_display_name_prefers_relationship_for_placeholder_names(self):
        npc_target = engine.NPC(
            10, 10,
            name="Mother Family_9990",
            family_ties={"relation_to_player": "mother"},
            player_id=self.world.player.id,
        )

        self.assertEqual(self.world.get_entity_display_name(npc_target), "Mother")
        self.assertEqual(self.world.get_entity_display_name(npc_target, include_relationship=True), "Mother")

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
        self.mock_call_llm.return_value = """```json
{"response":"I'm doing alright, all things considered.","goal":"continue_conversation"}
```"""

        self.world.continue_npc_dialogue(npc_target, "how are you doing?")

        self.assertEqual(self.world.chat_ui_history[-1], ("Theo Fletcher", "I'm doing alright, all things considered."))

    def test_start_npc_dialogue_rejects_placeholder_player_name_output(self):
        npc_target = engine.NPC(
            10, 10,
            name="Ada Graves",
            family_ties={"relation_to_player": "sister"},
            player_id=self.world.player.id,
        )
        self.mock_call_llm.return_value = "Oh, [Player Name]! What are you doing out this late?"

        self.world.start_npc_dialogue(npc_target)

        self.assertEqual(self.world.chat_ui_history[-1], ("Ada Graves", "Hey. What do you need?"))

    def test_continue_npc_dialogue_rejects_placeholder_player_name_output(self):
        npc_target = engine.NPC(10, 10, name="Ada Graves")
        self.mock_call_llm.return_value = json.dumps({
            "response": "Of course, [Player Name].",
            "goal": "continue_conversation",
        })

        self.world.continue_npc_dialogue(npc_target, "how are you?")

        self.assertEqual(self.world.chat_ui_history[-1], ("Ada Graves", "I've been alright."))

    def test_npc_conversation_logs_overheard_line_and_applies_social_goal(self):
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

        self.assertEqual(speaker.schedule.current_task, "going home")
        self.assertEqual(self.world.chat_log[-1], "You overhear A tell B: Come by later.")

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
