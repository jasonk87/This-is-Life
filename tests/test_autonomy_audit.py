import unittest
from entities.base import NPC
from engine import World
from simulation.systems.task_types import TaskType

class TestAutonomyAudit(unittest.TestCase):
    def test_autonomy_audit_updates_counters_and_npc_state(self):
        # Prevent calling out to LLMs during World init by patching OLLAMA config or just mocking OLLAMA endpoint directly
        import engine
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False

        # We also need to mock `all_npcs` chain or simply use `world` properly
        world = World(seed=42)

        npc = NPC(10, 10, name="Test NPC")
        world.npcs = [npc]
        world.village_npcs = []

        # We need to mock player_fov_map since it's checked by update
        import numpy as np
        from config import WORLD_HEIGHT, WORLD_WIDTH
        world.player_fov_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), False)

        # 1. Idle state
        world._update_autonomy_audit()
        self.assertEqual(world.autonomy_counters["active"], sum(1 for _ in world.all_npcs))
        # Find our NPC
        test_npc = next((n for n in world.all_npcs if n.name == "Test NPC"), None)
        self.assertIsNotNone(test_npc)
        self.assertEqual(test_npc.debug_autonomy["path_status"], "none")
        self.assertEqual(test_npc.debug_autonomy["moved_this_tick"], False)

        # 2. Moving state
        test_npc.x = 11
        test_npc.schedule.current_path = [(10, 10), (11, 10), (12, 10)]
        test_npc.schedule.current_task = "going_to_work"
        world._update_autonomy_audit()

        # Should be 'moving'
        self.assertTrue(test_npc.debug_autonomy["moved_this_tick"])
        self.assertEqual(test_npc.debug_autonomy["path_status"], "moving")
        self.assertEqual(test_npc.debug_autonomy["last_task"], "going_to_work")
        self.assertEqual(test_npc.debug_autonomy["previous_task"], TaskType.IDLE)

        # 3. Blocked state
        test_npc.x = 11 # didn't move
        test_npc.schedule.path_blocked_turns = 1
        world._update_autonomy_audit()
        self.assertFalse(test_npc.debug_autonomy["moved_this_tick"])
        self.assertEqual(test_npc.debug_autonomy["path_status"], "blocked")

        # 4. Failed path state
        test_npc.schedule.current_path = []
        test_npc.schedule.current_destination_coords = (15, 10)
        world._update_autonomy_audit()
        self.assertEqual(test_npc.debug_autonomy["path_status"], "failed")

if __name__ == '__main__':
    unittest.main()
