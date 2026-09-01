import unittest
from unittest.mock import patch
from types import SimpleNamespace

import config
import engine
from engine import NPC, World, Building
from simulation.careers import (
    get_age_work_performance_ceiling,
    WORK_PERFORMANCE_AGE_DECLINE_START,
    WORK_PERFORMANCE_AGE_DECLINE_END,
    WORK_PERFORMANCE_AGE_FLOOR,
)
from simulation.systems.work import update_npc_work_sub_tasks


class TestAgeWorkPerformanceCeiling(unittest.TestCase):
    """Ideation-audit item 3: age used to affect nothing but the old-age
    death roll (age > 70) and the child/adult sprite split - zero
    productivity effect. get_age_work_performance_ceiling is the new,
    gradual (not a cliff) curve: unaffected through 55, linearly declining
    to a floor of 60 by 80, held there beyond that."""

    def test_young_adult_has_no_ceiling_reduction(self):
        self.assertEqual(get_age_work_performance_ceiling(25), 100)

    def test_exactly_at_decline_start_has_no_reduction_yet(self):
        self.assertEqual(get_age_work_performance_ceiling(WORK_PERFORMANCE_AGE_DECLINE_START), 100)

    def test_midpoint_of_decline_is_roughly_midpoint_of_range(self):
        midpoint_age = (WORK_PERFORMANCE_AGE_DECLINE_START + WORK_PERFORMANCE_AGE_DECLINE_END) // 2
        ceiling = get_age_work_performance_ceiling(midpoint_age)
        expected_midpoint = (100 + WORK_PERFORMANCE_AGE_FLOOR) // 2
        self.assertAlmostEqual(ceiling, expected_midpoint, delta=2)

    def test_at_decline_end_hits_the_floor(self):
        self.assertEqual(get_age_work_performance_ceiling(WORK_PERFORMANCE_AGE_DECLINE_END), WORK_PERFORMANCE_AGE_FLOOR)

    def test_beyond_decline_end_stays_at_floor_not_lower(self):
        self.assertEqual(get_age_work_performance_ceiling(120), WORK_PERFORMANCE_AGE_FLOOR)

    def test_floor_is_safely_above_the_no_pay_and_firing_thresholds(self):
        """Deliberate design constraint: aging alone should never be able to
        talk an elderly NPC out of a paycheck (<=20, _pay_daily_company_wages)
        or into the 10% daily firing chance (<20, _update_npc_careers)."""
        self.assertGreater(WORK_PERFORMANCE_AGE_FLOOR, 20)

    def test_none_age_is_treated_as_unaffected(self):
        """The player has no .age field anywhere in this codebase - None
        must be a safe, no-op input, not a crash or an accidental penalty."""
        self.assertEqual(get_age_work_performance_ceiling(None), 100)

    def test_curve_is_monotonically_non_increasing_with_age(self):
        previous = 100
        for age in range(18, 100):
            ceiling = get_age_work_performance_ceiling(age)
            self.assertLessEqual(ceiling, previous)
            previous = ceiling


class TestAgeCeilingAppliedDuringWork(unittest.TestCase):
    """Integration check that the ceiling is actually wired into the real
    per-tick performance increment in simulation/systems/work.py, following
    the exact two-call sub_task_timer=1 completion pattern established in
    tests/test_hunt_to_table.py's test_hunter_butchering."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=4001)

    def _make_worker(self, age, starting_performance):
        worker = NPC(
            self.world.player.x,
            self.world.player.y,
            name="Worker",
            dialogue=["Hi."],
            personality="villager",
            player_id=self.world.player.id,
        )
        worker.age = age
        worker.economic.profession = "Farmer"
        worker.economic.work_performance = starting_performance
        worker.schedule.work_building_id = "farm_1"
        worker.current_sub_task = "till_soil"
        worker.sub_task_target_coords = (worker.x, worker.y)
        worker.sub_task_timer = 1

        farm = Building(worker.x, worker.y, 5, 5, "farm", "workplace")
        farm.id = "farm_1"
        self.world.buildings_by_id["farm_1"] = farm
        return worker

    def _drive_subtask_to_completion(self, worker):
        with patch("engine.get_sub_task_data") as mock_get_data:
            mock_get_data.return_value = {
                "id": "till_soil",
                "display_name": "Tilling",
                "duration_ticks": 1,
                "target_zone_tag": None,
                "action_verb": "tilling",
            }
            update_npc_work_sub_tasks(self.world, worker)
            update_npc_work_sub_tasks(self.world, worker)

    def test_young_worker_performance_increments_normally(self):
        worker = self._make_worker(age=30, starting_performance=90)

        self._drive_subtask_to_completion(worker)

        self.assertEqual(worker.economic.work_performance, 95)  # 90 + 5, well under 100

    def test_elderly_worker_performance_is_capped_at_their_ceiling(self):
        worker = self._make_worker(age=75, starting_performance=90)
        expected_ceiling = get_age_work_performance_ceiling(75)
        self.assertLess(expected_ceiling, 95)  # sanity: the cap must actually bind here

        self._drive_subtask_to_completion(worker)

        self.assertEqual(worker.economic.work_performance, expected_ceiling)

    def test_elderly_worker_below_their_ceiling_still_gains_normally(self):
        """The ceiling only stops climbing *past* it - an elderly worker
        starting well below their own ceiling still earns the full +5."""
        worker = self._make_worker(age=75, starting_performance=10)

        self._drive_subtask_to_completion(worker)

        self.assertEqual(worker.economic.work_performance, 15)


if __name__ == "__main__":
    unittest.main()
