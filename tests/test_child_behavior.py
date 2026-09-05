import unittest
from unittest.mock import patch

import config
import engine
from engine import NPC, World
from simulation.systems.scheduling import update_npc_daily_goal_policy
from simulation.world_model import Village
from tests.world_cache import fresh_world


class TestChildFollowsParentDuringWorkHours(unittest.TestCase):
    """Ideation-audit item 4, work-hours half: 'Child' profession NPCs fell
    into build_job_behavior's IdleBehavior bucket (entities/human_behaviors.py)
    with no distinct daily routine, identical to a jobless adult. Per Jason's
    design decision: follow a trackable parent during work hours instead."""

    WORK_TIME = int(config.DAY_LENGTH_TICKS * (config.WORK_START_TIME_RATIO + config.WORK_END_TIME_RATIO) / 2)

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=4001, pre_simulate=False)
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(30, 30)]}
        self.world.chunks[0][0].village = self.village
        self.world.villages = [self.village]

    def _make_npc(self, name, x, y):
        npc = NPC(x, y, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        return npc

    def _make_child(self, x, y, mother=None, father=None):
        child = self._make_npc("Kid", x, y)
        child.age = 6
        child.economic.profession = "Child"
        if mother is not None:
            child.social.family_ties["mother_id"] = mother.id
        if father is not None:
            child.social.family_ties["father_id"] = father.id
        return child

    def test_child_far_from_parent_paths_toward_them(self):
        mother = self._make_npc("Mother", 10, 10)
        self.world.village_npcs.append(mother)
        self.world.npcs.append(mother)
        child = self._make_child(2, 2, mother=mother)
        self.world.village_npcs.append(child)
        self.world.npcs.append(child)
        self.world._mark_entity_positions_dirty()

        update_npc_daily_goal_policy(self.world, child, self.WORK_TIME)

        self.assertEqual(child.schedule.current_task, "following_parent")
        self.assertIsNotNone(child.schedule.current_destination_coords)

    def test_child_close_to_parent_does_not_repath(self):
        mother = self._make_npc("Mother", 10, 10)
        self.world.village_npcs.append(mother)
        self.world.npcs.append(mother)
        child = self._make_child(11, 10, mother=mother)
        self.world.village_npcs.append(child)
        self.world.npcs.append(child)
        self.world._mark_entity_positions_dirty()

        update_npc_daily_goal_policy(self.world, child, self.WORK_TIME)

        self.assertNotEqual(child.schedule.current_task, "following_parent")

    def test_child_with_no_trackable_parent_does_not_crash(self):
        child = self._make_child(2, 2)  # no mother/father set at all
        self.world.village_npcs.append(child)
        self.world.npcs.append(child)
        self.world._mark_entity_positions_dirty()

        # Should not raise, and should not claim to be following a parent.
        update_npc_daily_goal_policy(self.world, child, self.WORK_TIME)
        self.assertNotEqual(child.schedule.current_task, "following_parent")

    def test_child_with_dead_parent_does_not_crash(self):
        mother = self._make_npc("Mother", 10, 10)
        mother.physical.is_dead = True
        self.world.npcs.append(mother)
        child = self._make_child(2, 2, mother=mother)
        self.world.village_npcs.append(child)
        self.world.npcs.append(child)
        self.world._mark_entity_positions_dirty()

        update_npc_daily_goal_policy(self.world, child, self.WORK_TIME)
        self.assertNotEqual(child.schedule.current_task, "following_parent")

    def test_non_child_npc_unaffected_by_child_branch(self):
        farmer = self._make_npc("Farmer", 2, 2)
        farmer.economic.profession = "Farmer"
        self.world.village_npcs.append(farmer)
        self.world.npcs.append(farmer)
        self.world._mark_entity_positions_dirty()

        # Should run the ordinary adult work-hours logic without error and
        # never claim the child-only "following_parent" task label.
        update_npc_daily_goal_policy(self.world, farmer, self.WORK_TIME)
        self.assertNotEqual(farmer.schedule.current_task, "following_parent")


class TestChildPlaysAtTownSquareDuringLeisure(unittest.TestCase):
    """Ideation-audit item 4, leisure half: town-square play during leisure
    hours, mirroring the existing tavern-going idiom."""

    LEISURE_TIME = int(config.DAY_LENGTH_TICKS * (config.WORK_END_TIME_RATIO + 0.85) / 2)

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=4002, pre_simulate=False)
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(30, 30)]}
        self.world.chunks[0][0].village = self.village
        self.world.villages = [self.village]

    def _make_child(self, x, y):
        child = NPC(x, y, name="Kid", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        child.age = 6
        child.economic.profession = "Child"
        child.leisure_timer = 0
        return child

    def test_child_eventually_heads_to_town_square(self):
        child = self._make_child(2, 2)
        self.world.village_npcs.append(child)
        self.world.npcs.append(child)
        self.world._mark_entity_positions_dirty()

        # This test is about the leisure-hours decision, not about whether
        # the generated terrain between the child and the square happens to
        # be walkable. update_npc_daily_goal_policy downgrades any chosen
        # task to "idle_confused" when calculate_path finds no route, so
        # without a stub route the assertion below tests the world
        # generator rather than the child's behaviour - which is exactly
        # how it started failing once real tcod noise replaced the compat
        # shim's flat-terrain stub.
        with patch("random.random", return_value=0.0), \
             patch.object(self.world, "calculate_path", return_value=[(2, 2), (30, 30)]):
            update_npc_daily_goal_policy(self.world, child, self.LEISURE_TIME)

        self.assertEqual(child.schedule.current_task, "playing_at_town_square")
        self.assertEqual(child.schedule.current_destination_coords, (30, 30))

    def test_child_does_not_use_adult_tavern_behavior(self):
        child = self._make_child(2, 2)
        self.world.village_npcs.append(child)
        self.world.npcs.append(child)
        self.world._mark_entity_positions_dirty()

        with patch("random.random", return_value=0.0):
            update_npc_daily_goal_policy(self.world, child, self.LEISURE_TIME)

        self.assertNotEqual(child.schedule.current_task, "going_to_tavern")

    def test_leisure_timer_counts_down_before_repathing(self):
        child = self._make_child(2, 2)
        child.leisure_timer = 5
        self.world.village_npcs.append(child)
        self.world.npcs.append(child)
        self.world._mark_entity_positions_dirty()

        with patch("random.random", return_value=0.0):
            update_npc_daily_goal_policy(self.world, child, self.LEISURE_TIME)

        self.assertEqual(child.leisure_timer, 4)
        self.assertNotEqual(child.schedule.current_task, "playing_at_town_square")


if __name__ == "__main__":
    unittest.main()
