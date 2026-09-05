"""Walkers reach where they were sent, and workers get past the first step of a job.

Three faults compounded here, and each hid the next:

* `calculate_path` passed (x, y) to a tcod AStar built over a cost array indexed
  [y, x], so every path came back transposed - a request to step east returned a
  path south. Diagonal moves are symmetric under a transpose and survived it,
  which is why NPCs still moved convincingly while never landing on an
  orthogonal target.
* The returned path omitted the walker's own tile, though `_update_npc_movement`
  reads from index 1 ("Path index 0 is current pos"), main.py pops index 0 when
  it matches, and the test doubles return [start, end]. Every path lost its
  first step, and a one-step path never moved anyone at all.
* A finished work sub-task did not advance the sequence index, and the search
  for the next one starts at that index - so a step that was still viable was
  simply re-selected. A profession's opening step (fetching, tending) consumes
  nothing and so is always viable: blacksmiths fetched ore forever and never
  smelted it.
"""

import unittest

from data.professions import PROFESSIONS, get_sub_task_data
from engine import World
from tests.world_cache import fresh_world
from simulation.systems.work import update_npc_work_sub_tasks
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini


class TestPathGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.centre = cls._find_open_block()

    @classmethod
    def _find_open_block(cls, radius=2):
        """A tile with `radius` of clear ground round it, so geometry is unambiguous."""
        world = cls.world
        player_x, player_y = world.player.x, world.player.y
        for search in range(3, 80):
            for offset_x in range(-search, search + 1):
                for offset_y in (-search, search):
                    x, y = player_x + offset_x, player_y + offset_y
                    if all(
                        (lambda tile: tile is not None and tile.passable)(world.get_tile_at(x + dx, y + dy))
                        for dy in range(-radius, radius + 1)
                        for dx in range(-radius, radius + 1)
                    ):
                        return x, y
        return None

    def setUp(self):
        if self.centre is None:
            self.skipTest("no open ground in this generated world")

    def test_a_path_ends_where_it_was_asked_to_go(self):
        x, y = self.centre
        for label, goal in (
            ("east", (x + 1, y)),
            ("west", (x - 1, y)),
            ("south", (x, y + 1)),
            ("north", (x, y - 1)),
            ("two east", (x + 2, y)),
            ("two south", (x, y + 2)),
            ("diagonal", (x + 1, y + 1)),
            ("two diagonal", (x + 2, y + 2)),
        ):
            with self.subTest(direction=label):
                path = self.world.calculate_path(x, y, goal[0], goal[1])
                self.assertTrue(path, f"no path {label}")
                self.assertEqual(path[-1], goal, f"path {label} ended at {path[-1]}")

    def test_a_path_starts_on_the_walkers_own_tile(self):
        """_update_npc_movement reads from index 1, so index 0 must be where they stand."""
        x, y = self.centre
        path = self.world.calculate_path(x, y, x + 2, y)
        self.assertEqual(path[0], (x, y))

    def test_a_one_step_path_has_something_to_step_to(self):
        """A path of length 1 is 'already there' to the mover, so it must be length 2."""
        x, y = self.centre
        path = self.world.calculate_path(x, y, x + 1, y)
        self.assertGreater(len(path), 1, "a one-tile move produced a path with no step in it")

    def test_every_step_is_adjacent_to_the_last(self):
        x, y = self.centre
        path = self.world.calculate_path(x, y, x + 2, y + 2)
        for previous, current in zip(path, path[1:]):
            self.assertLessEqual(
                max(abs(current[0] - previous[0]), abs(current[1] - previous[1])), 1,
                f"path jumps from {previous} to {current}",
            )

    def test_asking_to_stand_still_is_not_an_error(self):
        x, y = self.centre
        self.assertEqual(self.world.calculate_path(x, y, x, y), [(x, y)])


