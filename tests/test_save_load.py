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
