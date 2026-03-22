import unittest
from unittest.mock import MagicMock
import engine
from entities.base import NPC

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
        world = engine.World(seed=13)
        player = world.player
        player.physical.status_effects.append("broken_leg")

        initial_cooldown = player.state.move_cooldown
        world.handle_player_movement = MagicMock(return_value=1)

        # Manually trigger movement logic from update
        player.state.current_path = [(player.x+1, player.y)]
        world.update()

        self.assertEqual(player.state.move_cooldown, 10)

if __name__ == '__main__':
    unittest.main()
