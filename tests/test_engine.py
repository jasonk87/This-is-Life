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


class TestChunkSleepWakeAndAbstractSimulation(unittest.TestCase):
    def make_minimal_world(self):
        world = object.__new__(engine.World)
        world.player = SimpleNamespace(id=1, x=0, y=0)
        world.npcs = []
        world.village_npcs = []
        world.entity_positions = {(0, 0): 1}
        world.entity_positions_dirty = False
        world.entity_chunks_dirty = False
        world.entities_by_chunk = {(0, 0): {1}}
        world.npc_fov_maps = {}
        world.buildings_by_id = {}
        world.chunk_width = 8
        world.chunk_height = 8
        world.chunk_manager = engine.ChunkManager(config.CHUNK_SIZE, world.chunk_width, world.chunk_height)
        world.chunk_manager.update_for_player(world.player.x, world.player.y, force=True)
        world.last_abstract_simulation_hour = -1
        world.ensure_player_surroundings_generated = MagicMock()
        world.get_tile_at = lambda x, y: SimpleNamespace(passable=True, name="Plains")
        return world

    def test_sleep_and_wake_entity_preserve_state_and_strip_heavy_runtime_bits(self):
        world = self.make_minimal_world()
        npc = engine.NPC(config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4, name="Sleeper")
        world.village_npcs = [npc]
        world.entity_positions[(npc.x, npc.y)] = npc.id
        world.entities_by_chunk[(4, 4)] = {npc.id}
        world.npc_fov_maps[npc.id] = "cached"
        npc.economic.money = 37
        npc.economic.npc_inventory.add_item_reference(engine.ItemReference("axe_stone", quality="Fine"))
        inventory_ref = npc.economic.npc_inventory.get_item_reference("axe_stone")
        npc.knowledge.known_locations["work"] = (npc.x, npc.y)
        npc.social.relationships[world.player.id] = 68
        original_brain = npc.ai_brain

        slept = engine.World.sleep_entity(world, npc)

        self.assertTrue(slept)
        self.assertTrue(npc.is_sleeping)
        self.assertTrue(npc.render_disabled)
        self.assertIsNone(npc.ai_brain)
        self.assertEqual((npc.macro_x, npc.macro_y), (config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4))
        self.assertNotIn((npc.x, npc.y), world.entity_positions)
        self.assertNotIn(npc.id, world.npc_fov_maps)
        self.assertEqual(npc.economic.money, 37)
        self.assertEqual(npc.social.relationships[world.player.id], 68)
        self.assertEqual(npc.knowledge.known_locations["work"], (config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4))
        self.assertIs(npc.economic.npc_inventory.get_item_reference("axe_stone"), inventory_ref)

        woke = engine.World.wake_entity(world, npc)

        self.assertTrue(woke)
        self.assertFalse(npc.is_sleeping)
        self.assertFalse(npc.render_disabled)
        self.assertIs(npc.ai_brain, original_brain)
        self.assertIn((npc.x, npc.y), world.entity_positions)
        self.assertIs(npc.economic.npc_inventory.get_item_reference("axe_stone"), inventory_ref)

    def test_refresh_chunk_activity_sleeps_and_wakes_entities_as_player_crosses_boundary(self):
        world = self.make_minimal_world()
        nearby_npc = engine.NPC(2, 2, name="Nearby")
        far_npc = engine.NPC(config.CHUNK_SIZE * 4, config.CHUNK_SIZE * 4, name="Far")
        world.village_npcs = [nearby_npc, far_npc]
        world.entity_positions[(nearby_npc.x, nearby_npc.y)] = nearby_npc.id
        world.entity_positions[(far_npc.x, far_npc.y)] = far_npc.id
        world.entities_by_chunk[(0, 0)].add(nearby_npc.id)
        world.entities_by_chunk[(4, 4)] = {far_npc.id}

        engine.World._refresh_chunk_activity(world, force=True)

        self.assertFalse(nearby_npc.is_sleeping)
        self.assertTrue(far_npc.is_sleeping)

        world.player.x = config.CHUNK_SIZE * 4
        world.player.y = config.CHUNK_SIZE * 4
        engine.World._refresh_chunk_activity(world, force=True)

        self.assertTrue(nearby_npc.is_sleeping)
        self.assertFalse(far_npc.is_sleeping)
        self.assertIn((far_npc.x, far_npc.y), world.entity_positions)

    def test_update_npc_movement_skips_sleeping_entities(self):
        world = self.make_minimal_world()
        sleeping_npc = SimpleNamespace(
            id=2,
            x=3,
            y=4,
            macro_x=3,
            macro_y=4,
            is_sleeping=True,
            speed=1,
            task_target_entity_id=None,
            physical=SimpleNamespace(is_dead=False),
            schedule=SimpleNamespace(
                current_task="wandering",
                current_path=[(3, 4), (4, 4)],
                current_destination_coords=(4, 4),
                path_blocked_turns=0,
                last_blocked_position=None,
            ),
            economic=SimpleNamespace(profession="Villager"),
        )
        world.village_npcs = [sleeping_npc]
        world.entity_positions[(sleeping_npc.x, sleeping_npc.y)] = sleeping_npc.id
        world.entities_by_chunk[(0, 0)].add(sleeping_npc.id)
        world.add_message_to_chat_log = MagicMock()
        world._is_predator = lambda entity: False

        engine.World._update_npc_movement(world)

        self.assertEqual((sleeping_npc.x, sleeping_npc.y), (3, 4))
        self.assertEqual(sleeping_npc.schedule.current_path, [(3, 4), (4, 4)])

    def test_process_abstract_simulation_updates_sleeping_workers_and_inactive_buildings_hourly(self):
        world = self.make_minimal_world()
        building = engine.Building(
            0,
            0,
            5,
            5,
            building_type="farm",
            category="agricultural_workplace",
            global_chunk_x_start=config.CHUNK_SIZE * 3,
            global_chunk_y_start=config.CHUNK_SIZE * 3,
        )
        building.building_inventory["money"] = 120
        world.buildings_by_id[building.id] = building

        npc = engine.NPC(building.global_center_x, building.global_center_y, name="Farm Sleeper")
        npc.economic.profession = "Farmer"
        npc.economic.daily_wage = 24
        npc.schedule.work_building_id = building.id
        npc.is_sleeping = True
        npc.ai_brain = None
        world.village_npcs = [npc]

        hourly_tick = max(1, config.DAY_LENGTH_TICKS // 24)
        world.game_time = int(config.DAY_LENGTH_TICKS * config.WORK_START_TIME_RATIO) + hourly_tick

        engine.World.process_abstract_simulation(world)

        self.assertGreater(npc.economic.money, 0)
        self.assertGreater(npc.physical.hunger, 0)
        self.assertLess(building.building_inventory.get("money", 0), 120)
        self.assertGreater(building.building_inventory.get("wheat", 0), 0)
