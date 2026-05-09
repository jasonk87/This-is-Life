import os
import pickle
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
from save_manager import SAVE_FORMAT_VERSION, load_game, save_game
from simulation.history import DeathRecord
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
        if os.path.exists(f"saves/{self.test_save_file}"):
            os.remove(f"saves/{self.test_save_file}")
        if os.path.exists("saves") and not os.listdir("saves"):
            os.rmdir("saves")

    def test_save_and_load(self):
        # Modify world state
        self.world.player.economic.money = 9999
        self.world.game_time = 12345

        # Save
        success = save_game(self.world, self.test_save_file)
        self.assertTrue(success, "Game should save successfully.")

        with open(f"saves/{self.test_save_file}", "rb") as f:
            save_data = pickle.load(f)
        self.assertEqual(save_data["version"], SAVE_FORMAT_VERSION)
        self.assertIsNotNone(save_data["world"])

        # Load
        loaded_world = load_game(self.test_save_file)
        self.assertIsNotNone(loaded_world, "Game should load successfully.")

        # Verify state
        self.assertEqual(loaded_world.player.economic.money, 9999)
        self.assertEqual(loaded_world.game_time, 12345)
        self.assertEqual(len(loaded_world.chunks), len(self.world.chunks))

    def test_save_and_load_ignores_unpicklable_generator_noise(self):
        self.world.generator.noise = lambda: None

        success = save_game(self.world, self.test_save_file)
        self.assertTrue(success, "Game should save successfully even with an unpicklable generator noise object.")

        loaded_world = load_game(self.test_save_file)
        self.assertIsNotNone(loaded_world, "Game should load successfully.")
        self.assertIsNotNone(loaded_world.generator.noise)

    def test_load_rejects_unsupported_save_version(self):
        os.makedirs("saves", exist_ok=True)
        with open(f"saves/{self.test_save_file}", "wb") as f:
            pickle.dump({"version": SAVE_FORMAT_VERSION + 1, "world": self.world}, f)

        loaded_world = load_game(self.test_save_file)

        self.assertIsNone(loaded_world)

    def test_load_rejects_unversioned_save_payload(self):
        os.makedirs("saves", exist_ok=True)
        with open(f"saves/{self.test_save_file}", "wb") as f:
            pickle.dump(self.world, f)

        loaded_world = load_game(self.test_save_file)

        self.assertIsNone(loaded_world)

    def test_save_and_load_preserves_typed_history_records(self):
        death = self.world.history.record_death(
            deceased_id=101,
            killer_id=202,
            description="A villager died.",
            game_time=self.world.game_time,
            location=(4, 5),
            cause_of_death="test",
            settlement_id="settlement_test",
            region_id="region_test",
        )

        success = save_game(self.world, self.test_save_file)
        self.assertTrue(success, "Game should save successfully with typed history records.")

        loaded_world = load_game(self.test_save_file)

        self.assertIsNotNone(loaded_world)
        loaded_deaths = loaded_world.history.get_records_by_type(DeathRecord)
        self.assertEqual(len(loaded_deaths), 1)
        self.assertEqual(loaded_deaths[0].record_id, death.record_id)
        self.assertEqual(loaded_deaths[0].cause_of_death, "test")
        self.assertEqual(loaded_world.history.get_records_by_entity(202), loaded_deaths)
        self.assertEqual(loaded_world.history.get_records_by_settlement("settlement_test"), loaded_deaths)
        self.assertEqual(loaded_world.history.get_records_by_region("region_test"), loaded_deaths)
