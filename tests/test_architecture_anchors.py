import unittest
from engine import Building
from simulation.systems.scheduling import update_npc_daily_goal_policy
from config import DAY_LENGTH_TICKS
from entities.base import NPC
from unittest.mock import MagicMock

class MockWorld:
    def __init__(self):
        self.buildings_by_id = {}

    def _get_building_global_center_coords(self, building_id):
        building = self.buildings_by_id.get(building_id)
        if building:
            return (building.global_center_x, building.global_center_y)
        return None

    def _building_contains_item_with_interaction(self, building, interaction):
        return False

    def calculate_path(self, start_x, start_y, end_x, end_y):
        return [(start_x, start_y), (end_x, end_y)]

class TestArchitectureAnchors(unittest.TestCase):
    def setUp(self):
        self.world = MockWorld()
        self.home = Building(0, 0, 10, 10, building_type="house")
        self.home.id = "home_1"
        self.home.global_center_x = 5
        self.home.global_center_y = 5

        self.workplace = Building(20, 20, 10, 10, building_type="workshop")
        self.workplace.id = "work_1"
        self.workplace.global_center_x = 25
        self.workplace.global_center_y = 25

        self.world.buildings_by_id[self.home.id] = self.home
        self.world.buildings_by_id[self.workplace.id] = self.workplace

        self.npc = NPC(0, 0, "Test NPC")
        self.npc.schedule.home_building_id = self.home.id
        self.npc.schedule.work_building_id = self.workplace.id
        self.npc.economic.profession = "Carpenter"

    def test_anchor_lookup_helper(self):
        self.home.anchors = [{"type": "sleep", "x": 2, "y": 3}]
        # Helper should return the anchor coords
        coords = self.home.get_anchor_coordinates("sleep", (5, 5))
        self.assertEqual(coords, (2, 3))

        # Helper should fallback to provided coords if anchor type not found
        coords = self.home.get_anchor_coordinates("eat", (5, 5))
        self.assertEqual(coords, (5, 5))

        # Helper should handle None fallback cleanly
        coords = self.home.get_anchor_coordinates("eat", None)
        self.assertIsNone(coords)

    def test_sleep_behavior_prefers_sleep_anchor(self):
        self.home.anchors = [{"type": "sleep", "x": 2, "y": 3}]
        self.npc.x = 5
        self.npc.y = 5

        # Simulate night time (hour 23)
        current_time_in_day = int(DAY_LENGTH_TICKS * 0.95)

        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        # Should prefer the sleep anchor
        self.assertEqual(self.npc.schedule.current_task, "going_to_bed")
        self.assertEqual(self.npc.schedule.current_destination_coords, (2, 3))

    def test_work_behavior_prefers_work_anchor(self):
        self.workplace.anchors = [{"type": "work", "x": 22, "y": 23}]
        self.npc.x = 5
        self.npc.y = 5
        self.npc.schedule.current_task = "idle"

        # Simulate work time (hour 10)
        current_time_in_day = int(DAY_LENGTH_TICKS * 0.4)

        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        # Should prefer the work anchor
        self.assertEqual(self.npc.schedule.current_task, "going_to_work")
        self.assertEqual(self.npc.schedule.current_destination_coords, (22, 23))

    def test_missing_anchors_fallback_to_existing_behavior(self):
        self.home.anchors = []
        self.workplace.anchors = []
        self.npc.x = 5
        self.npc.y = 5
        self.npc.schedule.current_task = "idle"

        # Work behavior
        current_time_in_day = int(DAY_LENGTH_TICKS * 0.4)
        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        self.assertEqual(self.npc.schedule.current_task, "going_to_work")
        self.assertEqual(self.npc.schedule.current_destination_coords, (25, 25))

        # Sleep behavior
        self.npc.schedule.current_task = "at_home"
        current_time_in_day = int(DAY_LENGTH_TICKS * 0.95)

        # When there is no sleep spot, it checks `world._building_contains_item_with_interaction`, which we mock to False.
        # But it still sets new_task_label = "going_home" to the center, so we check that
        self.npc.x = 0
        self.npc.y = 0
        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        self.assertEqual(self.npc.schedule.current_task, "going_home")
        self.assertEqual(self.npc.schedule.current_destination_coords, (5, 5))

if __name__ == '__main__':
    unittest.main()
