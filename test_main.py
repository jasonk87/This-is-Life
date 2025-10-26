
import unittest
from unittest.mock import patch
from engine import World
import json

class TestGame(unittest.TestCase):
    @patch('engine.World._call_ollama')
    def test_world_initialization(self, mock_call_ollama):
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
        mock_call_ollama.return_value = json.dumps(mock_npc_data)

        try:
            world = World()
            self.assertIsNotNone(world)
            self.assertIsNotNone(world.player)
        except Exception as e:
            self.fail(f"World initialization failed with an exception: {e}")

class TestTemperatureSystem(unittest.TestCase):
    @patch('engine.World._call_ollama')
    def setUp(self, mock_call_ollama):
        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        mock_call_ollama.return_value = json.dumps(mock_npc_data)
        self.world = World()

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
        self.world.chunks[fire_y // 20][fire_x // 20].tiles[fire_y % 20][fire_x % 20] = fire_pit_tile

        # Rerun temperature update to capture heat source effect
        self.world._update_player_temperature()
        temp_with_fire = self.world.ambient_temperature

        self.assertGreater(temp_with_fire, initial_temp)

    def test_player_gets_wet_in_rain(self):
        self.world.weather = "rain"
        self.world.player.is_sheltered = False
        self.world._update_player_wetness()
        self.assertTrue(self.world.player.is_wet)
        self.assertGreater(self.world.player.wetness_timer, 0)

    def test_clothing_insulation_effect(self):
        player = self.world.player
        player.temperature = 30 # Set a cold body temp

        self.world._update_player_temperature()
        temp_change_without_cloak = player.temperature - 30

        player.equip_armor("fur_cloak")
        player.temperature = 30 # Reset temp

        self.world._update_player_temperature()
        temp_change_with_cloak = player.temperature - 30

        self.assertGreater(temp_change_with_cloak, temp_change_without_cloak)

    def test_freezing_effect(self):
        player = self.world.player
        initial_hp = player.hp
        player.temperature = 34.0 # Below freezing threshold

        # Update temperature to apply status effect
        self.world._update_player_temperature()
        self.assertIn("Freezing", player.status_effects)

        from config import DAY_LENGTH_TICKS
        ticks_for_damage = DAY_LENGTH_TICKS // 25

        for i in range(ticks_for_damage + 1):
            self.world.game_time += 1
            self.world._apply_temperature_effects(player)

        self.assertLess(player.hp, initial_hp)

    def test_rain_extinguishes_fire(self):
        from data.decorations import DECORATION_ITEM_DEFINITIONS
        from tile_types import Tile

        # 1. Place a lit fire pit
        fire_x, fire_y = self.world.player.x + 2, self.world.player.y
        fire_pit_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_pit_tile = Tile(char=fire_pit_def['char'], color=fire_pit_def['color'], passable=False, name="fire_pit_lit", properties=fire_pit_def['properties'].copy())

        chunk_x, chunk_y = fire_x // 20, fire_y // 20
        local_x, local_y = fire_x % 20, fire_y % 20
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
    @patch('engine.World._call_ollama')
    def setUp(self, mock_call_ollama):
        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        mock_call_ollama.return_value = json.dumps(mock_npc_data)
        self.world = World()

    def test_rain_waters_crops_and_they_grow(self):
        from data.tiles import TILE_DEFINITIONS
        from tile_types import Tile

        # 1. Place a growing wheat tile
        crop_x, crop_y = self.world.player.x + 2, self.world.player.y
        growing_def = TILE_DEFINITIONS["wheat_growing"]
        # Use .copy() on properties to avoid modifying the global definition
        growing_tile = Tile(char=growing_def['char'], color=growing_def['color'], passable=True, name="Growing Wheat", properties=growing_def['properties'].copy())

        chunk_x, chunk_y = crop_x // 20, crop_y // 20
        local_x, local_y = crop_x % 20, crop_y % 20
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
        self.assertEqual(mature_tile.name, "Mature Wheat Crop")


class TestNPCBehaviorSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_ollama')
        self.mock_call_ollama = self.mock_ollama_patcher.start()

        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_ollama.return_value = json.dumps(mock_npc_data)

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
        c_chunk_x, c_chunk_y = npc.x // 20, npc.y // 20
        c_local_x, c_local_y = npc.x % 20, npc.y % 20
        self.world.chunks[c_chunk_y][c_chunk_x].tiles[c_local_y][c_local_x] = plains_tile

        # Clear a path for the NPC
        for y_offset in range(-2, 3):
            for x_offset in range(0, 6):
                clear_x, clear_y = npc.x + x_offset, npc.y + y_offset
                self.world.get_tile_at(clear_x, clear_y) # Ensure chunk is generated
                c_chunk_x, c_chunk_y = clear_x // 20, clear_y // 20
                c_local_x, c_local_y = clear_x % 20, clear_y % 20
                self.world.chunks[c_chunk_y][c_chunk_x].tiles[c_local_y][c_local_x] = plains_tile

        fire_pit_def = DECORATION_ITEM_DEFINITIONS["fire_pit_lit"]
        fire_pit_tile = Tile(char=fire_pit_def['char'], color=fire_pit_def['color'], passable=False, name="fire_pit_lit", properties=fire_pit_def['properties'].copy())

        chunk_x, chunk_y = fire_x // 20, fire_y // 20
        local_x, local_y = fire_x % 20, fire_y % 20
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = fire_pit_tile

        # 3. Manually update NPC temperature to freezing
        npc.temperature = 34.0
        self.world._update_npc_temperature(npc)
        self.assertIn("Freezing", npc.status_effects)

        # 4. Advance time to ensure the schedule update runs
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL

        # 5. Run the NPC schedule update
        self.world._update_npc_schedules()

        # 6. Assert that the NPC is now seeking warmth and pathfinding to the fire
        self.assertEqual(npc.current_task, "seeking_warmth")
        self.assertIsNotNone(npc.current_path)
        # The path destination should be adjacent to the fire, not on it, because the fire is not passable.
        path_dest = npc.current_destination_coords
        self.assertIsNotNone(path_dest)
        self.assertTrue(abs(path_dest[0] - fire_x) + abs(path_dest[1] - fire_y) == 1)


class TestClothProductionSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_ollama')
        self.mock_call_ollama = self.mock_ollama_patcher.start()

        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_ollama.return_value = json.dumps(mock_npc_data)

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

        chunk_x, chunk_y = anvil_x // 20, anvil_y // 20
        local_x, local_y = anvil_x % 20, anvil_y % 20
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
        initial_wool_quantity = self.world.player.inventory[wool_indices[0]].get("quantity", 0)
        self.assertGreater(initial_wool_quantity, 0)

        # Check that sheep can't be shorn again immediately
        self.world.player_attempt_shear(sheep)
        current_wool_quantity = self.world.player.inventory[wool_indices[0]].get("quantity", 0)
        self.assertEqual(initial_wool_quantity, current_wool_quantity)


        # --- 2. Crafting ---
        # Add a loom
        loom_def = DECORATION_ITEM_DEFINITIONS["loom"]
        loom_tile = Tile(char=loom_def['char'], color=loom_def['color'], passable=False, name="Loom", properties=loom_def['properties'].copy())
        loom_x, loom_y = self.world.player.x - 1, self.world.player.y - 1

        chunk_x, chunk_y = loom_x // 20, loom_y // 20
        local_x, local_y = loom_x % 20, loom_y % 20
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
        initial_insulation = self.world.player.clothing_insulation
        self.world.player.equip_armor("cloth_tunic")
        self.assertGreater(self.world.player.clothing_insulation, initial_insulation)

class TestPredatorPreyAI(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_ollama')
        self.mock_call_ollama = self.mock_ollama_patcher.start()

        mock_npc_data = { "name": "Test NPC", "personality": "test", "dialogue": ["Hi"] }
        self.mock_call_ollama.return_value = json.dumps(mock_npc_data)

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
        predator = Animal(x=self.world.player.x + 5, y=self.world.player.y, name="Dire Wolf", animal_type="dire_wolf")
        prey = Animal(x=self.world.player.x + 10, y=self.world.player.y, name="Sheep", animal_type="sheep")

        # Set predator to be hungry
        predator.hunger = predator.max_hunger
        prey.hunger = 0

        # HACK: Manually set attributes required by the new AI/movement logic
        # These are not set by default on manually created test animals.
        setattr(predator, 'speed', 2)
        setattr(predator, 'attack_range', 2)
        setattr(prey, 'speed', 1)

        self.world.npcs.extend([predator, prey])

        # Ensure the area is clear for movement
        plains_def = TILE_DEFINITIONS["plains"]
        plains_tile = Tile(char=plains_def['char'], color=plains_def['color'], passable=True, name="Plains", properties={})

        # Clear a large area to ensure pathfinding works
        for y_offset in range(-15, 16):
            for x_offset in range(-10, 41):
                clear_x, clear_y = self.world.player.x + x_offset, self.world.player.y + y_offset
                try:
                    self.world.get_tile_at(clear_x, clear_y)
                    chunk_x, chunk_y = clear_x // 20, clear_y // 20
                    local_x, local_y = clear_x % 20, clear_y % 20
                    self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = plains_tile
                except IndexError:
                    pass # Ignore out-of-bounds coordinates

        # 2. Execution & Assertion (Predator starts hunting)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        self.assertEqual(predator.current_task, "hunting")
        self.assertTrue(predator.current_path, "Predator should have a path to the prey.")
        self.assertEqual(predator.task_target_entity_id, prey.id)

        # 3. Execution & Assertion (Prey starts fleeing)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        # Run schedules again so prey can react to the hunting predator
        self.world._update_npc_schedules()

        self.assertEqual(prey.current_task, "fleeing")
        self.assertTrue(prey.current_path, "Prey should have a path to flee.")
        # Check that prey's path is moving it away from the predator
        if prey.current_path and len(prey.current_path) > 1:
            dist_before = (prey.x - predator.x)**2 + (prey.y - predator.y)**2
            next_pos = prey.current_path[1]
            dist_after = (next_pos[0] - predator.x)**2 + (next_pos[1] - predator.y)**2
            self.assertGreater(dist_after, dist_before, "Prey should be moving away from the predator.")

        # 4. Execution (Simulate chase and attack)
        initial_prey_hp = prey.hp
        for _ in range(240): # Simulate a few turns
            self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
            self.world._update_npc_schedules()
            self.world._update_npc_movement()
            if prey.is_dead:
                break

        # The hunger reset now happens inside npc_attempt_attack_npc, which is called
        # during the _update_npc_schedules inside the loop. No extra update is needed.
        # A final update would cause the predator's hunger to start increasing again.

        # 5. Assertion (Attack and outcome)
        self.assertLess(prey.hp, initial_prey_hp, "Prey should have taken damage")
        self.assertTrue(prey.is_dead, "Prey should be dead after the chase.")
        self.assertEqual(predator.hunger, 0, "Predator should not be hungry after a successful kill")


class TestFearSystem(unittest.TestCase):
    def setUp(self):
        self.mock_ollama_patcher = patch('engine.World._call_ollama')
        self.mock_call_ollama = self.mock_ollama_patcher.start()

        mock_npc_data = {
            "name": "Generic Villager", "personality": "neutral", "dialogue": ["..."],
            "wealth_level": "average", "combat_behavior": "defensive", "base_attack_name": "fists"
        }
        self.mock_call_ollama.return_value = json.dumps(mock_npc_data)

        # Use a fixed seed for any remaining randomness
        self.world = World(seed=1337)
        self.world.current_season_index = 1 # Summer, to ensure neutral temperature

    def tearDown(self):
        self.mock_ollama_patcher.stop()

    def _clear_area_and_place_tile(self, x, y, tile_def):
        """Helper to ensure a chunk is generated, clear a tile, and place a new one."""
        from tile_types import Tile
        self.world.get_tile_at(x, y) # Ensure chunk generation
        chunk_x, chunk_y = x // 20, y // 20
        local_x, local_y = x % 20, y % 20
        tile = Tile(char=tile_def['char'], color=tile_def['color'], passable=tile_def['passable'], name=tile_def['name'], properties=tile_def.get('properties', {}).copy())
        self.world.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = tile
        # Also update the transparency map for FOV calculations
        self.world.transparency_map[x, y] = not tile.blocks_fov

    def test_civilian_flees_from_wolf_pack(self):
        from entities.base import NPC
        from entities.animal import Animal
        from engine import Village, Building
        from data.tiles import TILE_DEFINITIONS
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Manual Setup
        center_x, center_y = 50, 50
        village = Village()
        chunk_x, chunk_y = center_x // 20, center_y // 20
        self.world.chunks[chunk_y][chunk_x].village = village

        home_building = Building(center_x - 10, center_y - 10, 5, 5, building_type="house", category="residential", global_chunk_x_start=chunk_x * 20, global_chunk_y_start=chunk_y * 20)
        village.add_building(home_building)
        self.world.buildings_by_id[home_building.id] = home_building

        civilian = NPC(x=center_x, y=center_y, name="Civilian")
        civilian.profession = "Farmer"
        civilian.home_building_id = home_building.id
        self.world.village_npcs.append(civilian)

        wolf1 = Animal(x=civilian.x + 2, y=civilian.y + 2, name="Wolf", animal_type="wolf")
        wolf2 = Animal(x=civilian.x + 3, y=civilian.y + 2, name="Wolf", animal_type="wolf")
        self.world.npcs.extend([wolf1, wolf2])

        plains_def = TILE_DEFINITIONS["plains"]
        for y_offset in range(-15, 16):
            for x_offset in range(-15, 16):
                self._clear_area_and_place_tile(center_x + x_offset, center_y + y_offset, plains_def)

        self.world.update_fov()
        self.assertTrue(self.world.npc_fov_maps[civilian.id][wolf1.x, wolf1.y])

        # 2. Execution
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 3. Assertion
        self.assertTrue(civilian.is_frightened)
        self.assertEqual(civilian.current_task, "fleeing_from_threat")
        self.assertIsNotNone(civilian.current_path)
        self.assertEqual(civilian.current_destination_coords, (home_building.global_center_x, home_building.global_center_y))

    def test_guard_alerts_other_guards(self):
        from entities.base import NPC
        from entities.animal import Animal
        from engine import Village, Building
        from data.tiles import TILE_DEFINITIONS
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Manual Setup
        center_x, center_y = 50, 50
        alarm_spot = (center_x, center_y)

        village = Village()
        village.interaction_points["town_square_center"] = alarm_spot
        chunk_x, chunk_y = center_x // 20, center_y // 20
        self.world.chunks[chunk_y][chunk_x].village = village

        home_building = Building(2, 2, 5, 5, building_type="house", category="residential", global_chunk_x_start=chunk_x * 20, global_chunk_y_start=chunk_y * 20)
        village.add_building(home_building)
        self.world.buildings_by_id[home_building.id] = home_building

        guard1 = NPC(x=alarm_spot[0] - 5, y=alarm_spot[1], name="Guard")
        guard1.profession = "Guard"
        guard1.home_building_id = home_building.id

        guard2 = NPC(x=alarm_spot[0] - 2, y=alarm_spot[1] - 2, name="Alerted Guard")
        guard2.profession = "Guard"

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

        self.world.update_fov()
        self.assertTrue(self.world.npc_fov_maps[guard1.id][wolf1.x, wolf1.y])

        # 2. Execution
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 3. Assertion (Guard 1 starts alerting)
        self.assertTrue(guard1.is_frightened)
        self.assertEqual(guard1.current_task, "alerting_guards")
        self.assertIsNotNone(guard1.current_path, "Guard1 should have a path to the alarm spot")

        destination = guard1.current_destination_coords
        self.assertIsNotNone(destination)
        distance_to_alarm = abs(destination[0] - alarm_spot[0]) + abs(destination[1] - alarm_spot[1])
        self.assertEqual(distance_to_alarm, 1, "Guard should be pathing to a tile adjacent to the alarm spot.")

        self.assertFalse(guard2.is_hostile_to_player, "Guard 2 should not be alerted yet.")

        # 4. Manually move guard1 to their destination
        guard1.x, guard1.y = destination
        guard1.current_path = []

        # 5. Execution (Second update)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 6. Assertion (Guards become hostile)
        self.assertTrue(guard1.is_hostile_to_player, "Alerting guard should become hostile.")
        self.assertTrue(guard2.is_hostile_to_player, "Nearby guard should become hostile after alarm.")

    def test_npc_calms_down_when_threat_is_gone(self):
        from entities.base import NPC
        from entities.animal import Animal
        from data.tiles import TILE_DEFINITIONS
        from config import NPC_SCHEDULE_UPDATE_INTERVAL

        # 1. Manual Setup
        center_x, center_y = 50, 50
        civilian = NPC(x=center_x, y=center_y, name="Civilian")
        civilian.profession = "Farmer"
        self.world.village_npcs.append(civilian)

        wolf1 = Animal(x=center_x + 2, y=center_y, name="Wolf", animal_type="wolf")
        wolf2 = Animal(x=center_x + 3, y=center_y, name="Wolf", animal_type="wolf")
        self.world.npcs.extend([wolf1, wolf2])

        plains_def = TILE_DEFINITIONS["plains"]
        for y_offset in range(-5, 6):
            for x_offset in range(-5, 6):
                self._clear_area_and_place_tile(center_x + x_offset, center_y + y_offset, plains_def)

        self.world.update_fov()
        self.assertTrue(self.world.npc_fov_maps[civilian.id][wolf1.x, wolf1.y])


        # 2. Execution (Initial fear)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()
        self.assertTrue(civilian.is_frightened)
        self.assertNotEqual(civilian.current_task, "idle")

        # 3. Remove the threat
        self.world.npcs.remove(wolf1)
        self.world.npcs.remove(wolf2)

        # Update FOV so NPC no longer sees them
        self.world.update_fov()
        # self.assertFalse(self.world.npc_fov_maps[civilian.id][wolf1.x, wolf1.y]) # This assertion is incorrect

        # 4. Execution (Calm down)
        self.world.game_time += NPC_SCHEDULE_UPDATE_INTERVAL
        self.world._update_npc_schedules()

        # 5. Assertion
        self.assertFalse(civilian.is_frightened)
        self.assertEqual(civilian.current_task, "idle")

if __name__ == '__main__':
    unittest.main()
