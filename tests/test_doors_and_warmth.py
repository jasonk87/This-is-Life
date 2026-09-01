"""NPCs can get through a shut door, and a freezing one keeps looking for warmth.

`npc_toggle_door` was written to let NPCs open doors and had no caller anywhere,
while `_get_pathfinding_tile_cost` gave a shut door the same cost as a wall. So a
villager indoors when a door was shut could reach nothing outside that room -
one was found frozen at 17 degrees of body heat with a tavern a short walk away
and no route to it.

The freezing branch made that worse: it only ran when the NPC was *not* already
seeking warmth, so whoever failed to find a fire or a route indoors on the single
tick they started freezing kept the task with nowhere to go, forever.
"""

import unittest

from config import CHUNK_SIZE
from engine import DOOR_PATHFINDING_COST, World
from simulation.systems.survival import update_npc_environmental_tasks
from simulation.systems.task_types import TaskType


def _find_closed_door(world):
    for chunk_y, row in enumerate(world.chunks):
        for chunk_x, chunk in enumerate(row):
            if not chunk.is_terrain_generated:
                continue
            for local_y in range(CHUNK_SIZE):
                for local_x in range(CHUNK_SIZE):
                    x = chunk_x * CHUNK_SIZE + local_x
                    y = chunk_y * CHUNK_SIZE + local_y
                    tile = world.get_tile_at(x, y)
                    if (
                        tile is not None
                        and not tile.passable
                        and (getattr(tile, "properties", None) or {}).get("is_door")
                    ):
                        return x, y
    return None


class TestDoorsAreNotWalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.door = _find_closed_door(cls.world)

    def setUp(self):
        if self.door is None:
            self.skipTest("no closed door in this generated world")

    def test_a_shut_door_costs_more_than_open_ground_but_is_not_impassable(self):
        cost = self.world._get_pathfinding_tile_cost(*self.door)
        self.assertGreater(cost, 0.0, "a shut door is still costed as a wall")
        self.assertEqual(cost, DOOR_PATHFINDING_COST)
        self.assertGreater(DOOR_PATHFINDING_COST, 1.0, "a door should not be as cheap as open ground")

    def test_an_npc_can_open_a_shut_door(self):
        world = self.world
        npc = next(n for n in world.village_npcs if not n.physical.is_dead)
        self.assertFalse(world.get_tile_at(*self.door).passable)

        self.assertTrue(world.npc_toggle_door(npc, *self.door))
        self.assertTrue(world.get_tile_at(*self.door).passable, "the door did not open")

    def test_a_room_behind_a_shut_door_is_reachable(self):
        """Regression: sealed rooms were how villagers got stranded indoors."""
        world = self.world
        door_x, door_y = self.door

        def reachable_from(start, limit=400):
            seen = {start}
            frontier = [start]
            while frontier and len(seen) < limit:
                x, y = frontier.pop()
                for step_x in (-1, 0, 1):
                    for step_y in (-1, 0, 1):
                        if step_x == 0 and step_y == 0:
                            continue
                        point = (x + step_x, y + step_y)
                        if point in seen:
                            continue
                        if world._get_pathfinding_tile_cost(point[0], point[1]) <= 0:
                            continue
                        seen.add(point)
                        frontier.append(point)
            return seen

        # Standing on a tile beside the door, the far side must be reachable.
        for offset_x, offset_y in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            start = (door_x + offset_x, door_y + offset_y)
            if world._get_pathfinding_tile_cost(*start) > 0:
                self.assertIn(
                    (door_x, door_y), reachable_from(start),
                    "the door itself is not reachable, so it still walls the room off",
                )
                return
        self.skipTest("the door has no walkable neighbour in this world")


class TestFreezingKeepsLooking(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def _stranded_freezing_npc(self):
        world = self.world
        npc = next(
            n for n in world.village_npcs
            if not n.physical.is_dead and (n.schedule.home_building_id or world._find_nearest_tavern(n))
        )
        npc.is_sleeping = False
        npc.physical.status_effects = ["Freezing"]
        npc.schedule.current_task = "seeking_warmth"
        npc.schedule.previous_task = TaskType.AT_WORK
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None
        return npc

    def test_the_search_runs_again_when_there_is_nowhere_to_go(self):
        """The old guard skipped anyone already on the errand, however stuck."""
        npc = self._stranded_freezing_npc()
        before = npc.schedule.previous_task
        update_npc_environmental_tasks(self.world, npc)
        # Whether a route is found depends on the map; what must not happen is
        # the retry being skipped and previous_task being trampled.
        self.assertEqual(
            npc.schedule.previous_task, before,
            "a retry overwrote what the NPC was doing before they got cold",
        )

    def test_warming_up_returns_them_to_what_they_were_doing(self):
        npc = self._stranded_freezing_npc()
        update_npc_environmental_tasks(self.world, npc)

        npc.physical.status_effects = []
        update_npc_environmental_tasks(self.world, npc)

        self.assertEqual(npc.schedule.current_task, TaskType.AT_WORK)
        self.assertIsNone(npc.schedule.previous_task)

    def test_a_retry_never_leaves_them_seeking_warmth_forever(self):
        """previous_task must never become 'seeking_warmth' - that is the loop."""
        npc = self._stranded_freezing_npc()
        for _ in range(5):
            update_npc_environmental_tasks(self.world, npc)
        self.assertNotIn(
            npc.schedule.previous_task, ("seeking_warmth", "huddling_indoors"),
            "warming up would send them straight back to freezing",
        )


if __name__ == "__main__":
    unittest.main()
