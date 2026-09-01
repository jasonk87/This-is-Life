"""Two whole-world faults that only showed up in the parts of the map nobody tests.

* `transparency_map` is (WORLD_HEIGHT, WORLD_WIDTH), and seven of the nine
  writes to it index [y, x]. The two in tree growth used [x, y]: they marked the
  wrong tile opaque, and threw IndexError outright once a tree matured at an x
  past WORLD_HEIGHT - the right third of the map. Trees mature on a timer, so
  this fired during ordinary play with no player action at all.

* Arriving at a village noticeboard was tested as exact equality with its single
  tile. Only one villager fits there, so everyone else queued beside it, had
  their path dropped by the occupancy check in _update_npc_movement, and kept a
  task nothing ever cleared. It grew to nearly 12% of everything the population
  was doing.
"""

import unittest

import numpy as np

from config import CHUNK_SIZE, WORLD_HEIGHT, WORLD_WIDTH
from engine import World
from simulation.systems.task_types import TaskType


class TestTransparencyMapIndexing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")

    def test_the_map_is_shaped_height_by_width(self):
        self.assertEqual(self.world.transparency_map.shape, (WORLD_HEIGHT, WORLD_WIDTH))

    def test_every_world_coordinate_is_writable_as_y_x(self):
        for x in (0, WORLD_HEIGHT - 1, WORLD_HEIGHT, WORLD_WIDTH - 1):
            for y in (0, WORLD_HEIGHT - 1):
                with self.subTest(x=x, y=y):
                    self.world.transparency_map[y, x] = True

    def test_the_transposed_order_is_what_used_to_crash(self):
        """Pins the diagnosis: past WORLD_HEIGHT, [x, y] runs off the first axis."""
        self.assertGreater(WORLD_WIDTH, WORLD_HEIGHT, "this test's premise is stale")
        with self.assertRaises(IndexError):
            self.world.transparency_map[WORLD_WIDTH - 1, 0] = True

    def test_a_tree_maturing_in_the_right_hand_map_columns_does_not_crash(self):
        """The tree-growth path is what hit this in play."""
        world = self.world
        planted = 0
        for chunk_y, row in enumerate(world.chunks):
            for chunk_x, chunk in enumerate(row):
                if not chunk.is_terrain_generated or not chunk.tiles:
                    continue
                if chunk_x * CHUNK_SIZE < WORLD_HEIGHT:
                    continue  # only the columns the old order could not address
                for local_y in range(CHUNK_SIZE):
                    for local_x in range(CHUNK_SIZE):
                        tile = chunk.tiles[local_y][local_x]
                        if tile is None or not getattr(tile, "properties", None):
                            continue
                        tile.name = "Sapling"
                        tile.properties["growth_timer"] = 1
                        tile.properties["evolves_to"] = "oak"
                        planted += 1
                        if planted >= 3:
                            break
                    if planted >= 3:
                        break
            if planted >= 3:
                break

        if not planted:
            self.skipTest("no generated chunk past WORLD_HEIGHT in this world")
        world._update_world_environment()


class TestNoticeboardErrandTerminates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def _village_with_a_board(self):
        for row in self.world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is None:
                    continue
                points = (getattr(village, "interaction_points", {}) or {}).get("noticeboard") or []
                if points:
                    return village, points[0]
        return None, None

    def test_standing_beside_the_board_counts_as_reading_it(self):
        village, board = self._village_with_a_board()
        if board is None:
            self.skipTest("no noticeboard in this generated world")
        world = self.world
        seeker = next(
            (npc for npc in world.village_npcs
             if not npc.physical.is_dead and npc.economic.profession.lower() == "unemployed"),
            None,
        )
        if seeker is None:
            self.skipTest("no job seeker in this generated world")

        seeker.is_sleeping = False
        # One tile diagonally off the board - a tile a second reader would take.
        world._update_entity_position(seeker, board[0] + 1, board[1] + 1)
        seeker.schedule.current_task = "reviewing_noticeboard_jobs"
        seeker.schedule.current_destination_coords = board
        seeker.schedule.current_path = []

        world.handle_npc_job_seeking(seeker)

        self.assertNotEqual(
            seeker.schedule.current_task, "reviewing_noticeboard_jobs",
            "a villager beside the board is still queueing to reach it",
        )

    def test_an_errand_with_no_route_left_is_given_up(self):
        village, board = self._village_with_a_board()
        if board is None:
            self.skipTest("no noticeboard in this generated world")
        world = self.world
        seeker = next(
            (npc for npc in world.village_npcs
             if not npc.physical.is_dead and npc.economic.profession.lower() == "unemployed"),
            None,
        )
        if seeker is None:
            self.skipTest("no job seeker in this generated world")

        seeker.is_sleeping = False
        world._update_entity_position(seeker, board[0], board[1] + 6)
        seeker.schedule.current_task = "reviewing_noticeboard_jobs"
        seeker.schedule.current_destination_coords = board
        seeker.schedule.current_path = []

        world.handle_npc_job_seeking(seeker)

        self.assertEqual(
            seeker.schedule.current_task, TaskType.IDLE,
            "a villager whose route to the board is gone kept holding the errand",
        )


if __name__ == "__main__":
    unittest.main()
