import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace
import json
import math
import uuid

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
        )

        main.apply_ui_requests(world, context_handler)

        self.assertEqual(world.game_state, "DIALOGUE")
        self.assertIs(world.chat_ui_target_npc, npc)
        self.assertEqual(world.chat_ui_mode, "talk")
        self.assertTrue(world.chat_ui_active)
        self.assertFalse(world.trade_ui_active)
        self.assertIsNone(world.trade_ui_npc_target)
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

    def test_update_entity_titles_writes_social_title(self):
        npc = engine.NPC(10, 10, name="Legend")
        npc.social.fame = 60
        self.world.village_npcs.append(npc)
        self.world.game_time = 100
        self.mock_call_llm.return_value = json.dumps({"title": "the Bold"})

        self.world._update_entity_titles()

        self.assertEqual(npc.social.title, "the Bold")
        self.assertFalse(hasattr(npc, "title"))
