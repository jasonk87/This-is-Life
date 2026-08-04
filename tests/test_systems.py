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
from simulation.systems import survival
from tcod_compat import tcod
import tile_types

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

        survival.update_entity_temperature(self.world, self.world.player, update_world_ambient=True)

        from config import SEASON_TEMPERATURE_MODIFIERS, BIOME_TEMPERATURE_MODIFIERS, TIME_OF_DAY_TEMPERATURE_MODIFIERS
        expected_temp = (SEASON_TEMPERATURE_MODIFIERS["Winter"] +
                         BIOME_TEMPERATURE_MODIFIERS["snow"] +
                         TIME_OF_DAY_TEMPERATURE_MODIFIERS["DEEP_NIGHT"])
        self.assertAlmostEqual(self.world.ambient_temperature, expected_temp)

    def test_heat_source_effect(self):
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile

        # First, get temperature without any heat source
        survival.update_entity_temperature(self.world, self.world.player, update_world_ambient=True)
        initial_temp = self.world.ambient_temperature

        fire_pit_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_pit_tile = Tile(char=fire_pit_def['char'], color=fire_pit_def['color'], passable=False, name="fire_pit_lit", properties=fire_pit_def['properties'])

        # Place a fire pit near the player
        fire_x, fire_y = self.world.player.x + 1, self.world.player.y
        self.world.chunks[fire_y // config.CHUNK_SIZE][fire_x // config.CHUNK_SIZE].tiles[fire_y % config.CHUNK_SIZE][fire_x % config.CHUNK_SIZE] = fire_pit_tile

        # Rerun temperature update to capture heat source effect
        survival.update_entity_temperature(self.world, self.world.player, update_world_ambient=True)
        temp_with_fire = self.world.ambient_temperature

        self.assertGreater(temp_with_fire, initial_temp)

    def test_player_gets_wet_in_rain(self):
        self.world.weather = "rain"
        self.world.player.physical.is_sheltered = False
        survival.update_player_wetness(self.world)
        self.assertTrue(self.world.player.physical.is_wet)
        self.assertGreater(self.world.player.physical.wetness_timer, 0)

    def test_clothing_insulation_effect(self):
        player = self.world.player
        player.physical.temperature = 30 # Set a cold body temp

        survival.update_entity_temperature(self.world, self.world.player, update_world_ambient=True)
        temp_change_without_cloak = player.physical.temperature - 30

        player.equip_armor("fur_cloak")
        player.physical.temperature = 30 # Reset temp

        survival.update_entity_temperature(self.world, self.world.player, update_world_ambient=True)
        temp_change_with_cloak = player.physical.temperature - 30

        self.assertGreater(temp_change_with_cloak, temp_change_without_cloak)

    def test_freezing_effect(self):
        player = self.world.player
        initial_hp = player.combat.hp
        player.physical.temperature = 34.0 # Below freezing threshold

        # Update temperature to apply status effect
        survival.update_entity_temperature(self.world, self.world.player, update_world_ambient=True)
        self.assertIn("Freezing", player.physical.status_effects)

        from config import DAY_LENGTH_TICKS
        ticks_for_damage = DAY_LENGTH_TICKS // 25

        for i in range(ticks_for_damage + 1):
            self.world.game_time += 1
            survival.apply_temperature_effects(self.world, player, is_player=True)

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

        # Ensure sheep is sheering ready
        sheep.physical.hunger = 0 # Not hungry
        sheep.last_shorn_time = -100000 * config.DAY_LENGTH_TICKS

        # Shear the sheep
        self.world.player_attempt_shear(sheep)

        # Check for wool
        self.assertTrue(self.world.player.has_item("raw_wool"), "Player should have raw wool after shearing sheep.")

        # Find wool in inventory to check quantity
        initial_wool_quantity = self.world.player.economic.inventory.get("raw_wool", 0)
        self.assertGreater(initial_wool_quantity, 0)

        # Check that sheep can't be shorn again immediately
        self.world.player_attempt_shear(sheep)
        current_wool_quantity = self.world.player.economic.inventory.get("raw_wool", 0)
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
        hoe_instance = player.get_item_reference("stone_hoe")
        initial_durability = hoe_instance.current_durability

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
        self.assertLess(hoe_instance.current_durability, initial_durability)

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

    def test_static_fetch_quest_completion_grants_questing_experience(self):
        from entities.base import NPC
        from data.quests import QUEST_DEFINITIONS

        quest_id = "fetch_herbs_01"
        quest_def = QUEST_DEFINITIONS[quest_id]
        npc = NPC(x=self.world.player.x + 1, y=self.world.player.y, name="Healer", player_id=self.world.player.id)
        npc.economic.profession = "Healer"
        self.world.village_npcs.append(npc)
        self.world.player.knowledge.active_quests[quest_id] = {
            "title": quest_def["title"], "description": quest_def["description"], "type": "fetch",
            "quest_giver_id": npc.id, "item_to_fetch_key": quest_def["item_to_fetch_key"],
            "item_fetch_count": quest_def["item_fetch_count"], "progress": 0,
            "quest_giver_id_or_role": "Healer"
        }
        self.world.player.add_item(quest_def["item_to_fetch_key"], quest_def["item_fetch_count"])
        starting_xp = self.world.player.skills.experience.get("questing", 0)

        self.world.complete_quest(quest_id, npc)

        self.assertGreater(self.world.player.skills.experience["questing"], starting_xp)


class TestSkillProgressionHooks(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC", "personality": "test", "dialogue": ["Hi"],
            "wealth_level": "average", "combat_behavior": "defensive", "base_attack_name": "fists"
        })
        self.world = World(seed=17)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_player_crafting_grants_crafting_experience(self):
        self.world.player.add_item("stone_chunk", 2)
        self.world.player.add_item("raw_log", 2)
        starting_xp = self.world.player.skills.experience.get("crafting", 0)

        self.world.craft_item("stone_hoe")

        self.assertTrue(self.world.player.has_item("stone_hoe"))
        self.assertGreater(self.world.player.skills.experience["crafting"], starting_xp)

    def test_player_harvest_grants_farming_experience(self):
        from data.tiles import TILE_DEFINITIONS

        player = self.world.player
        target_x, target_y = player.x + 1, player.y
        chunk_x, chunk_y = target_x // config.CHUNK_SIZE, target_y // config.CHUNK_SIZE
        local_x, local_y = target_x % config.CHUNK_SIZE, target_y % config.CHUNK_SIZE
        wheat_def = TILE_DEFINITIONS["wheat_plant"]
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = engine.Tile(
            wheat_def['char'], wheat_def['color'], wheat_def['passable'], wheat_def['name'], properties=wheat_def['properties'].copy()
        )
        starting_xp = self.world.player.skills.experience.get("farming", 0)

        with patch('random.random', return_value=0.1):
            self.world.player_attempt_harvest(target_x, target_y)

        self.assertGreater(self.world.player.skills.experience["farming"], starting_xp)


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
        wolf1.combat.is_hostile_to_player = True
        wolf2.combat.is_hostile_to_player = True
        wolf1.economic.profession = "Creature"
        wolf2.economic.profession = "Creature"
        self.world.entity_positions_dirty = True
        self.world._update_npc_fov(civilian)

        # 2. Execution
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL

        from unittest.mock import patch
        with patch.object(self.world, "_update_npc_fov"), patch("simulation.systems.survival.update_npc_survival"):
            # Mock threat detection because the FOV logic heavily depends on lighting and precise raycasting
            civilian.is_frightened = True
            civilian.threat_source_ids = [wolf1.id, wolf2.id]
            # Initialize map before overriding it
            self.world.npc_fov_maps[civilian.id] = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
            self.world.npc_fov_maps[civilian.id][int(wolf1.y), int(wolf1.x)] = True
            self.world.npc_fov_maps[civilian.id][int(wolf2.y), int(wolf2.x)] = True
            self.world._find_best_adjacent_tile = lambda x, y, npc: (x+1, y) # Force safe spot adjacency properly
            self.world._update_npc_schedules()

        # 3. Assertion
        self.assertTrue(getattr(civilian, 'is_frightened', False))
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

        wolf1.combat.is_hostile_to_player = True
        wolf2.combat.is_hostile_to_player = True
        wolf1.economic.profession = "Creature"
        wolf2.economic.profession = "Creature"
        self.world.village_npcs.extend([guard1, guard2])
        self.world.npcs.extend([wolf1, wolf2])
        self.world.entity_positions_dirty = True

        plains_def = TILE_DEFINITIONS["plains"]
        for y_offset in range(-15, 16):
            for x_offset in range(-15, 16):
                self._clear_area_and_place_tile(center_x + x_offset, center_y + y_offset, plains_def)

        well_def = TILE_DEFINITIONS["well"]
        self._clear_area_and_place_tile(alarm_spot[0], alarm_spot[1], well_def)
        self.assertFalse(self.world.get_tile_at(alarm_spot[0], alarm_spot[1]).passable)

        wolf1.combat.is_hostile_to_player = True
        wolf2.combat.is_hostile_to_player = True
        self.world.entity_positions_dirty = True
        self.world._update_player_fov()
        self.world._update_npc_fov(guard1)

        if guard1.id in self.world.npc_fov_maps:
            self.world.npc_fov_maps[guard1.id][int(wolf1.y), int(wolf1.x)] = True
            self.world.npc_fov_maps[guard1.id][int(wolf2.y), int(wolf2.x)] = True

        # 2. Execution
        from unittest.mock import patch
        with patch.object(self.world, "_update_npc_fov"), patch("simulation.systems.survival.update_npc_survival"):
            with patch.object(self.world, "calculate_path", return_value=[(guard1.x, guard1.y), (guard1.x+1, guard1.y)]):
                guard1.is_frightened = True
                guard1.threat_source_ids = [wolf1.id, wolf2.id]

                # Initialize fov map
                self.world.npc_fov_maps[guard1.id] = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
                self.world.npc_fov_maps[guard1.id][int(wolf1.y), int(wolf1.x)] = True
                self.world.npc_fov_maps[guard1.id][int(wolf2.y), int(wolf2.x)] = True

                # Mock threat tracking
                wolf1.x = int(wolf1.x)
                wolf1.y = int(wolf1.y)
                wolf2.x = int(wolf2.x)
                wolf2.y = int(wolf2.y)

                self.world._find_best_adjacent_tile = lambda x, y, npc: (x+1, y) # Force safe spot adjacency properly
                self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
                self.world._update_npc_schedules()

        # 3. Assertion (Guard 1 starts alerting)
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
        with patch.object(self.world, "_update_npc_fov"), patch("simulation.systems.survival.update_npc_survival"):
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

        wolf1.combat.is_hostile_to_player = True
        wolf2.combat.is_hostile_to_player = True
        wolf1.economic.profession = "Creature"
        wolf2.economic.profession = "Creature"

        self.world.npcs.extend([wolf1, wolf2])
        self.world.entity_positions_dirty = True

        plains_def = TILE_DEFINITIONS["plains"]
        for y_offset in range(-5, 6):
            for x_offset in range(-5, 6):
                self._clear_area_and_place_tile(center_x + x_offset, center_y + y_offset, plains_def)

        self.world._update_player_fov()
        civilian._force_fov_update = True
        self.world._update_npc_fov(civilian)

        # Override maps for tests
        civilian.is_frightened = True
        civilian.threat_source_ids = [wolf1.id, wolf2.id]
        self.world.npc_fov_maps[civilian.id] = engine.np.zeros((config.WORLD_HEIGHT, config.WORLD_WIDTH), dtype=bool)
        self.world.npc_fov_maps[civilian.id][int(wolf1.y), int(wolf1.x)] = True
        self.world.npc_fov_maps[civilian.id][int(wolf2.y), int(wolf2.x)] = True

        # 2. Execution (Initial fear)
        from unittest.mock import patch
        with patch.object(self.world, "_update_npc_fov"), patch("simulation.systems.survival.update_npc_survival"):
            self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
            self.world._update_npc_schedules()
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
        with patch.object(self.world, "_update_npc_fov"), patch("simulation.systems.survival.update_npc_survival"):
            self.world._update_npc_schedules()

        # 5. Assertion
        self.assertFalse(civilian.is_frightened)
        self.assertEqual(civilian.schedule.current_task, "idle")


