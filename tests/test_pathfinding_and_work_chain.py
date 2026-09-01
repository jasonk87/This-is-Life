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

from data.professions import PROFESSIONS
from engine import World


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
    """A profession's sequence has to be a sequence, not its first step on repeat."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

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

        seen = {npc.id: set() for npc in workers}
        for _ in range(900):
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

    def test_the_sequence_index_moves_on_after_a_step_finishes(self):
        """Directly: the next search must not start on the step just completed."""
        world = self.world
        worker = next(
            npc
            for npc in world.village_npcs
            if npc.schedule.work_building_id
            and len(PROFESSIONS.get(npc.economic.profession, {}).get("default_sub_task_sequence", [])) > 1
        )
        sequence = PROFESSIONS[worker.economic.profession]["default_sub_task_sequence"]
        building = world.buildings_by_id[worker.schedule.work_building_id]

        from simulation.systems.work import update_npc_work_sub_tasks

        worker.is_sleeping = False
        world._update_entity_position(worker, building.global_center_x, building.global_center_y)
        worker.current_sub_task_sequence_index = 0
        worker.current_sub_task = sequence[0]
        worker.sub_task_target_coords = (worker.x, worker.y)
        worker.sub_task_timer = 0

        update_npc_work_sub_tasks(world, worker)

        self.assertNotEqual(
            worker.current_sub_task, sequence[0],
            "the completed step was picked again straight away",
        )


if __name__ == "__main__":
    unittest.main()