class TestWorkChainAdvances(unittest.TestCase):
    """A profession's sequence has to be a sequence, not its first step on repeat.

    A world per test, deliberately. These shared one, and the first test below
    runs nine hundred world updates on it - so by the time the second test picked
    a worker, that worker had been through most of a working day and might have
    changed job, gone home or died. It failed about one run in six for reasons
    that had nothing to do with what it checks.
    """

    # Seeded. Now that a seeded world is reproducible (see
    # test_simulation_determinism) a test can pick one where its precondition
    # actually holds, instead of generating a fresh village each run and skipping
    # whenever that village has no workplace with a reachable second station.
    SEED = 1

    def setUp(self):
        self.world = fresh_world(seed=self.SEED)

    def test_a_worker_runs_more_than_the_opening_step(self):
        world = self.world
        workers = [
            npc
            for npc in world.village_npcs
            if not npc.physical.is_dead
            and npc.schedule.work_building_id
            and len(PROFESSIONS.get(npc.economic.profession, {}).get("default_sub_task_sequence", [])) > 1
        ]
        self.assertGreater(len(workers), 0, "generated world has no multi-step workers")

        # Put them at their workplace so the run is about the chain, not the walk.
        for npc in workers:
            building = world.buildings_by_id.get(npc.schedule.work_building_id)
            if building is not None:
                npc.is_sleeping = False
                world._update_entity_position(npc, building.global_center_x, building.global_center_y)

        # Four hundred updates rather than nine hundred: measured, the first
        # workers reach a second step by 200, and the extra five hundred were
        # costing the suite a minute to confirm what it already knew.
        seen = {npc.id: set() for npc in workers}
        for _ in range(400):
            world.update()
            for npc in workers:
                sub_task = getattr(npc, "current_sub_task", None)
                if sub_task:
                    seen[npc.id].add(sub_task)

        advanced = [npc_id for npc_id, tasks in seen.items() if len(tasks) > 1]
        self.assertTrue(
            advanced,
            "no worker got past the first step of its job: "
            + str({npc.economic.profession: sorted(seen[npc.id]) for npc in workers if seen[npc.id]}),
        )

    def _ready_worker(self, world):
        """A non-owner worker with a multi-step job, standing at their workplace.

        Not an owner: update_npc_work_sub_tasks injects management steps for an
        owner who has staff, which is a different path with its own cursor rules.
        """
        worker = next(
            npc
            for npc in world.village_npcs
            if not npc.physical.is_dead
            and npc.schedule.work_building_id in world.buildings_by_id
            and getattr(world.buildings_by_id[npc.schedule.work_building_id], "owner_id", None) != npc.id
            and len(PROFESSIONS.get(npc.economic.profession, {}).get("default_sub_task_sequence", [])) > 1
        )
        building = world.buildings_by_id[worker.schedule.work_building_id]
        sequence = PROFESSIONS[worker.economic.profession]["default_sub_task_sequence"]

        worker.is_sleeping = False
        world._update_entity_position(worker, building.global_center_x, building.global_center_y)
        worker.current_sub_task_sequence_index = 0
        worker.current_sub_task = sequence[0]
        worker.sub_task_target_coords = (worker.x, worker.y)
        worker.sub_task_timer = 0
        # The first thing update_npc_work_sub_tasks does is return early if this
        # worker is inside a validation back-off window, and whether one is
        # pending depends on what pre-simulation did. Left to chance it decided
        # the result about one run in six.
        worker._work_validation_retry_after_tick = 0
        return worker, building, sequence

    def test_the_cursor_steps_past_a_finished_step_when_another_one_can_run(self):
        """The actual contract, which is narrower than it first looks.

        Finishing a step advances the cursor past it, and the search then walks
        forward for a step that can actually run. It does NOT promise to leave
        the finished step - if nothing else is viable it comes back round, which
        is correct and is the test below. An earlier version of this asserted the
        cursor simply must not be 0 afterwards, and failed about one run in seven
        on a Farmer whose farm had nothing to work with.
        """
        world = self.world
        worker, building, sequence = self._ready_worker(world)

        # Stock the workplace with everything every step consumes, so viability
        # is decided by the sequence rather than by what this village happens to
        # have in store.
        for task_id in sequence:
            data = get_sub_task_data(worker.economic.profession, task_id) or {}
            for item_key, needed in (data.get("consumes_item_from_workplace", {}) or {}).items():
                building.building_inventory[item_key] = int(needed) + 10

        others_runnable = [
            task_id for task_id in sequence[1:]
            if world._find_target_coords_for_sub_task(
                worker, building, get_sub_task_data(worker.economic.profession, task_id) or {}
            )
        ]
        if not others_runnable:
            self.skipTest(
                f"no step after the first has a reachable station in this "
                f"{building.building_type} - nothing to advance to"
            )

        update_npc_work_sub_tasks(world, worker)

        self.assertNotEqual(
            worker.current_sub_task_sequence_index, 0,
            f"finished step 0 of {len(sequence)} with {others_runnable} runnable, "
            f"and the cursor stayed on the step just completed "
            f"({worker.economic.profession})",
        )

    def test_the_cursor_comes_back_round_when_nothing_else_can_run(self):
        """The other half of the contract, stated so it is not mistaken for the bug.

        A worker whose workplace cannot supply any later step should repeat the
        one step it can do, not stall. Stepping past the finished step is about
        where the *search* starts, not a promise to never return to it.
        """
        world = self.world
        worker, building, sequence = self._ready_worker(world)

        for task_id in sequence[1:]:
            data = get_sub_task_data(worker.economic.profession, task_id) or {}
            for item_key in (data.get("consumes_item_from_workplace", {}) or {}):
                building.building_inventory.pop(item_key, None)

        update_npc_work_sub_tasks(world, worker)

        self.assertIsNotNone(
            worker.current_sub_task_sequence_index,
            "the worker was left with no cursor at all",
        )
        self.assertIn(
            worker.current_sub_task_sequence_index, range(len(sequence)),
            "the cursor left the sequence entirely",
        )


if __name__ == "__main__":
    unittest.main()
