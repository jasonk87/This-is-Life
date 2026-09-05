import unittest
import config
import engine
from engine import NPC, World
from simulation.systems.scheduling import find_dispersed_destination_coords, update_npc_daily_goal_policy
from simulation.systems.survival import check_emergency_npc_sustenance, update_npc_survival
from simulation.systems.task_types import TaskType
from simulation.world_model import Village
from tests.world_cache import fresh_world


class TestSchedulingAndSpatialDispersion(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=9001, pre_simulate=False)
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(30, 30)]}
        self.world.villages = [self.village]
        self.world.chunks[0][0].village = self.village

    def _make_npc(self, x=10, y=10, name="Citizen", profession="Commoner", age=25):
        npc = NPC(
            x=x,
            y=y,
            name=name,
            dialogue=["Hello."],
            personality="calm",
            family_ties={},
            attitude_to_player="neutral",
            player_id=self.world.player.id,
        )
        npc.economic.profession = profession
        npc.age = age
        return npc

    def test_town_square_spatial_dispersion_avoids_stacking(self):
        # When multiple NPCs seek the town square, they receive distinct, non-overlapping coordinates.
        npcs = [self._make_npc(x=10 + i, y=10, name=f"Citizen_{i}") for i in range(6)]
        self.world.village_npcs = npcs
        self.world._rebuild_entity_positions()

        destinations = set()
        for npc in npcs:
            dest = find_dispersed_destination_coords(
                self.world,
                (30, 30),
                radius=4,
                requesting_entity=npc,
            )
            npc.schedule.current_destination_coords = dest
            destinations.add(dest)

        self.assertEqual(len(destinations), 6, f"Expected 6 distinct destinations, got: {destinations}")

    def test_arrival_maintains_active_leisure_state_instead_of_idle_drop(self):
        # Arriving at a leisure activity preserves the active task state with a timer instead of resetting to IDLE.
        from unittest.mock import patch

        npc = self._make_npc(x=30, y=30, profession="Commoner")
        npc.schedule.current_task = TaskType.IDLE
        
        is_leisure_time = config.DAY_LENGTH_TICKS * 0.75
        self.world.active_scheduled_events = {"harvest_festival": {"draws_crowd": True}}
        
        with patch("random.random", return_value=0.01):
            update_npc_daily_goal_policy(self.world, npc, int(is_leisure_time))
        
        # When goal policy assigns attending_festival at destination, it transitions to active festival state with timer
        self.assertIn(
            npc.schedule.current_task,
            ["attending_festival", "at_leisure", "socializing_at_focal_point", "going_to_tavern", "socializing"],
            f"Expected persistent leisure state, got: {npc.schedule.current_task}",
        )
        self.assertGreater(getattr(npc, "leisure_timer", 0), 0)

    def test_idle_confused_self_recovery(self):
        # An NPC stuck in idle_confused automatically clears blocked state and recovers within 8 ticks.
        npc = self._make_npc(x=15, y=15, profession="Farmer")
        npc.schedule.current_task = "idle_confused"
        npc.schedule.current_path = [(16, 16)]
        npc.schedule.current_destination_coords = (16, 16)
        
        time_tick = int(config.DAY_LENGTH_TICKS * 0.5)
        
        for _ in range(9):
            update_npc_daily_goal_policy(self.world, npc, time_tick)
            
        self.assertNotEqual(npc.schedule.current_task, "idle_confused")
        self.assertEqual(npc.schedule.current_path, [])
        self.assertIsNone(npc.schedule.current_destination_coords)

    def test_emergency_pocket_food_consumption_during_night(self):
        # Starving NPC with pocket rations consumes food and recovers hunger.
        npc = self._make_npc(x=20, y=20)
        npc.physical.hunger = 85
        npc.economic.npc_inventory = {"bread": 2}
        
        consumed = check_emergency_npc_sustenance(self.world, npc)
        
        self.assertTrue(consumed)
        self.assertEqual(npc.physical.hunger, 50)
        self.assertEqual(npc.economic.npc_inventory["bread"], 1)

    def test_emergency_pocket_drink_consumption(self):
        # Thirsty NPC with pocket water flask consumes drink and recovers thirst.
        npc = self._make_npc(x=20, y=20)
        npc.physical.thirst = 80
        npc.economic.npc_inventory = {"water_flask": 1}
        
        consumed = check_emergency_npc_sustenance(self.world, npc)
        
        self.assertTrue(consumed)
        self.assertEqual(npc.physical.thirst, 40)
        self.assertNotIn("water_flask", npc.economic.npc_inventory)


if __name__ == "__main__":
    unittest.main()
