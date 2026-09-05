"""A worker sent somewhere by their own job is not marched back as a truant.

Every production chain in the game begins by fetching something from another
building: the baker's fetch_flour targets the mill, the blacksmith's fetch_ore
the mine, the miller's fetch_wheat the farm. None of them ever completed.

Two systems were fighting. The work sub-task system pathed the NPC out to the
station; update_npc_daily_goal_policy computed is_at_work as "standing inside
the workplace", saw them outside it, and sent them back. Traced tick by tick on
a blacksmith, their entire working life was: ten ticks walking toward the ore,
a flip to GOING_TO_WORK, ten ticks walking back, idle, repeat - forever, without
one sub-task ever completing.

Arriving was not enough on its own either. update_npc_work_sub_tasks only runs
for an NPC whose task is AT_WORK, and a worker who reached an outside station
fell through every branch of the policy to idle - so they stood on the ore
holding a full 120-tick timer that nothing would ever count down, until a social
policy wandered them off.

Measured over 3000 ticks on seed 5, before and after, same world:

    blacksmith   0 -> 25 work steps
    baker        0 -> 32
    miller       0 -> 18
    miner       20 -> 152
    sheriff      0 -> 16

The guard is deliberately narrow. An NPC merely *holding* a sub-task is not on
an errand - a healer carrying an unfinished preparing_salves while the foraging
policy walks them into the woods still needs the ordinary rule to bring them
home. Only two cases count: the work system is driving them to the station, or
they are standing on it.
"""

import unittest

from config import DAY_LENGTH_TICKS, WORK_START_TIME_RATIO
from engine import World
from tests.world_cache import fresh_world
from simulation.systems.scheduling import update_npc_daily_goal_policy
from simulation.systems.task_types import TaskType
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini


class TestAnErrandIsNotTruancy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5)

    def setUp(self):
        self.npc = next(
            n for n in self.world.village_npcs
            if not n.physical.is_dead and n.schedule.work_building_id
        )
        self.building = self.world.buildings_by_id[self.npc.schedule.work_building_id]
        self.npc.is_sleeping = False
        # Mid working hours, so the policy's work branch is the live one.
        self.world.game_time = int(DAY_LENGTH_TICKS * WORK_START_TIME_RATIO) + 600
        self.time_in_day = self.world.game_time % DAY_LENGTH_TICKS

    def _somewhere_outside_the_workplace(self):
        origin_x = self.building.global_origin_x
        origin_y = self.building.global_origin_y
        for radius in range(6, 30):
            for dx, dy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
                spot = (origin_x + dx, origin_y + dy)
                tile = self.world.get_tile_at(*spot)
                if tile is None or not tile.passable:
                    continue
                if self.world.get_building_at(*spot) is self.building:
                    continue
                return spot
        return None

    def test_a_worker_walking_to_an_outside_station_is_left_alone(self):
        station = self._somewhere_outside_the_workplace()
        self.assertIsNotNone(station, "found nowhere outside the workplace to stand")

        # Halfway there, with the work system driving.
        self.world._update_entity_position(
            self.npc, self.building.global_origin_x, self.building.global_origin_y
        )
        self.npc.current_sub_task = "fetch_ore"
        self.npc.sub_task_target_coords = station
        self.npc.schedule.current_task = TaskType.AT_WORK
        self.npc.schedule.current_destination_coords = station

        update_npc_daily_goal_policy(self.world, self.npc, self.time_in_day)

        self.assertNotEqual(
            self.npc.schedule.current_task, TaskType.GOING_TO_WORK,
            "a worker on the way to their own station was sent back to the shop",
        )

    def test_a_worker_standing_at_an_outside_station_counts_as_at_work(self):
        """The work sub-task system only runs for AT_WORK, so this is what lets
        the timer start at all."""
        station = self._somewhere_outside_the_workplace()
        self.assertIsNotNone(station)

        self.world._update_entity_position(self.npc, *station)
        self.npc.current_sub_task = "fetch_ore"
        self.npc.sub_task_target_coords = station
        self.npc.schedule.current_task = "idle"
        self.npc.schedule.current_destination_coords = None

        update_npc_daily_goal_policy(self.world, self.npc, self.time_in_day)

        self.assertEqual(self.npc.schedule.current_task, TaskType.AT_WORK)

    def test_merely_holding_a_sub_task_is_not_an_errand(self):
        """The narrowing that keeps the healer honest: carried off by another
        policy, away from the station, still gets fetched back."""
        station = (self.building.global_origin_x + 1, self.building.global_origin_y + 1)
        wandered = self._somewhere_outside_the_workplace()
        self.assertIsNotNone(wandered)

        self.world._update_entity_position(self.npc, *wandered)
        self.npc.current_sub_task = "preparing_salves"
        self.npc.sub_task_target_coords = station
        self.npc.schedule.current_task = "foraging_for_herbs"
        self.npc.schedule.current_destination_coords = (wandered[0] + 1, wandered[1])

        update_npc_daily_goal_policy(self.world, self.npc, self.time_in_day)

        self.assertEqual(
            self.npc.schedule.current_task, TaskType.GOING_TO_WORK,
            "an NPC wandering with a stale sub-task was treated as working",
        )

    def test_someone_with_no_sub_task_is_still_sent_to_work(self):
        """The ordinary rule has to keep working."""
        wandered = self._somewhere_outside_the_workplace()
        self.assertIsNotNone(wandered)

        self.world._update_entity_position(self.npc, *wandered)
        self.npc.current_sub_task = None
        self.npc.sub_task_target_coords = None
        self.npc.schedule.current_task = "idle"
        self.npc.schedule.current_destination_coords = None

        update_npc_daily_goal_policy(self.world, self.npc, self.time_in_day)

        self.assertEqual(self.npc.schedule.current_task, TaskType.GOING_TO_WORK)


class TestTheProductionTradesActuallyWork(unittest.TestCase):
    """End to end, at the only level that would have caught this.

    No unit test could see it: every piece worked. It needed the two systems
    running together against a real village for long enough that a sub-task
    ought to have finished.
    """

    @classmethod
    def setUpClass(cls):
        from simulation.systems.tick import run_world_tick

        cls.world = fresh_world(seed=5)

        cls.completed = []
        original = cls.world._execute_completed_work_sub_task

        def counting(npc, building, sub_task_id, data, *args, **kwargs):
            cls.completed.append((npc.economic.profession, sub_task_id))
            return original(npc, building, sub_task_id, data, *args, **kwargs)

        cls.world._execute_completed_work_sub_task = counting
        for _ in range(900):
            run_world_tick(cls.world)

    def test_some_work_gets_done_at_all(self):
        self.assertTrue(self.completed, "not one work step completed in 900 ticks")

    def test_a_fetch_step_completes(self):
        """The specific step that could never finish. Any trade's will do - the
        fault was shared by all of them."""
        fetches = [
            (profession, step) for profession, step in self.completed
            if str(step).startswith("fetch_")
        ]
        self.assertTrue(
            fetches,
            "no fetch_* step completed in 900 ticks, which is how every "
            f"production chain begins. Completed instead: "
            f"{sorted({s for _, s in self.completed})}",
        )


if __name__ == "__main__":
    unittest.main()
