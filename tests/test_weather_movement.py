import json
import unittest
from unittest.mock import patch

from engine import World


class TestWeatherMovementCostMultiplier(unittest.TestCase):
    """Ideation-audit item: WEATHER_DEFINITIONS['snow']['slows_movement']
    was declared in data/environment.py but never read anywhere in the
    codebase - confirmed via a full-repo grep before this fix. Wired into
    Player.handle_player_movement's movement_cost calculation, which is the
    real "how many game ticks does this step take" mechanism
    (simulation/systems/tick.py adds action_cost-1 straight onto
    world.game_time). Deliberately player-only - see
    _get_weather_movement_cost_multiplier's docstring for why NPC movement
    (an integer moves-per-tick "speed" value, not a tick-cost value) isn't
    touched in this pass."""

    def setUp(self):
        mock_ollama_patcher = patch('engine.World._call_llm')
        self.mock_call_llm = mock_ollama_patcher.start()
        self.addCleanup(mock_ollama_patcher.stop)
        self.mock_call_llm.return_value = json.dumps({
            "name": "Test NPC",
            "personality": "neutral",
            "dialogue": ["..."],
        })
        self.world = World(seed=17)

    def test_multiplier_is_1_for_clear_weather(self):
        self.world.weather = "clear"
        self.assertEqual(self.world._get_weather_movement_cost_multiplier(), 1.0)

    def test_multiplier_is_1_for_rain(self):
        """Rain applies wetness but its slows_movement flag is False -
        confirms this only reacts to the flag, not to weather != clear."""
        self.world.weather = "rain"
        self.assertEqual(self.world._get_weather_movement_cost_multiplier(), 1.0)

    def test_multiplier_is_elevated_for_snow(self):
        self.world.weather = "snow"
        self.assertGreater(self.world._get_weather_movement_cost_multiplier(), 1.0)

    def test_unknown_weather_key_does_not_crash_and_does_not_slow(self):
        self.world.weather = "some_future_weather_type"
        self.assertEqual(self.world._get_weather_movement_cost_multiplier(), 1.0)

    def test_snow_makes_a_normal_step_cost_more_action_time_than_clear(self):
        self.world.weather = "clear"
        with patch("engine.random.random", return_value=0.99):  # skip dust-particle roll
            clear_cost = self.world.handle_player_movement(1, 0)

        origin_x, origin_y = self.world.player.x, self.world.player.y
        self.world.weather = "snow"
        with patch("engine.random.random", return_value=0.99):
            snow_cost = self.world.handle_player_movement(-1, 0)  # step back to a fresh tile

        self.assertGreater(snow_cost, clear_cost)
        # Player still actually moved - snow slows, it doesn't stop.
        self.assertEqual((self.world.player.x, self.world.player.y), (origin_x - 1, origin_y))

    def test_riding_movement_cost_also_respects_snow(self):
        from engine import NPC

        animal = NPC(self.world.player.x, self.world.player.y, name="Horse", dialogue=["Neigh"], personality="villager", player_id=self.world.player.id)
        self.world.npcs.append(animal)
        self.world.player.state.is_riding = True
        self.world.player.state.riding_animal_id = animal.id

        self.world.weather = "clear"
        clear_cost = self.world.handle_player_movement(1, 0)

        self.world.weather = "snow"
        snow_cost = self.world.handle_player_movement(-1, 0)

        self.assertGreater(snow_cost, 0)
        self.assertGreater(clear_cost, 0)
        self.assertGreaterEqual(snow_cost, clear_cost)


if __name__ == "__main__":
    unittest.main()
