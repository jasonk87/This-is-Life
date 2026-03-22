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
        self.assertTrue(any("(HP: 33/35)" in message for message in self.world.chat_log))

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

        self.world.chat_log = []
        self.world.npcs = []
        with patch.object(self.world, "_update_npc_fov"):
            with patch.object(self.world, "add_message_to_chat_log") as mock_add_msg:
                self.world._update_npc_schedules()

        self.assertTrue(guard.combat.is_hostile_to_player)

        arrest_call_found = False
        for call in mock_add_msg.call_args_list:
            if "moves to arrest you" in call.args[0]:
                arrest_call_found = True
                break
        self.assertTrue(arrest_call_found, "Expected 'moves to arrest you' message to be logged.")


class TestCombatMemory(unittest.TestCase):
    def setUp(self):
        self.world = engine.World(seed=13)

    def test_deterministic_combat_memory_logging(self):
        attacker = engine.NPC(x=10, y=10, name="Attacker")
        attacker.economic.profession = "Guard"
        defender = engine.NPC(x=11, y=10, name="Defender")
        defender.combat.hp = 30
        defender.combat.max_hp = 30

        witness_a = engine.NPC(x=12, y=10, name="Witness A") # in FOV
        witness_b = engine.NPC(x=50, y=50, name="Witness B") # out of FOV

        self.world.npcs = [attacker, defender, witness_a, witness_b]
        self.world.village_npcs = []

        import config
        fov_a = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        fov_a[10, 11] = True # Can see defender
        self.world.npc_fov_maps[witness_a.id] = fov_a

        fov_b = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        self.world.npc_fov_maps[witness_b.id] = fov_b

        # Manually invoke broadcast
        defender.take_damage = MagicMock(return_value=False)
        defender.combat.hp = 25 # Assume 5 damage
        defender.combat.last_hit_part = "left_leg"
        defender.physical.status_effects = ["broken_leg"]

        self.world._broadcast_combat_memory(attacker, defender, "sword", 5, {"broken_leg"})

        memory_str = "Witnessed Attacker strike Defender's left_leg with sword for 5 damage. ...causing a broken_leg."

        self.assertIn(memory_str, witness_a.knowledge.long_term_memory)
        self.assertNotIn(memory_str, witness_b.knowledge.long_term_memory)
        self.assertIn(memory_str, attacker.knowledge.long_term_memory)
        self.assertIn(memory_str, defender.knowledge.long_term_memory)
