import unittest
from unittest.mock import MagicMock

import engine
from engine import NPC, Building, World
from simulation.systems.illness import SICK_STATUS_EFFECT
from simulation.systems.medical import update_npc_medical_state


class TestMedicalTasksExcludedFromWorkOverride(unittest.TestCase):
    """Regression tests for the work-scheduling/medical-task collision:
    update_npc_daily_goal_policy used to unconditionally overwrite
    current_task with GOING_TO_WORK during work hours, even for an NPC
    medical.py had just routed toward treatment, since its exclusion list
    only covered combat tasks. Fixed by adding the medical task labels to
    _run_humanoid_schedule_logic's exclusion list, the same way combat
    tasks are already excluded. Affects both the pre-existing broken_leg
    case and the new "sick" case."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=71)
        # Land squarely inside work hours (WORK_START/END_TIME_RATIO are
        # 0.333/0.708 of DAY_LENGTH_TICKS), well clear of both edges.
        self.world.game_time = int(engine.DAY_LENGTH_TICKS * 0.5)
        self.world.calculate_path = MagicMock(return_value=[(0, 0), (1, 1)])

    def _make_working_npc(self, name, task):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        workplace = Building(5, 5, 5, 5, building_type="general_store", category="commercial_workplace")
        self.world.buildings_by_id[workplace.id] = workplace
        npc.schedule.work_building_id = workplace.id
        npc.schedule.current_task = task
        npc.economic.profession = "Merchant"
        return npc

    def test_seeking_healer_task_is_not_overridden_to_going_to_work(self):
        npc = self._make_working_npc("Patient", "seeking_healer")
        self.world._run_humanoid_schedule_logic(npc)
        self.assertEqual(npc.schedule.current_task, "seeking_healer")

    def test_waiting_for_treatment_task_is_not_overridden(self):
        npc = self._make_working_npc("Patient", "waiting_for_treatment")
        self.world._run_humanoid_schedule_logic(npc)
        self.assertEqual(npc.schedule.current_task, "waiting_for_treatment")

    def test_resting_in_bed_task_is_not_overridden(self):
        npc = self._make_working_npc("Patient", "resting_in_bed")
        self.world._run_humanoid_schedule_logic(npc)
        self.assertEqual(npc.schedule.current_task, "resting_in_bed")

    def test_treating_patient_task_is_not_overridden(self):
        npc = self._make_working_npc("Healer NPC", "treating_patient")
        self.world._run_humanoid_schedule_logic(npc)
        self.assertEqual(npc.schedule.current_task, "treating_patient")

    def test_going_to_work_is_still_assigned_when_not_in_a_medical_task(self):
        # Control case: confirms the exclusion is scoped to medical tasks
        # only, and ordinary work-scheduling still functions for everyone
        # else - this fix should not make NPCs stop going to work in general.
        npc = self._make_working_npc("Healthy Worker", engine.TaskType.IDLE)
        self.world._run_humanoid_schedule_logic(npc)
        self.assertIn(npc.schedule.current_task, ["going_to_work", "at_work"])

    def test_full_sick_npc_pipeline_stays_routed_to_treatment_during_work_hours(self):
        """End-to-end regression: run medical-state assignment and humanoid
        scheduling back to back, exactly the order _update_npc_schedules
        actually calls them in, and confirm a sick NPC doesn't get bounced
        to work mid-routing."""
        npc = self._make_working_npc("Sick Worker", engine.TaskType.IDLE)
        npc.physical.status_effects.append(SICK_STATUS_EFFECT)
        npc.physical.temperature = 37.0

        update_npc_medical_state(self.world, npc)
        self.assertIn(npc.schedule.current_task, ["seeking_healer", "waiting_for_treatment", "resting_in_bed"])

        self.world._run_humanoid_schedule_logic(npc)

        self.assertNotEqual(npc.schedule.current_task, "going_to_work")
        self.assertNotEqual(npc.schedule.current_task, "at_work")

    def test_full_broken_leg_npc_pipeline_stays_routed_to_treatment_during_work_hours(self):
        """Same regression, but for the pre-existing broken_leg case - this
        bug predates the illness system and affected broken_leg from the
        start."""
        npc = self._make_working_npc("Injured Worker", engine.TaskType.IDLE)
        npc.physical.status_effects.append("broken_leg")

        update_npc_medical_state(self.world, npc)
        self.assertIn(npc.schedule.current_task, ["seeking_healer", "waiting_for_treatment", "resting_in_bed"])

        self.world._run_humanoid_schedule_logic(npc)

        self.assertNotEqual(npc.schedule.current_task, "going_to_work")
        self.assertNotEqual(npc.schedule.current_task, "at_work")


if __name__ == "__main__":
    unittest.main()
