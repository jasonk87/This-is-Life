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