class TestCraftingVisualFeedback(unittest.TestCase):
    """Player crafting completion spawns a spark particle-burst visual effect."""

    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = self.mock_ollama_patcher.start()
        mock_npc_data = {"name": "Test NPC", "personality": "test", "dialogue": ["Hi"]}
        self.mock_call_llm.return_value = json.dumps(mock_npc_data)
        self.world = World(seed=1)

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def test_craft_item_spawns_spark_particle_burst_at_player_position(self):
        self.world.player.add_item("medicinal_herb", 2)

        self.world.craft_item("healing_salve")

        self.assertTrue(self.world.player.has_item("healing_salve"))
        burst_effects = [e for e in self.world.visual_effects if getattr(e, "effect_type", None) == "particle_burst"]
        self.assertEqual(len(burst_effects), 1)
        self.assertEqual(burst_effects[0].kind, "spark")
        self.assertEqual((burst_effects[0].x, burst_effects[0].y), (float(self.world.player.x), float(self.world.player.y)))

    def test_craft_item_skips_particle_burst_when_ingredients_missing(self):
        # No medicinal_herb given - crafting should fail before touching visual_effects.
        self.world.craft_item("healing_salve")

        self.assertFalse(self.world.player.has_item("healing_salve"))
        burst_effects = [e for e in self.world.visual_effects if getattr(e, "effect_type", None) == "particle_burst"]
        self.assertEqual(burst_effects, [])
