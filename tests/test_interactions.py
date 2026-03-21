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

        # Ensure there are no random hostile creatures spawned near the NPC that would cause them to flee instead
        self.world.npcs = [n for n in self.world.npcs if n.id == npc.id]

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
