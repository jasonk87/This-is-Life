import unittest
from engine import Building
from simulation.systems.scheduling import update_npc_daily_goal_policy
from config import DAY_LENGTH_TICKS
from entities.base import NPC
from unittest.mock import MagicMock

class MockTile:
    def __init__(self, passable=True):
        self.passable = passable

class MockWorld:
    def __init__(self):
        self.buildings_by_id = {}
        self.entity_positions = {}
        self.village_npcs = []

    def _get_building_global_center_coords(self, building_id):
        building = self.buildings_by_id.get(building_id)
        if building:
            return (building.global_center_x, building.global_center_y)
        return None

    def _building_contains_item_with_interaction(self, building, interaction):
        return False

    def calculate_path(self, start_x, start_y, end_x, end_y):
        return [(start_x, start_y), (end_x, end_y)]

    def get_tile_at(self, x, y):
        return MockTile(passable=True)

    def _find_nearest_tavern(self, npc):
        return None

    def _get_village_for_npc(self, npc):
        return None

    def _start_npc_socialization(self, npc):
        return None

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

    def test_anchor_preference_scoring(self):
        # Setup multiple anchors of same type but different roles
        self.workplace.anchors = [
            {"type": "work", "x": 21, "y": 21, "tags": {"role": "desk"}},
            {"type": "work", "x": 23, "y": 23, "tags": {"role": "workbench"}},
        ]

        # A scribe should prefer the desk
        self.npc.economic.profession = "Scribe"
        self.npc.x = 25
        self.npc.y = 25
        coords = self.workplace.get_anchor_coordinates("work", world=self.world, requesting_entity=self.npc, ideal_role="desk")
        self.assertEqual(coords, (21, 21))

        # A carpenter should prefer the workbench
        self.npc.economic.profession = "Carpenter"
        coords = self.workplace.get_anchor_coordinates("work", world=self.world, requesting_entity=self.npc, ideal_role="workbench")
        self.assertEqual(coords, (23, 23))

        # If neither ideal role matches, it should just pick the closest or first valid one
        self.npc.economic.profession = "Unemployed"
        self.npc.x = 24
        self.npc.y = 24
        coords = self.workplace.get_anchor_coordinates("work", world=self.world, requesting_entity=self.npc)
        # Because (23,23) is closer to (24,24) than (21,21), proximity scoring should pick it
        self.assertEqual(coords, (23, 23))

    def test_correct_role_beats_closer_incorrect_role(self):
        self.workplace.anchors = [
            {"type": "work", "x": 24, "y": 25, "tags": {"role": "desk"}},
            {"type": "work", "x": 31, "y": 31, "tags": {"role": "workbench"}},
        ]
        self.npc.x = 25
        self.npc.y = 25

        coords = self.workplace.get_anchor_coordinates(
            "work",
            world=self.world,
            requesting_entity=self.npc,
            ideal_role="workbench",
        )

        self.assertEqual(coords, (31, 31))

    def test_proximity_breaks_ties_between_similar_anchors(self):
        self.workplace.anchors = [
            {"type": "work", "x": 21, "y": 21, "tags": {"role": "workbench"}},
            {"type": "work", "x": 24, "y": 24, "tags": {"role": "workbench"}},
        ]
        self.npc.x = 25
        self.npc.y = 25

        coords = self.workplace.get_anchor_coordinates(
            "work",
            world=self.world,
            requesting_entity=self.npc,
            ideal_role="workbench",
        )

        self.assertEqual(coords, (24, 24))

    def test_anchor_occupancy_penalty(self):
        self.workplace.anchors = [
            {"type": "work", "x": 21, "y": 21, "tags": {"role": "workbench"}},
            {"type": "work", "x": 23, "y": 23, "tags": {"role": "workbench"}},
        ]

        # NPC is closest to 23, 23
        self.npc.x = 24
        self.npc.y = 24

        # But 23, 23 is occupied
        self.world.entity_positions[(23, 23)] = 999

        coords = self.workplace.get_anchor_coordinates("work", world=self.world, requesting_entity=self.npc, ideal_role="workbench")
        # Should pick the further, but unoccupied anchor
        self.assertEqual(coords, (21, 21))

    def test_occupied_best_role_anchor_still_returns_safe_choice(self):
        self.workplace.anchors = [
            {"type": "work", "x": 26, "y": 25, "tags": {"role": "desk"}},
            {"type": "work", "x": 40, "y": 40, "tags": {"role": "workbench"}},
        ]
        self.npc.x = 25
        self.npc.y = 25
        self.world.entity_positions[(40, 40)] = 999

        coords = self.workplace.get_anchor_coordinates(
            "work",
            world=self.world,
            requesting_entity=self.npc,
            ideal_role="workbench",
        )

        self.assertEqual(coords, (40, 40))

    def test_sleep_behavior_prefers_sleep_anchor(self):
        self.home.anchors = [{"type": "sleep", "x": 2, "y": 3}]
        self.npc.x = 5
        self.npc.y = 5

        # Simulate night time (hour 23)
        current_time_in_day = int(DAY_LENGTH_TICKS * 0.95)

        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        # Should prefer the sleep anchor (could be slightly refined if the tile is occupied, but here it's empty and passable)
        self.assertEqual(self.npc.schedule.current_task, "going_to_bed")
        self.assertEqual(self.npc.schedule.current_destination_coords, (2, 3))

    def test_anchor_target_refinement(self):
        # Anchor is at (2, 3) but let's say it's occupied
        self.home.anchors = [{"type": "sleep", "x": 2, "y": 3}]
        self.npc.x = 5
        self.npc.y = 5

        self.world.entity_positions[(2, 3)] = 999  # Occupied by some entity ID 999

        # Simulate night time (hour 23)
        current_time_in_day = int(DAY_LENGTH_TICKS * 0.95)

        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        self.assertEqual(self.npc.schedule.current_task, "going_to_bed")
        # The exact anchor is occupied, so the refined coords should be an adjacent tile.
        # Since all adjacent are empty and passable in MockWorld, it should pick one like (2, 2) or (3, 3) etc.
        # The important thing is it's NOT (2, 3) anymore, but within radius 1 of it.
        dest_x, dest_y = self.npc.schedule.current_destination_coords
        self.assertNotEqual((dest_x, dest_y), (2, 3))
        self.assertTrue(abs(dest_x - 2) <= 1 and abs(dest_y - 3) <= 1)

    def test_anchor_target_refinement_ignores_self(self):
        # Anchor is at (2, 3) and the NPC is already standing on it
        self.home.anchors = [{"type": "sleep", "x": 2, "y": 3}]
        self.npc.x = 2
        self.npc.y = 3

        # Update center to (2, 3) so that `is_at_home` becomes True
        self.home.global_center_x = 2
        self.home.global_center_y = 3

        self.world.entity_positions[(2, 3)] = self.npc.id  # Occupied by the NPC themselves

        # Simulate night time
        current_time_in_day = int(DAY_LENGTH_TICKS * 0.95)

        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        # Since `is_at_home` is True, and `(npc.x, npc.y) == sleep_spot_coords`, the task should be "sleeping"
        self.assertEqual(self.npc.schedule.current_task, "sleeping")

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

    def test_work_behavior_prefers_role_anchor_over_closer_wrong_role(self):
        self.workplace.anchors = [
            {"type": "work", "x": 21, "y": 21, "tags": {"role": "desk"}},
            {"type": "work", "x": 28, "y": 28, "tags": {"role": "workbench"}},
        ]
        self.npc.x = 5
        self.npc.y = 5
        self.npc.schedule.current_task = "idle"

        current_time_in_day = int(DAY_LENGTH_TICKS * 0.4)

        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        self.assertEqual(self.npc.schedule.current_task, "going_to_work")
        self.assertEqual(self.npc.schedule.current_destination_coords, (28, 28))

    def test_at_home_does_not_randomly_drift_to_social_anchor(self):
        import random
        random.seed(42) # stabilize the test to prevent the 1% chance of courting happening
        self.home.anchors = [
            {"type": "social", "x": 4, "y": 4},
            {"type": "eat", "x": 6, "y": 6},
        ]
        self.home.global_center_x = 5
        self.home.global_center_y = 5
        self.npc.x = 5
        self.npc.y = 5
        self.npc.schedule.current_task = "at_home"
        self.npc.leisure_timer = 0

        current_time_in_day = int(DAY_LENGTH_TICKS * 0.75)

        update_npc_daily_goal_policy(self.world, self.npc, current_time_in_day)

        self.assertEqual(self.npc.schedule.current_task, "at_home")
        self.assertIsNone(self.npc.schedule.current_destination_coords)

    def test_anchor_selection_is_deterministic(self):
        self.workplace.anchors = [
            {"type": "work", "x": 24, "y": 24, "tags": {"role": "workbench"}},
            {"type": "work", "x": 29, "y": 29, "tags": {"role": "workbench"}},
            {"type": "work", "x": 21, "y": 21, "tags": {"role": "desk"}},
        ]
        self.npc.x = 25
        self.npc.y = 25

        first = self.workplace.get_anchor_coordinates(
            "work",
            world=self.world,
            requesting_entity=self.npc,
            ideal_role="workbench",
        )
        second = self.workplace.get_anchor_coordinates(
            "work",
            world=self.world,
            requesting_entity=self.npc,
            ideal_role="workbench",
        )

        self.assertEqual(first, second)

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
