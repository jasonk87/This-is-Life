import unittest
from unittest.mock import patch
import importlib
from types import SimpleNamespace
import config
import tcod_compat
import tcod.event

# Set test-specific configurations
config.WORLD_WIDTH = 100
config.WORLD_HEIGHT = 80
config.DAY_LENGTH_TICKS = 1000
config.NPC_SCHEDULE_UPDATE_INTERVAL = 50
config.ENABLE_OLLAMA_CONNECTION = False

# Reload the engine module to apply the config changes
import engine
importlib.reload(engine)

from engine import World
import json
import main
from rendering import console_renderer

class TestGame(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        # Canned response for NPC generation
        mock_npc_data = {
            "name": "Test NPC",
            "personality": "test",
            "family_ties": "none",
            "attitude_to_player": "neutral",
            "dialogue": ["Hello."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists"
        }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_world_initialization(self):
        try:
            world = World()
            self.assertIsNotNone(world)
            self.assertIsNotNone(world.player)
        except Exception as e:
            self.fail(f"World initialization failed with an exception: {e}")


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



class TestPopulateNpcsCompatibility(unittest.TestCase):
    def test_populate_npcs_spawns_traveling_merchants_when_missing(self):
        world = engine.World.__new__(engine.World)
        world.npcs = []
        world._spawn_traveling_merchants = unittest.mock.Mock()

        world._populate_npcs()

        world._spawn_traveling_merchants.assert_called_once_with()

    def test_populate_npcs_skips_spawning_when_traveling_merchant_exists(self):
        world = engine.World.__new__(engine.World)
        world.npcs = [SimpleNamespace(economic=SimpleNamespace(profession="Traveling Merchant"))]
        world._spawn_traveling_merchants = unittest.mock.Mock()

        world._populate_npcs()

        world._spawn_traveling_merchants.assert_not_called()



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


class TestWorldOccupancyMap(unittest.TestCase):
    def test_update_entity_position_keeps_occupancy_map_in_sync(self):
        world = object.__new__(engine.World)
        npc = SimpleNamespace(id=2, x=3, y=4, physical=SimpleNamespace(is_dead=False))
        new_coords = (config.CHUNK_SIZE + 1, 6)
        world.player = SimpleNamespace(id=1, x=1, y=1)
        world.village_npcs = [npc]
        world.npcs = []
        world.entity_positions = {(1, 1): 1, (3, 4): 2}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {1, 2}}

        engine.World._update_entity_position(world, npc, *new_coords)

        self.assertNotIn((3, 4), world.entity_positions)
        self.assertEqual(world.entity_positions[new_coords], 2)
        self.assertEqual((npc.x, npc.y), new_coords)
        self.assertEqual(world.entities_by_chunk[(0, 0)], {1})
        self.assertEqual(world.entities_by_chunk[(1, 0)], {2})

    def test_update_npc_movement_updates_occupancy_map_after_move(self):
        npc = SimpleNamespace(
            id=2,
            x=3,
            y=4,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[(3, 4), (4, 4)],
                current_destination_coords=(4, 4),
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        world = object.__new__(engine.World)
        world.player = SimpleNamespace(id=1, x=10, y=10)
        world.village_npcs = [npc]
        world.npcs = []
        world.entity_positions = {(10, 10): 1, (3, 4): 2}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {2}, (1, 1): {1}}
        world.add_message_to_chat_log = unittest.mock.Mock()
        world.get_tile_at = lambda x, y: SimpleNamespace(passable=True)
        world._is_predator = lambda entity: False

        engine.World._update_npc_movement(world)

        self.assertEqual((npc.x, npc.y), (4, 4))
        self.assertNotIn((3, 4), world.entity_positions)
        self.assertEqual(world.entity_positions[(4, 4)], 2)
        self.assertEqual(npc.schedule.current_path, [])
        self.assertIn(2, world.entities_by_chunk[(0, 0)])

    def test_update_npc_movement_waits_in_queue_when_tile_is_temporarily_blocked(self):
        blocker = SimpleNamespace(
            id=2,
            x=4,
            y=4,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[],
                current_destination_coords=None,
                path_blocked_turns=0,
                last_blocked_position=None,
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        follower = SimpleNamespace(
            id=3,
            x=3,
            y=4,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[(3, 4), (4, 4), (5, 4)],
                current_destination_coords=(5, 4),
                path_blocked_turns=0,
                last_blocked_position=None,
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        world = object.__new__(engine.World)
        world.player = SimpleNamespace(id=1, x=10, y=10)
        world.village_npcs = [blocker, follower]
        world.npcs = []
        world.entity_positions = {(10, 10): 1, (4, 4): 2, (3, 4): 3}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {2, 3}, (1, 1): {1}}
        world.add_message_to_chat_log = unittest.mock.Mock()
        world.get_tile_at = lambda x, y: SimpleNamespace(passable=True)
        world._is_predator = lambda entity: False
        world.get_entity_by_id = lambda entity_id: {1: world.player, 2: blocker, 3: follower}.get(entity_id)

        engine.World._update_npc_movement(world)

        self.assertEqual((follower.x, follower.y), (3, 4))
        self.assertEqual(follower.schedule.current_path, [(3, 4), (4, 4), (5, 4)])
        self.assertEqual(follower.schedule.path_blocked_turns, 1)
        self.assertEqual(follower.schedule.last_blocked_position, (4, 4))


class TestWorldInteractionActions(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC",
            "personality": "test",
            "family_ties": "none",
            "attitude_to_player": "neutral",
            "dialogue": ["Hello."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists"
        })
        self.world = World()

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_trade_action_uses_npc_economic_profession(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"

        actions = self.world._get_actions_for_entity({"type": "npc", "data": merchant, "name": merchant.name})

        self.assertIn("Talk", actions)
        self.assertIn("Attack", actions)
        self.assertIn("Trade", actions)

    def test_initialize_trade_session_uses_schedule_work_building_id(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        merchant.schedule.work_building_id = "shop_1"

        shop = SimpleNamespace(building_type="general_store", building_inventory={"raw_log": 3, "money": 25})
        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = merchant
        self.world.buildings_by_id = {"shop_1": shop}

        with patch.object(self.world, "_get_village_for_npc", return_value=None), \
             patch.object(self.world, "get_dynamic_price", return_value=7):
            self.world.initialize_trade_session()

        self.assertIn(("raw_log", 3, 7), self.world.trade_ui_merchant_inventory_snapshot)

    def test_handle_trade_action_uses_schedule_work_building_id(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        merchant.schedule.work_building_id = "shop_1"

        shop = SimpleNamespace(building_type="general_store", building_inventory={"raw_log": 1, "money": 0})
        self.world.trade_ui_active = True
        self.world.trade_ui_npc_target = merchant
        self.world.trade_ui_player_selling = False
        self.world.trade_ui_merchant_inventory_snapshot = [("raw_log", 1, 5)]
        self.world.trade_ui_merchant_item_index = 0
        self.world.buildings_by_id = {"shop_1": shop}

        self.world.player.economic.money = 10 # Provide enough money for purchase
        with patch.object(self.world, "_get_village_for_npc", return_value=None):
            self.world.handle_trade_action()

        self.assertTrue(self.world.player.has_item("raw_log", 1))
        self.assertEqual(shop.building_inventory["money"], 5)
        self.assertNotIn("raw_log", shop.building_inventory)

    def test_handle_npc_goal_start_trade_activates_trade_ui(self):
        merchant = engine.NPC(0, 0, name="Merchant")
        merchant.economic.profession = "Merchant"
        self.world.chat_ui_active = True
        self.world.needs_text_input = True

        with patch.object(self.world, "initialize_trade_session") as mock_init:
            self.world._handle_npc_goal(merchant, "start_trade", "")
            main.apply_ui_requests(self.world)

        self.assertEqual(self.world.game_state, "TRADE_MENU")
        self.assertTrue(self.world.trade_ui_active)
        self.assertIs(self.world.trade_ui_npc_target, merchant)
        self.assertFalse(self.world.chat_ui_active)
        self.assertFalse(self.world.needs_text_input)
        mock_init.assert_called_once_with()

    def test_npc_attempt_fish_uses_schedule_work_building_id(self):
        fisher = engine.NPC(0, 0, name="Fisher")
        fisher.schedule.work_building_id = "dock_1"
        self.world.buildings_by_id = {
            "dock_1": SimpleNamespace(building_inventory={}, building_type="dock")
        }

        with patch.object(self.world, "get_tile_at", return_value=SimpleNamespace(name="Water")), \
             patch("engine.random.random", return_value=0.0), \
             patch("engine.random.choice", return_value="fish"):
            self.world.npc_attempt_fish(fisher, 5, 5)

        self.assertEqual(self.world.buildings_by_id["dock_1"].building_inventory["raw_fish"], 1)

    def test_player_attempt_attack_marks_target_hostile_via_combat_state(self):
        target = engine.NPC(1, 1, name="Target")
        target.combat.is_hostile_to_player = False

        with patch.object(self.world, "_call_llm", return_value=None):
            self.world.player_attempt_attack(target)

        self.assertTrue(target.combat.is_hostile_to_player)

    def test_handle_witness_reaction_uses_schedule_state_for_reporting(self):
        witness = engine.NPC(2, 2, name="Witness")
        witness.combat.is_hostile_to_player = False

        sheriff_office = SimpleNamespace(global_center_x=10, global_center_y=12)
        with patch.object(self.world, "_call_llm", return_value=json.dumps({"reaction": "report_crime", "dialogue": "Guards!"})), \
             patch.object(self.world, "_find_nearest_building_of_type", return_value=sheriff_office):
            self.world._handle_witness_reaction(witness, "theft", self.world.player)

        self.assertEqual(witness.schedule.current_task, "going_to_report_crime")
        self.assertEqual(witness.task_target_coords, (10, 12))
        self.assertEqual(witness.schedule.current_path, [])

    def test_player_attempt_ride_animal_clears_schedule_pathing(self):
        mount = engine.Animal(3, 4, name="Deer", animal_type="deer")
        mount.is_tame = True
        mount.owner = self.world.player
        mount.schedule.current_path = [(3, 4), (4, 4)]
        mount.schedule.current_destination_coords = (4, 4)

        self.world.player_attempt_ride_animal(mount)

        self.assertEqual(mount.schedule.current_path, [])
        self.assertIsNone(mount.schedule.current_destination_coords)

    def test_handle_npc_work_sub_tasks_marks_missing_workplace_as_idle_confused(self):
        worker = engine.NPC(0, 0, name="Worker")
        worker.economic.profession = "Farmer"
        worker.schedule.work_building_id = "missing_farm"

        handled = self.world._handle_npc_work_sub_tasks(worker)

        self.assertTrue(handled)
        self.assertEqual(worker.schedule.current_task, "idle_confused")

    def test_execute_completed_work_sub_task_uses_command_registry(self):
        worker = engine.NPC(0, 0, name="Miller")
        worker.economic.profession = "Miller"
        work_building = SimpleNamespace(building_inventory={"wheat": 2, "flour": 0})

        self.world._execute_completed_work_sub_task(
            worker,
            work_building,
            "mill_flour",
            {"id": "mill_flour"},
        )

        self.assertEqual(work_building.building_inventory["wheat"], 1)
        self.assertEqual(work_building.building_inventory["flour"], 1)

    def test_npc_eat_from_inventory_reduces_physical_hunger(self):
        npc = engine.NPC(0, 0, name="Hungry NPC")
        npc.physical.hunger = 40
        inventory = {"apple": 1}

        found_food, consumed_food = self.world._npc_eat_from_inventory(npc, inventory)

        self.assertTrue(found_food)
        self.assertTrue(consumed_food)
        self.assertLess(npc.physical.hunger, 40)
        self.assertNotIn("apple", inventory)

class TestTemperatureSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)
        self.world = World()

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_season_progression(self):
        from config import DAY_LENGTH_TICKS, DAYS_PER_SEASON
        self.assertEqual(self.world.seasons[self.world.current_season_index], "Spring")
        self.world.game_time = DAY_LENGTH_TICKS * DAYS_PER_SEASON
        self.world._update_season()
        self.assertEqual(self.world.seasons[self.world.current_season_index], "Summer")
        self.world.game_time = DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4
        self.world._update_season()
        self.assertEqual(self.world.seasons[self.world.current_season_index], "Spring")

    def test_ambient_temperature_calculation(self):
        self.world.current_season_index = 3 # Winter
        self.world.current_light_level_name = "DEEP_NIGHT"
        # Move player to a snow biome for test
        self.world.player.x = 1
        self.world.player.y = 1
        chunk = self.world.chunks[0][0]
        chunk.biome = "snow"

        self.world._update_player_temperature()

        from config import SEASON_TEMPERATURE_MODIFIERS, BIOME_TEMPERATURE_MODIFIERS, TIME_OF_DAY_TEMPERATURE_MODIFIERS
        expected_temp = (SEASON_TEMPERATURE_MODIFIERS["Winter"] +
                         BIOME_TEMPERATURE_MODIFIERS["snow"] +
                         TIME_OF_DAY_TEMPERATURE_MODIFIERS["DEEP_NIGHT"])
        self.assertAlmostEqual(self.world.ambient_temperature, expected_temp)

    def test_heat_source_effect(self):
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile

        # First, get temperature without any heat source
        self.world._update_player_temperature()
        initial_temp = self.world.ambient_temperature

        fire_pit_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_pit_tile = Tile(char=fire_pit_def['char'], color=fire_pit_def['color'], passable=False, name="fire_pit_lit", properties=fire_pit_def['properties'])

        # Place a fire pit near the player
        fire_x, fire_y = self.world.player.x + 1, self.world.player.y
        self.world.chunks[fire_y // config.CHUNK_SIZE][fire_x // config.CHUNK_SIZE].tiles[fire_y % config.CHUNK_SIZE][fire_x % config.CHUNK_SIZE] = fire_pit_tile

        # Rerun temperature update to capture heat source effect
        self.world._update_player_temperature()
        temp_with_fire = self.world.ambient_temperature

        self.assertGreater(temp_with_fire, initial_temp)

    def test_player_gets_wet_in_rain(self):
        self.world.weather = "rain"
        self.world.player.physical.is_sheltered = False
        self.world._update_player_wetness()
        self.assertTrue(self.world.player.physical.is_wet)
        self.assertGreater(self.world.player.physical.wetness_timer, 0)

    def test_clothing_insulation_effect(self):
        player = self.world.player
        player.physical.temperature = 30 # Set a cold body temp

        self.world._update_player_temperature()
        temp_change_without_cloak = player.physical.temperature - 30

        player.equip_armor("fur_cloak")
        player.physical.temperature = 30 # Reset temp

        self.world._update_player_temperature()
        temp_change_with_cloak = player.physical.temperature - 30

        self.assertGreater(temp_change_with_cloak, temp_change_without_cloak)

    def test_freezing_effect(self):
        player = self.world.player
        initial_hp = player.combat.hp
        player.physical.temperature = 34.0 # Below freezing threshold

        # Update temperature to apply status effect
        self.world._update_player_temperature()
        self.assertIn("Freezing", player.physical.status_effects)

        from config import DAY_LENGTH_TICKS
        ticks_for_damage = DAY_LENGTH_TICKS // 25

        for i in range(ticks_for_damage + 1):
            self.world.game_time += 1
            self.world._apply_temperature_effects(player)

        self.assertLess(player.combat.hp, initial_hp)

    def test_rain_extinguishes_fire(self):
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile

        # 1. Place a lit fire pit
        fire_x, fire_y = self.world.player.x + 2, self.world.player.y
        fire_pit_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_pit_tile = Tile(char=fire_pit_def['char'], color=fire_pit_def['color'], passable=False, name="fire_pit_lit", properties=fire_pit_def['properties'].copy())

        chunk_x, chunk_y = fire_x // config.CHUNK_SIZE, fire_y // config.CHUNK_SIZE
        local_x, local_y = fire_x % config.CHUNK_SIZE, fire_y % config.CHUNK_SIZE
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = fire_pit_tile

        # Verify it's initially lit
        self.assertEqual(self.world.get_tile_at(fire_x, fire_y).name, "fire_pit_lit")

        # 2. Set weather to rain
        self.world.weather = "rain"
        self.world.weather_change_timer = 1000 # Prevent weather from changing during test

        # 3. Ensure the location is not sheltered (mock the shelter check to be certain)
        with patch('engine.World._check_for_shelter', return_value=False) as mock_shelter_check:
            # 4. Call the weather update function
            self.world._update_weather()
            mock_shelter_check.assert_called_with(fire_x, fire_y)

        # 5. Assert the fire is now extinguished
        extinguished_tile = self.world.get_tile_at(fire_x, fire_y)
        self.assertIsNotNone(extinguished_tile)
        self.assertEqual(extinguished_tile.name, "Simple Fire Pit")


class TestAgriculturalSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)
        self.world = World()

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_rain_waters_crops_and_they_grow(self):
        from data.tiles import TILE_DEFINITIONS
        from tile_types import Tile

        # 1. Place a growing wheat tile
        crop_x, crop_y = self.world.player.x + 2, self.world.player.y
        growing_def = TILE_DEFINITIONS["wheat_plant_growing"]
        # Use .copy() on properties to avoid modifying the global definition
        growing_tile = Tile(char=growing_def['char'], color=growing_def['color'], passable=True, name="Growing Wheat", properties=growing_def['properties'].copy())

        chunk_x, chunk_y = crop_x // config.CHUNK_SIZE, crop_y // config.CHUNK_SIZE
        local_x, local_y = crop_x % config.CHUNK_SIZE, crop_y % config.CHUNK_SIZE
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = growing_tile

        self.assertEqual(self.world.get_tile_at(crop_x, crop_y).name, "Growing Wheat")
        self.assertEqual(self.world.get_tile_at(crop_x, crop_y).properties["growth_progress"], 0)

        # 2. Make it rain for enough ticks to water the plant to maturity
        self.world.weather = "rain"
        self.world.weather_change_timer = 1000 # Prevent weather from changing during test
        watering_increment = 5 # From _water_crops
        growth_needed = growing_def['properties']['growth_needed']
        updates_needed = (growth_needed // watering_increment) + 1

        for _ in range(updates_needed):
            self.world._update_weather()

        # Verify progress has been made
        self.assertGreater(self.world.get_tile_at(crop_x, crop_y).properties["growth_progress"], 0)

        # 3. Call the environment update to trigger the evolution
        self.world._update_world_environment()

        # 4. Assert the crop is now mature
        mature_tile = self.world.get_tile_at(crop_x, crop_y)
        self.assertIsNotNone(mature_tile)
        self.assertEqual(mature_tile.name, "Wheat")


class TestNPCBehaviorSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()

        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)

        self.world = World(seed=0)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_npc_seeks_warmth_when_freezing(self):
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from data.tiles import TILE_DEFINITIONS
        from tile_types import Tile
        from entities.base import NPC
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Create a freezing environment and an NPC
        self.world.current_season_index = 3 # Winter
        npc = NPC(x=self.world.player.x + 5, y=self.world.player.y, name="Test NPC")
        self.world.village_npcs.append(npc)

        # 2. Ensure a clear path and place a heat source
        fire_x, fire_y = npc.x + 3, npc.y
        plains_def = TILE_DEFINITIONS["plains"]
        plains_tile = Tile(char=plains_def['char'], color=plains_def['color'], passable=True, name="Plains", properties={})

        # Also clear the NPC's starting tile
        self.world.get_tile_at(npc.x, npc.y) # Ensure chunk is generated
        c_chunk_x, c_chunk_y = npc.x // config.CHUNK_SIZE, npc.y // config.CHUNK_SIZE
        c_local_x, c_local_y = npc.x % config.CHUNK_SIZE, npc.y % config.CHUNK_SIZE
        self.world.chunks[c_chunk_y][c_chunk_x].tiles[c_local_y][c_local_x] = plains_tile

        # Clear a path for the NPC
        for y_offset in range(-2, 3):
            for x_offset in range(0, 6):
                clear_x, clear_y = npc.x + x_offset, npc.y + y_offset
                self.world.get_tile_at(clear_x, clear_y) # Ensure chunk is generated
                c_chunk_x, c_chunk_y = clear_x // config.CHUNK_SIZE, clear_y // config.CHUNK_SIZE
                c_local_x, c_local_y = clear_x % config.CHUNK_SIZE, clear_y % config.CHUNK_SIZE
                self.world.chunks[c_chunk_y][c_chunk_x].tiles[c_local_y][c_local_x] = plains_tile

        fire_pit_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_pit_tile = Tile(char=fire_pit_def['char'], color=fire_pit_def['color'], passable=False, name="fire_pit_lit", properties=fire_pit_def['properties'].copy())

        chunk_x, chunk_y = fire_x // config.CHUNK_SIZE, fire_y // config.CHUNK_SIZE
        local_x, local_y = fire_x % config.CHUNK_SIZE, fire_y % config.CHUNK_SIZE
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = fire_pit_tile

        # 3. Manually update NPC temperature to freezing
        npc.physical.temperature = 34.0
        self.world._update_npc_temperature(npc)
        self.assertIn("Freezing", npc.physical.status_effects)

        # 4. Advance time to ensure the schedule update runs
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL

        # 5. Run the NPC schedule update
        self.world._update_npc_schedules()

        # 6. Assert that the NPC is now seeking warmth and pathfinding to the fire
        self.assertEqual(npc.schedule.current_task, "seeking_warmth")
        self.assertIsNotNone(npc.schedule.current_path)
        # The path destination should be adjacent to the fire, not on it, because the fire is not passable.
        path_dest = npc.schedule.current_destination_coords
        self.assertIsNotNone(path_dest)
        self.assertTrue(abs(path_dest[0] - fire_x) + abs(path_dest[1] - fire_y) == 1)


class TestClothProductionSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()

        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)

        self.world = World(seed=1) # Use a fixed seed

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_full_cloth_production_cycle(self):
        from entities.animal import Animal
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile
        from data.items import ITEM_DEFINITIONS

        # --- 1. Shearing ---
        # Add a sheep and shears for the player
        sheep = Animal(x=self.world.player.x + 1, y=self.world.player.y, name="Sheep", animal_type="sheep")
        self.world.npcs.append(sheep)

        # Player needs to craft shears first
        self.world.player.add_item("iron_ingot", 2)
        anvil_def = DECORATION_ITEM_DEFINITIONS["anvil"]
        anvil_tile = Tile(char=anvil_def['char'], color=anvil_def['color'], passable=False, name="Anvil", properties=anvil_def['properties'].copy())
        anvil_x, anvil_y = self.world.player.x + 1, self.world.player.y + 1

        chunk_x, chunk_y = anvil_x // config.CHUNK_SIZE, anvil_y // config.CHUNK_SIZE
        local_x, local_y = anvil_x % config.CHUNK_SIZE, anvil_y % config.CHUNK_SIZE
        self.world.get_tile_at(anvil_x, anvil_y)
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = anvil_tile

        self.world.craft_item("shears")
        self.assertTrue(self.world.player.has_item("shears"))

        # Shear the sheep
        self.world.player_attempt_shear(sheep)

        # Check for wool
        self.assertTrue(self.world.player.has_item("raw_wool"))

        # Find wool in inventory to check quantity
        wool_indices = self.world.player.get_item_instance_indices("raw_wool")
        self.assertTrue(wool_indices)
        initial_wool_quantity = self.world.player.economic.inventory[wool_indices[0]].get("quantity", 0)
        self.assertGreater(initial_wool_quantity, 0)

        # Check that sheep can't be shorn again immediately
        self.world.player_attempt_shear(sheep)
        current_wool_quantity = self.world.player.economic.inventory[wool_indices[0]].get("quantity", 0)
        self.assertEqual(initial_wool_quantity, current_wool_quantity)


        # --- 2. Crafting ---
        # Add a loom
        loom_def = DECORATION_ITEM_DEFINITIONS["loom"]
        loom_tile = Tile(char=loom_def['char'], color=loom_def['color'], passable=False, name="Loom", properties=loom_def['properties'].copy())
        loom_x, loom_y = self.world.player.x - 1, self.world.player.y - 1

        chunk_x, chunk_y = loom_x // config.CHUNK_SIZE, loom_y // config.CHUNK_SIZE
        local_x, local_y = loom_x % config.CHUNK_SIZE, loom_y % config.CHUNK_SIZE
        self.world.get_tile_at(loom_x, loom_y) # Ensure chunk generated
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = loom_tile

        # Craft cloth
        self.world.player.add_item("raw_wool", 10) # Ensure enough wool
        self.world.craft_item("cloth")
        self.assertTrue(self.world.player.has_item("cloth"))

        # Craft tunic
        self.world.player.add_item("cloth", 10) # Ensure enough cloth
        self.world.craft_item("cloth_tunic")
        self.assertTrue(self.world.player.has_item("cloth_tunic"))

        # --- 3. Equipping ---
        initial_insulation = self.world.player.physical.clothing_insulation
        self.world.player.equip_armor("cloth_tunic")
        self.assertGreater(self.world.player.physical.clothing_insulation, initial_insulation)

class TestPredatorPreyAI(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()

        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)

        # Use a fixed seed for deterministic world generation
        self.world = World(seed=42)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_predator_hunts_prey_and_prey_flees(self):
        from entities.animal import Animal
        from data.tiles import TILE_DEFINITIONS
        from tile_types import Tile
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Setup: Create predator and prey
        # Move player far away to not interfere with AI
        self.world.player.x = 1000
        self.world.player.y = 1000

        predator = Animal(x=50, y=50, name="Dire Wolf", animal_type="dire_wolf")
        prey = Animal(x=55, y=50, name="Sheep", animal_type="sheep")

        # Set predator to be hungry
        predator.physical.hunger = predator.physical.max_hunger
        prey.physical.hunger = 0

        # HACK: Manually set attributes required by the new AI/movement logic
        # These are not set by default on manually created test animals.
        setattr(predator, 'speed', 2)
        setattr(predator, 'attack_range', 2)
        setattr(prey, 'speed', 1)

        self.world.village_npcs = []
        self.world.npcs = [predator, prey]

        # Ensure the area is clear for movement
        plains_def = TILE_DEFINITIONS["plains"]
        plains_tile = Tile(char=plains_def['char'], color=plains_def['color'], passable=True, name="Plains", properties={})

        # Clear a large area to ensure pathfinding works
        for y_offset in range(-15, 16):
            for x_offset in range(-10, 41):
                clear_x, clear_y = predator.x + x_offset, predator.y + y_offset
                try:
                    self.world.get_tile_at(clear_x, clear_y)
                    chunk_x, chunk_y = clear_x // config.CHUNK_SIZE, clear_y // config.CHUNK_SIZE
                    local_x, local_y = clear_x % config.CHUNK_SIZE, clear_y % config.CHUNK_SIZE
                    self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = plains_tile
                except IndexError:
                    pass # Ignore out-of-bounds coordinates

        # 2. Execution & Assertion (Predator starts hunting)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        self.assertEqual(predator.schedule.current_task, "hunting")
        self.assertTrue(predator.schedule.current_path, "Predator should have a path to the prey.")
        self.assertEqual(predator.task_target_entity_id, prey.id)

        # 3. Execution & Assertion (Prey starts fleeing)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        # Run schedules again so prey can react to the hunting predator
        self.world._update_npc_schedules()

        self.assertEqual(prey.schedule.current_task, "fleeing")
        self.assertTrue(prey.schedule.current_path, "Prey should have a path to flee.")
        # Check that prey's path is moving it away from the predator
        if prey.schedule.current_path and len(prey.schedule.current_path) > 1:
            dist_before = (prey.x - predator.x)**2 + (prey.y - predator.y)**2
            next_pos = prey.schedule.current_path[1]
            dist_after = (next_pos[0] - predator.x)**2 + (next_pos[1] - predator.y)**2
            self.assertGreater(dist_after, dist_before, "Prey should be moving away from the predator.")

        # 4. Execution (Simulate chase and attack)
        initial_prey_hp = prey.combat.hp
        for _ in range(240): # Simulate a few turns
            self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
            self.world._update_npc_schedules()
            self.world._update_npc_movement()
            if prey.physical.is_dead:
                break

        # The hunger reset now happens inside npc_attempt_attack_npc, which is called
        # during the _update_npc_schedules inside the loop. No extra update is needed.
        # A final update would cause the predator's hunger to start increasing again.

        # 5. Assertion (Attack and outcome)
        self.assertLess(prey.combat.hp, initial_prey_hp, "Prey should have taken damage")
        self.assertTrue(prey.physical.is_dead, "Prey should be dead after the chase.")


class TestCombatAndAnimalStateRegression(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC",
            "personality": "neutral",
            "dialogue": ["..."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists",
        })
        self.world = World(seed=7)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_handle_npc_combat_turn_tracks_player_on_nested_combat_state(self):
        npc = engine.NPC(10, 10, name="Bandit")
        npc.combat.is_hostile_to_player = True
        self.world.player.x = 13
        self.world.player.y = 10
        self.world.npc_fov_maps[npc.id] = engine.np.ones((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)

        self.world._handle_npc_combat_turn(npc)

        self.assertEqual(npc.combat.target_entity_id, self.world.player.id)
        self.assertEqual(npc.schedule.current_task, "combat_action_move_to_attack_player")
        self.assertFalse(hasattr(npc, "target_entity_id"))

    def test_npc_attack_player_uses_nested_player_combat_stats(self):
        npc = engine.NPC(self.world.player.x + 1, self.world.player.y, name="Bandit")
        npc.combat.base_attack_name = "club"
        npc.combat.base_attack_damage_dice = "1d1"

        with patch('engine.random.randint', side_effect=[20, 1]):
            self.world.npc_attempt_attack_player(npc, self.world.player)

        self.assertEqual(self.world.player.combat.hp, self.world.player.combat.max_hp - 2)
        self.assertTrue(any("(HP: 28/30)" in message for message in self.world.chat_log))

    def test_animal_defaults_live_in_nested_component_state(self):
        animal = engine.Animal(5, 6, name="Goat", animal_type="goat")

        self.assertEqual(animal.economic.profession, "Creature")
        self.assertEqual(animal.social.personality, "animal")
        self.assertEqual(animal.social.family_ties["description"], "animal")
        self.assertEqual(animal.combat.combat_behavior, "defensive")
        self.assertEqual(animal.physical.hunger, 0)
        self.assertEqual(animal.schedule.current_task, "idle")
        self.assertFalse(hasattr(animal, "personality"))
        self.assertFalse(hasattr(animal, "family_ties"))

    def test_render_biome_details_sets_spawned_animal_nested_combat_stats(self):
        from tile_types import Tile
        plains_def = engine.TILE_DEFINITIONS["plains"]
        chunk = engine.Chunk("plains")
        chunk.tiles = [[Tile(plains_def['char'], plains_def['color'], plains_def['passable'], plains_def['name'], properties={})]]
        self.world.player.x = 1000
        self.world.player.y = 1000

        test_animal_defs = {
            "test_beast": {
                "name": "Test Beast",
                "char": 'b',
                "color": (1, 2, 3),
                "max_hp": 9,
                "behavior": "prowls",
                "hostile": True,
                "base_attack_name": "bite",
                "base_attack_damage_dice": "1d4",
                "combat_behavior": "aggressive",
                "spawn_biomes": ["plains"],
                "spawn_chance": 1.0,
            }
        }

        with patch.object(engine, 'CHUNK_SIZE', 1), \
             patch.dict(engine.ANIMAL_DEFINITIONS, test_animal_defs, clear=True), \
             patch('engine.random.random', side_effect=[1.0, 1.0, 1.0, 1.0, 0.0, 1.0]), \
             patch('engine.random.choice', return_value='male'):
            self.world.npcs.clear()
            self.world._render_biome_details(chunk, 0, 0)

        self.assertEqual(len(self.world.npcs), 1)
        spawned = self.world.npcs[0]
        self.assertEqual(spawned.combat.max_hp, 9)
        self.assertEqual(spawned.combat.hp, 9)
        self.assertEqual(spawned.combat.base_attack_name, "bite")
        self.assertEqual(spawned.combat.base_attack_damage_dice, "1d4")
        self.assertEqual(spawned.combat.combat_behavior, "aggressive")



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



class TestNpcFovIndexRegression(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC",
            "personality": "neutral",
            "dialogue": ["..."],
        })
        self.world = World(seed=13)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_handle_npc_combat_turn_reads_fov_map_as_y_x(self):
        npc = engine.NPC(10, 10, name="Bandit")
        npc.combat.is_hostile_to_player = True
        self.world.player.x = 11
        self.world.player.y = 10
        fov_map = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        fov_map[self.world.player.y, self.world.player.x] = True
        self.world.npc_fov_maps[npc.id] = fov_map

        self.world._handle_npc_combat_turn(npc)

        self.assertEqual(npc.schedule.current_task, "combat_action_attack_player")

    def test_guard_hostility_check_reads_fov_map_as_y_x(self):
        guard = engine.NPC(15, 15, name="Guard")
        guard.economic.profession = "Guard"
        guard.combat.is_hostile_to_player = False
        self.world.village_npcs = [guard]
        self.world.npcs = []
        self.world.player.x = 19
        self.world.player.y = 7
        self.world.player.economic.bounty = 150
        fov_map = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        fov_map[self.world.player.y, self.world.player.x] = True
        self.world.npc_fov_maps[guard.id] = fov_map
        self.world.game_time += config.NPC_SCHEDULE_UPDATE_INTERVAL

        with patch.object(self.world, "_update_npc_fov"):
            self.world._update_npc_schedules()

        self.assertTrue(guard.combat.is_hostile_to_player)
        self.assertTrue(any("moves to arrest you" in message for message in self.world.chat_log))



class TestFearSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()

        mock_npc_data = {
            "name": "Generic Villager", "personality": "neutral", "dialogue": ["..."],
            "wealth_level": "average", "combat_behavior": "defensive", "base_attack_name": "fists"
        }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)

        # Use a fixed seed for any remaining randomness
        self.world = World(seed=1337)
        self.world.current_season_index = 1 # Summer, to ensure neutral temperature

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def _clear_area_and_place_tile(self, x, y, tile_def):
        """Helper to ensure a chunk is generated, clear a tile, and place a new one."""
        from tile_types import Tile
        self.world.get_tile_at(x, y) # Ensure chunk generation
        chunk_x, chunk_y = x // config.CHUNK_SIZE, y // config.CHUNK_SIZE

        # Ensure is_terrain_generated is true if we manually touch tiles
        if not self.world.chunks[chunk_y][chunk_x].is_terrain_generated:
             self.world._generate_chunk_detail(self.world.chunks[chunk_y][chunk_x])

        local_x, local_y = x % config.CHUNK_SIZE, y % config.CHUNK_SIZE
        tile = Tile(char=tile_def['char'], color=tile_def['color'], passable=tile_def['passable'], name=tile_def['name'], properties=tile_def.get('properties', {}).copy())
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = tile
        # Also update the transparency map for FOV calculations
        self.world.transparency_map[y, x] = not tile.blocks_fov

    def test_civilian_flees_from_wolf_pack(self):
        from entities.base import NPC
        from entities.animal import Animal
        from engine import Village, Building
        from data.tiles import TILE_DEFINITIONS
        from config import NPC_SCHEDULE_UPDATE_INTERVAL, CHUNK_SIZE

        # 1. Manual Setup
        center_x, center_y = 50, 50
        village = Village()
        chunk_x, chunk_y = center_x // CHUNK_SIZE, center_y // CHUNK_SIZE
        self.world.chunks[chunk_y][chunk_x].village = village

        # Correctly calculate local coordinates for the building within its chunk
        building_global_x, building_global_y = center_x - 10, center_y - 10
        local_building_x = building_global_x % CHUNK_SIZE
        local_building_y = building_global_y % CHUNK_SIZE

        home_building = Building(local_building_x, local_building_y, 5, 5, building_type="house", category="residential", global_chunk_x_start=chunk_x * CHUNK_SIZE, global_chunk_y_start=chunk_y * CHUNK_SIZE)
        village.add_building(home_building)
        self.world.buildings_by_id[home_building.id] = home_building

        civilian = NPC(x=center_x, y=center_y, name="Civilian")
        civilian.economic.profession = "Farmer"
        civilian.schedule.home_building_id = home_building.id
        self.world.village_npcs.append(civilian)

        wolf1 = Animal(x=civilian.x + 2, y=civilian.y + 2, name="Wolf", animal_type="wolf")
        wolf2 = Animal(x=civilian.x + 3, y=civilian.y + 2, name="Wolf", animal_type="wolf")
        self.world.npcs.extend([wolf1, wolf2])

        plains_def = TILE_DEFINITIONS["plains"]
        for y_offset in range(-15, 16):
            for x_offset in range(-15, 16):
                self._clear_area_and_place_tile(center_x + x_offset, center_y + y_offset, plains_def)

        self.world._update_player_fov()
        # Re-calculating individual NPC FOV is now done in _update_npc_schedules
        # To test this properly, we need to manually call it or run the schedule update
        civilian._force_fov_update = True
        self.world._update_npc_fov(civilian)
        # FOV map is now indexed [y, x]
        self.assertTrue(self.world.npc_fov_maps[civilian.id][wolf1.y, wolf1.x])

        # 2. Execution
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 3. Assertion
        self.assertTrue(civilian.is_frightened)
        self.assertEqual(civilian.schedule.current_task, "fleeing_from_threat")
        self.assertIsNotNone(civilian.schedule.current_path)
        # Assert that the destination is adjacent to the home, not the center itself
        destination = civilian.schedule.current_destination_coords
        self.assertIsNotNone(destination)
        distance_to_home_center = abs(destination[0] - home_building.global_center_x) + abs(destination[1] - home_building.global_center_y)
        self.assertEqual(distance_to_home_center, 1)

    def test_guard_alerts_other_guards(self):
        from entities.base import NPC
        from entities.animal import Animal
        from engine import Village, Building
        from data.tiles import TILE_DEFINITIONS
        from config import NPC_SCHEDULE_UPDATE_INTERVAL, CHUNK_SIZE

        # 1. Manual Setup
        center_x, center_y = 50, 50
        alarm_spot = (center_x, center_y)

        village = Village()
        village.interaction_points["town_square_center"] = alarm_spot
        chunk_x, chunk_y = center_x // CHUNK_SIZE, center_y // CHUNK_SIZE
        self.world.chunks[chunk_y][chunk_x].village = village

        home_building = Building(2, 2, 5, 5, building_type="house", category="residential", global_chunk_x_start=chunk_x * CHUNK_SIZE, global_chunk_y_start=chunk_y * CHUNK_SIZE)
        village.add_building(home_building)
        self.world.buildings_by_id[home_building.id] = home_building

        guard1 = NPC(x=alarm_spot[0] - 5, y=alarm_spot[1], name="Guard")
        guard1.economic.profession = "Guard"
        guard1.schedule.home_building_id = home_building.id

        guard2 = NPC(x=alarm_spot[0] - 2, y=alarm_spot[1] - 2, name="Alerted Guard")
        guard2.economic.profession = "Guard"

        wolf1 = Animal(x=guard1.x + 2, y=guard1.y, name="Wolf", animal_type="wolf")
        wolf2 = Animal(x=guard1.x + 3, y=guard1.y, name="Wolf", animal_type="wolf")

        self.world.village_npcs.extend([guard1, guard2])
        self.world.npcs.extend([wolf1, wolf2])

        plains_def = TILE_DEFINITIONS["plains"]
        for y_offset in range(-15, 16):
            for x_offset in range(-15, 16):
                self._clear_area_and_place_tile(center_x + x_offset, center_y + y_offset, plains_def)

        well_def = TILE_DEFINITIONS["well"]
        self._clear_area_and_place_tile(alarm_spot[0], alarm_spot[1], well_def)
        self.assertFalse(self.world.get_tile_at(alarm_spot[0], alarm_spot[1]).passable)

        self.world._update_player_fov()
        self.world._update_npc_fov(guard1)
        # FOV map is now indexed [y, x]
        self.assertTrue(self.world.npc_fov_maps[guard1.id][wolf1.y, wolf1.x])

        # 2. Execution
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 3. Assertion (Guard 1 starts alerting)
        self.assertTrue(guard1.is_frightened)
        self.assertEqual(guard1.schedule.current_task, "alerting_guards")
        self.assertIsNotNone(guard1.schedule.current_path, "Guard1 should have a path to the alarm spot")

        destination = guard1.schedule.current_destination_coords
        self.assertIsNotNone(destination)
        distance_to_alarm = abs(destination[0] - alarm_spot[0]) + abs(destination[1] - alarm_spot[1])
        self.assertEqual(distance_to_alarm, 1, "Guard should be pathing to a tile adjacent to the alarm spot.")

        self.assertFalse(guard2.combat.is_hostile_to_player, "Guard 2 should not be alerted yet.")

        # 4. Manually move guard1 to their destination
        guard1.x, guard1.y = destination
        guard1.schedule.current_path = []

        # 5. Execution (Second update)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 6. Assertion (Guards become hostile)
        self.assertTrue(guard1.combat.is_hostile_to_player, "Alerting guard should become hostile.")
        self.assertTrue(guard2.combat.is_hostile_to_player, "Nearby guard should become hostile after alarm.")

    def test_npc_calms_down_when_threat_is_gone(self):
        from entities.base import NPC
        from entities.animal import Animal
        from data.tiles import TILE_DEFINITIONS
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Manual Setup
        # Clear existing NPCs to prevent interference from procedurally generated animals
        self.world.npcs.clear()

        center_x, center_y = 50, 50
        civilian = NPC(x=center_x, y=center_y, name="Civilian")
        civilian.economic.profession = "Farmer"
        self.world.village_npcs.append(civilian)

        wolf1 = Animal(x=center_x + 2, y=center_y, name="Wolf", animal_type="wolf")
        wolf2 = Animal(x=center_x + 3, y=center_y, name="Wolf", animal_type="wolf")
        self.world.npcs.extend([wolf1, wolf2])

        plains_def = TILE_DEFINITIONS["plains"]
        for y_offset in range(-5, 6):
            for x_offset in range(-5, 6):
                self._clear_area_and_place_tile(center_x + x_offset, center_y + y_offset, plains_def)

        self.world._update_player_fov()
        civilian._force_fov_update = True
        self.world._update_npc_fov(civilian)
        self.assertTrue(self.world.npc_fov_maps[civilian.id][wolf1.y, wolf1.x])


        # 2. Execution (Initial fear)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()
        self.assertTrue(civilian.is_frightened)
        self.assertNotEqual(civilian.schedule.current_task, "idle")

        # 3. Remove the threat
        self.world.npcs.remove(wolf1)
        self.world.npcs.remove(wolf2)

        # Update FOV so NPC no longer sees them
        self.world._update_player_fov()
        self.world._update_npc_fov(civilian)
        # self.assertFalse(self.world.npc_fov_maps[civilian.id][wolf1.x, wolf1.y]) # This assertion is incorrect

        # 4. Execution (Calm down)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 5. Assertion
        self.assertFalse(civilian.is_frightened)
        self.assertEqual(civilian.schedule.current_task, "idle")


class TestPlayerFarming(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)
        self.world = World(seed=123) # Use a consistent seed for placement

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_player_can_till_soil(self):
        from data.tiles import TILE_DEFINITIONS
        player = self.world.player
        # Give player a hoe
        player.add_item("stone_hoe", 1)
        self.assertTrue(player.has_item("stone_hoe"))
        hoe_instance = player.get_item_by_index(player.get_item_instance_indices("stone_hoe")[0])
        initial_durability = hoe_instance['durability']

        # Find a plains tile in front of the player
        target_x, target_y = player.x + 1, player.y
        self.world.get_tile_at(target_x, target_y) # Ensure chunk is generated
        chunk_x, chunk_y = target_x // config.CHUNK_SIZE, target_y // config.CHUNK_SIZE
        local_x, local_y = target_x % config.CHUNK_SIZE, target_y % config.CHUNK_SIZE
        plains_def = TILE_DEFINITIONS["plains"]
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = engine.Tile(plains_def['char'], plains_def['color'], plains_def['passable'], plains_def['name'])

        # Perform the action
        self.world.player_attempt_till_soil(target_x, target_y)

        # Assert tile has changed
        tilled_tile = self.world.get_tile_at(target_x, target_y)
        self.assertEqual(tilled_tile.name, "Tilled Soil")

        # Assert hoe durability has decreased
        self.assertLess(hoe_instance['durability'], initial_durability)

    def test_player_can_plant_seeds(self):
        from data.tiles import TILE_DEFINITIONS
        player = self.world.player
        # Give player seeds
        player.add_item("wheat_seeds", 1)
        self.assertTrue(player.has_item("wheat_seeds"))

        # Create a tilled soil tile
        target_x, target_y = player.x + 1, player.y
        self.world.get_tile_at(target_x, target_y) # Ensure chunk is generated
        chunk_x, chunk_y = target_x // config.CHUNK_SIZE, target_y // config.CHUNK_SIZE
        local_x, local_y = target_x % config.CHUNK_SIZE, target_y % config.CHUNK_SIZE
        tilled_def = TILE_DEFINITIONS["tilled_soil"]
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = engine.Tile(tilled_def['char'], tilled_def['color'], tilled_def['passable'], tilled_def['name'])

        # Perform the action
        self.world.player_attempt_plant_seeds(target_x, target_y)

        # Assert tile has changed
        growing_tile = self.world.get_tile_at(target_x, target_y)
        self.assertEqual(growing_tile.name, "Growing Wheat")

        # Assert player has used one seed
        self.assertFalse(player.has_item("wheat_seeds"))

    def test_player_can_harvest_crop(self):
        from data.tiles import TILE_DEFINITIONS
        player = self.world.player

        # Create a mature wheat tile
        target_x, target_y = player.x + 1, player.y
        self.world.get_tile_at(target_x, target_y)
        chunk_x, chunk_y = target_x // config.CHUNK_SIZE, target_y // config.CHUNK_SIZE
        local_x, local_y = target_x % config.CHUNK_SIZE, target_y % config.CHUNK_SIZE
        wheat_def = TILE_DEFINITIONS["wheat_plant"]
        # Need to use engine.Tile and a copy of properties
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = engine.Tile(wheat_def['char'], wheat_def['color'], wheat_def['passable'], wheat_def['name'], properties=wheat_def['properties'].copy())

        # Perform the action
        with patch('random.random', return_value=0.1): # Ensure successful harvest
            self.world.player_attempt_harvest(target_x, target_y)

        # Assert tile has reverted
        reverted_tile = self.world.get_tile_at(target_x, target_y)
        self.assertEqual(reverted_tile.name, "Tilled Soil")

        # Assert player received wheat
        self.assertTrue(player.has_item("wheat"))


class TestQuestSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        # Default mock for NPC generation
        self.mock_npc_data = {
            "name": "Quest Giver", "personality": "desperate", "dialogue": ["Help me!"],
            "wealth_level": "poor", "combat_behavior": "cowardly", "base_attack_name": "pleading"
        }
        self.mock_call_llm.return_value = json.dumps(self.mock_npc_data)
        self.world = World(seed=101)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_dynamic_fetch_quest_lifecycle(self):
        from entities.base import NPC
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Setup: Create a needy NPC
        npc = NPC(x=self.world.player.x + 2, y=self.world.player.y, name="Hungry Hal", player_id=self.world.player.id)
        npc.physical.hunger = 95
        npc.knowledge.known_locations.clear()
        self.world.village_npcs = [npc]
        self.world.npcs = []
        initial_relationship = npc.social.relationships.get(self.world.player.id, 50)

        # 2. Quest Generation
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        with patch('random.random', return_value=0.05): # Ensure quest generation check passes
            self.world._update_npc_schedules()

        self.assertTrue(hasattr(npc, 'active_quest') and npc.active_quest is not None, "NPC should have generated a quest.")
        self.assertEqual(npc.active_quest.type, "fetch")

        quest_item = npc.active_quest.item_key
        quest_item_count = npc.active_quest.required_count
        quest_id = npc.active_quest.id

        # 3. Quest Offer & Acceptance
        # Mock dialogue responses
        def dialogue_side_effect(prompt):
            if "conversation_greeting" in prompt:
                return f"Oh, hello! I'm so hungry..."
            elif "conversation_continue" in prompt:
                # Mock a response for when player accepts
                return json.dumps({"response": "Thank you, thank you! Please hurry!", "goal": "continue_conversation"})
            return json.dumps(self.mock_npc_data)
        self.mock_call_llm.side_effect = dialogue_side_effect

        self.world.start_npc_dialogue(npc)
        # The offer text is hardcoded, so it should be in the history
        self.assertTrue(any("desperately need" in text for _, text in self.world.chat_ui_history))

        self.world.continue_npc_dialogue(npc, "I will accept your quest")

        # 4. Quest Tracking
        self.assertIn(quest_id, self.world.player.knowledge.active_quests)
        self.assertIsNone(npc.active_quest, "NPC's active quest should be cleared after player accepts it.")
        active_quest_data = self.world.player.knowledge.active_quests[quest_id]
        self.assertEqual(active_quest_data["item_to_fetch_key"], quest_item)

        # 5. Quest Completion
        initial_money = self.world.player.economic.money
        self.world.player.add_item(quest_item, quest_item_count)
        self.assertTrue(self.world.player.has_item(quest_item, quest_item_count))

        # Re-initiate dialogue to turn in the quest
        self.world.start_npc_dialogue(npc)
        self.world.continue_npc_dialogue(npc, "I have what you need, complete quest")

        # 6. Verification
        self.assertFalse(self.world.player.has_item(quest_item, quest_item_count), "Quest items should be removed from player inventory.")
        self.assertGreater(self.world.player.economic.money, initial_money, "Player should have received money.")
        self.assertEqual(npc.physical.hunger, 0, "NPC's hunger should be satisfied.")
        self.assertGreater(npc.social.relationships.get(self.world.player.id, 50), initial_relationship, "NPC relationship with player should improve.")
        self.assertNotIn(quest_id, self.world.player.knowledge.active_quests, "Quest should be removed from active quests.")
        self.assertIn(quest_id, self.world.player.knowledge.completed_quests, "Quest should be in completed quests.")

    def test_dynamic_thirst_quest_requests_water_flask(self):
        from entities.base import NPC
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        npc = NPC(x=self.world.player.x + 2, y=self.world.player.y, name="Thirsty Theo", player_id=self.world.player.id)
        npc.physical.thirst = 95
        npc.physical.hunger = 0
        npc.knowledge.known_locations.clear()
        self.world.village_npcs = [npc]
        self.world.npcs = []

        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        with patch('random.random', return_value=0.05):
            self.world._update_npc_schedules()

        self.assertTrue(hasattr(npc, 'active_quest') and npc.active_quest is not None)
        self.assertEqual(npc.knowledge.help_needed, "water")
        self.assertEqual(npc.active_quest.item_key, "water_flask")
        self.assertEqual(npc.active_quest.required_count, 1)
        self.assertEqual(npc.active_quest.type, "fetch")

    def test_static_fetch_quest_completion_and_rewards(self):
        from entities.base import NPC
        from data.quests import QUEST_DEFINITIONS

        # 1. Setup
        quest_id = "fetch_herbs_01"
        quest_def = QUEST_DEFINITIONS[quest_id]
        npc = NPC(x=self.world.player.x + 1, y=self.world.player.y, name="Healer", player_id=self.world.player.id)
        npc.economic.profession = "Healer" # Matches quest giver role
        self.world.village_npcs.append(npc)

        # Manually add the quest to the player's active quests
        self.world.player.knowledge.active_quests[quest_id] = {
            "title": quest_def["title"], "description": quest_def["description"], "type": "fetch",
            "quest_giver_id": npc.id, "item_to_fetch_key": quest_def["item_to_fetch_key"],
            "item_fetch_count": quest_def["item_fetch_count"], "progress": 0,
            "quest_giver_id_or_role": "Healer"
        }

        # Give player the required items
        self.world.player.add_item(quest_def["item_to_fetch_key"], quest_def["item_fetch_count"])
        initial_fame = self.world.player.social.fame
        initial_money = self.world.player.economic.money

        # 2. Execution
        self.world.complete_quest(quest_id, npc)

        # 3. Verification
        # Check rewards
        self.assertGreater(self.world.player.social.fame, initial_fame, "Fame should be awarded for static quests.")
        expected_money = initial_money + quest_def["reward_money"]
        self.assertEqual(self.world.player.economic.money, expected_money, "Money reward should match quest definition.")
        for item_key, quantity in quest_def["reward_items"].items():
            self.assertTrue(self.world.player.has_item(item_key, quantity), f"Player should have received {quantity}x {item_key}.")

        # Check quest state
        self.assertNotIn(quest_id, self.world.player.knowledge.active_quests)
        self.assertIn(quest_id, self.world.player.knowledge.completed_quests)

        # Check that quest items were consumed
        self.assertFalse(self.world.player.has_item(quest_def["item_to_fetch_key"]), "Quest items should have been consumed.")

class TestLockpickChestLooting(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC",
            "personality": "neutral",
            "dialogue": ["..."],
        })
        self.world = World(seed=21)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_pick_lock_loots_chest_inventory_into_player_inventory(self):
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile

        target_x, target_y = self.world.player.x + 1, self.world.player.y
        self.world.get_tile_at(target_x, target_y)
        chunk_x, chunk_y = target_x // config.CHUNK_SIZE, target_y // config.CHUNK_SIZE
        local_x, local_y = target_x % config.CHUNK_SIZE, target_y % config.CHUNK_SIZE
        chest_def = DECORATION_ITEM_DEFINITIONS["chest_wooden"]
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
            chest_def["char"],
            chest_def["color"],
            chest_def["passable"],
            chest_def["name"],
            properties=chest_def["properties"].copy(),
        )

        building = engine.Building(local_x, local_y, 1, 1, building_type="house", category="residential", global_chunk_x_start=chunk_x * config.CHUNK_SIZE, global_chunk_y_start=chunk_y * config.CHUNK_SIZE)
        building.building_inventory = {"apple": 2, "money": 7}
        self.world.buildings_by_id = {building.id: building}

        starting_money = self.world.player.economic.money
        self.world.player.add_item("lockpick", 1)
        self.mock_call_llm.return_value = json.dumps({
            "success": True,
            "narrative_feedback": "Click.",
            "lockpick_broken": False,
        })

        handled = self.world.player_attempt_pick_lock(target_x, target_y)

        self.assertTrue(handled)
        self.assertTrue(self.world.player.has_item("apple", 2))
        self.assertEqual(self.world.player.economic.money, starting_money + 7)
        self.assertEqual(building.building_inventory, {})
        self.assertFalse(self.world.get_tile_at(target_x, target_y).properties["is_locked"])
        self.assertTrue(any("You loot the Wooden Chest" in message for message in self.world.chat_log))



class TestSaveLoadSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)
        self.world = World(seed=999)
        self.test_save_file = "test_save.sav"

    def tearDown(self):
        self.mock_ollama_patcher.stop()
        import os
        if os.path.exists(f"saves/{self.test_save_file}"):
            os.remove(f"saves/{self.test_save_file}")
        if os.path.exists("saves") and not os.listdir("saves"):
            os.rmdir("saves")

    def test_save_and_load(self):
        from save_manager import save_game, load_game

        # Modify world state
        self.world.player.economic.money = 9999
        self.world.game_time = 12345

        # Save
        success = save_game(self.world, self.test_save_file)
        self.assertTrue(success, "Game should save successfully.")

        # Load
        loaded_world = load_game(self.test_save_file)
        self.assertIsNotNone(loaded_world, "Game should load successfully.")

        # Verify state
        self.assertEqual(loaded_world.player.economic.money, 9999)
        self.assertEqual(loaded_world.game_time, 12345)
        self.assertEqual(len(loaded_world.chunks), len(self.world.chunks))

    def test_save_and_load_ignores_unpicklable_generator_noise(self):
        from save_manager import save_game, load_game

        self.world.generator.noise = lambda: None

        success = save_game(self.world, self.test_save_file)
        self.assertTrue(success, "Game should save successfully even with an unpicklable generator noise object.")

        loaded_world = load_game(self.test_save_file)
        self.assertIsNotNone(loaded_world, "Game should load successfully.")
        self.assertIsNotNone(loaded_world.generator.noise)

if __name__ == '__main__':
    unittest.main()
