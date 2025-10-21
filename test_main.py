
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
            self.world._apply_temperature_effects()

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

        # 3. Ensure the location is not sheltered (mock the shelter check to be certain)
        with patch('engine.World._check_for_shelter', return_value=False) as mock_shelter_check:
            # 4. Call the weather update function
            self.world._update_weather()
            mock_shelter_check.assert_called_with(fire_x, fire_y)

        # 5. Assert the fire is now extinguished
        extinguished_tile = self.world.get_tile_at(fire_x, fire_y)
        self.assertIsNotNone(extinguished_tile)
        self.assertEqual(extinguished_tile.name, "Simple Fire Pit")


if __name__ == '__main__':
    unittest.main()
