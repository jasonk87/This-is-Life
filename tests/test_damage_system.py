import unittest
from unittest.mock import MagicMock
import engine
from entities.base import NPC
from tests.world_cache import fresh_world

class TestLocalizedDamage(unittest.TestCase):
    def test_localized_damage_broken_leg(self):
        # Create an NPC
        npc = NPC(x=10, y=10, name="Test NPC")
        npc.combat.max_hp = 30
        npc.combat.hp = 30

        # Mock random.choice to always hit "left_leg"
        import random
        original_choice = random.choice
        def mock_choice(seq):
            if "left_leg" in seq:
                return "left_leg"
            return original_choice(seq)

        random.choice = mock_choice

        # Test NPC takes damage to leg
        npc.take_damage(6, world=None) # Left leg has 5 hp, so 6 damage should break it and spill 1 to torso

        self.assertEqual(npc.combat.body_parts_hp["left_leg"], 0)
        self.assertIn("broken_leg", npc.physical.status_effects)
        self.assertEqual(npc.combat.hp, 24) # 30 - 6

        # Restore random.choice
        random.choice = original_choice

    def test_player_broken_leg_movement_cooldown(self):
        from simulation.systems.body_combat import ensure_body
        from tests.test_weather_movement import stand_on_open_ground
        world = fresh_world(seed=13, pre_simulate=False)
        player = world.player
        stand_on_open_ground(world)
        world.weather = "clear"
        healthy_cost = world.handle_player_movement(1, 0)
        world.handle_player_movement(-1, 0)
        player.physical.status_effects.append("broken_leg")
        ensure_body(player, world.game_time)  # Upgrade the legacy injury, not a UI throttle.
        player.state.current_path = [(player.x+1, player.y)]
        start = world.game_time
        world.update()
        self.assertGreater(player.state.move_ready_tick - start, healthy_cost)
        self.assertEqual(player.state.move_cooldown, 0)

if __name__ == '__main__':
    unittest.main()
