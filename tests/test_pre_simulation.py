"""Pre-simulation settling: villagers start the game standing where their routine puts them.

World generation seats a villager on their home building's centre, but villages
generate far more residents than houses, so most fall back to a single
per-village tile and the whole population starts the game in one heap. These
cover the settling pass that undoes that, and the arrival tests it relies on.
"""

import unittest

import main
from config import (
    DAY_LENGTH_TICKS,
    MAP_HEIGHT,
    MAP_WIDTH,
    WORK_END_TIME_RATIO,
    WORK_START_TIME_RATIO,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from engine import Building, World
from entities.base import NPC
from simulation.systems.scheduling import get_work_anchor_coords
from simulation.systems.task_types import TaskType


class TestPreSimulationSettling(unittest.TestCase):
    """End-to-end checks against a real generated world."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.npcs = [npc for npc in cls.world.village_npcs if not npc.physical.is_dead]

    def test_pre_simulation_runs(self):
        """Regression: the pre-sim call site once passed too few arguments and every new game died here."""
        self.assertGreater(len(self.npcs), 0)

    def test_no_two_npcs_share_a_tile(self):
        occupied = {}
        for npc in self.npcs:
            self.assertNotIn(
                (npc.x, npc.y),
                occupied,
                f"{npc.name} is stacked on {occupied.get((npc.x, npc.y))} at {(npc.x, npc.y)}",
            )
            occupied[(npc.x, npc.y)] = npc.name

    def test_every_npc_stands_on_walkable_ground(self):
        for npc in self.npcs:
            tile = self.world.get_tile_at(npc.x, npc.y)
            self.assertIsNotNone(tile, f"{npc.name} is off the map at {(npc.x, npc.y)}")
            self.assertTrue(tile.passable, f"{npc.name} is inside terrain at {(npc.x, npc.y)}")

    def _is_work_time(self) -> bool:
        current_time_in_day = self.world.game_time % DAY_LENGTH_TICKS
        return (
            DAY_LENGTH_TICKS * WORK_START_TIME_RATIO
            <= current_time_in_day
            < DAY_LENGTH_TICKS * WORK_END_TIME_RATIO
        )

    def test_employed_npcs_start_the_workday_at_their_workplace(self):
        if not self._is_work_time():
            self.skipTest("world does not start during working hours")

        employed = [npc for npc in self.npcs if npc.schedule.work_building_id]
        self.assertGreater(len(employed), 0, "generated world has nobody in work")

        at_work = [
            npc
            for npc in employed
            if self.world.buildings_by_id[npc.schedule.work_building_id].contains_global_coords(npc.x, npc.y)
        ]
        # Not all of them: a workplace whose interior is full pushes the
        # overflow outside, which is a fine place for a villager to be.
        self.assertGreaterEqual(
            len(at_work),
            int(len(employed) * 0.75),
            f"only {len(at_work)} of {len(employed)} employed villagers made it to work",
        )

    def test_settling_leaves_npcs_busy_with_something_else_alone(self):
        world = self.world
        npc = self.npcs[0]
        origin = (npc.x, npc.y)
        npc.schedule.current_task = "conversing"

        world._settle_npcs_into_daily_routines()

        self.assertEqual((npc.x, npc.y), origin)
        self.assertEqual(npc.schedule.current_task, "conversing")

    def test_settling_does_not_reshuffle_villagers_who_have_somewhere_to_be(self):
        """A second pass leaves anyone with somewhere to be exactly where the first one put them.

        Only villagers whose anchor is fixed right now count: during working
        hours that is the employed. Everyone else is loitering, and picking a
        fresh spot each pass is the point of loitering.
        """
        world = self.world
        if not self._is_work_time():
            self.skipTest("world does not start during working hours")

        for npc in self.npcs:
            if npc.schedule.current_task not in world.ROUTINE_SETTLE_TASKS:
                npc.schedule.current_task = TaskType.IDLE

        world._settle_npcs_into_daily_routines()
        # Children trail a parent who may themselves shift, so they have no
        # fixed anchor either.
        anchored = [
            npc
            for npc in self.npcs
            if npc.schedule.work_building_id and npc.economic.profession != "Child"
        ]
        self.assertGreater(len(anchored), 0, "generated world has nobody in work")
        before = {npc.id: (npc.x, npc.y) for npc in anchored}

        world._settle_npcs_into_daily_routines()

        for npc in anchored:
            self.assertEqual(
                (npc.x, npc.y),
                before[npc.id],
                f"{npc.name} was shuffled by a repeat settling pass",
            )


class TestVillagerSpawnPositions(unittest.TestCase):
    """Generation itself should not stack villagers, before any settling runs."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.npcs = [npc for npc in cls.world.village_npcs if not npc.physical.is_dead]
        cls.villages = [
            chunk.village
            for row in cls.world.chunks
            for chunk in row
            if getattr(chunk, "village", None)
        ]

    def test_no_two_villagers_spawn_on_one_tile(self):
        occupied = {}
        for npc in self.npcs:
            self.assertNotIn(
                (npc.x, npc.y),
                occupied,
                f"{npc.name} spawned on top of {occupied.get((npc.x, npc.y))}",
            )
            occupied[(npc.x, npc.y)] = npc.name

    def test_nobody_spawns_on_the_player(self):
        player_tile = (self.world.player.x, self.world.player.y)
        on_player = [npc.name for npc in self.npcs if (npc.x, npc.y) == player_tile]
        self.assertEqual(on_player, [], f"{on_player} spawned on the player's tile")

    def test_homeless_villagers_spawn_outside_buildings(self):
        homeless = [npc for npc in self.npcs if not npc.schedule.home_building_id]
        self.assertGreater(len(homeless), 0, "generated world housed everybody")
        for npc in homeless:
            for village in self.villages:
                inside = next(
                    (b for b in village.buildings if b.contains_global_coords(npc.x, npc.y)),
                    None,
                )
                self.assertIsNone(
                    inside,
                    f"{npc.name} has no home but spawned inside a {getattr(inside, 'building_type', '')}",
                )


class TestOffMapLookups(unittest.TestCase):
    """Right-clicking the UI panels used to feed off-map coordinates into the world."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")

    def test_get_building_at_returns_none_off_map(self):
        for x, y in [
            (-1, 0),
            (0, -1),
            (-5, -5),
            (WORLD_WIDTH, 0),
            (0, WORLD_HEIGHT),
            (WORLD_WIDTH + 50, WORLD_HEIGHT + 50),
        ]:
            self.assertIsNone(
                self.world.get_building_at(x, y),
                f"get_building_at({x}, {y}) should be None off the map",
            )

    def test_clicks_outside_the_map_view_are_not_world_clicks(self):
        world = self.world
        # The status panel down the right and the log along the bottom.
        for mouse_x, mouse_y in [(MAP_WIDTH, 0), (MAP_WIDTH + 5, 10), (0, MAP_HEIGHT), (10, MAP_HEIGHT + 3)]:
            world.mouse_x, world.mouse_y = mouse_x, mouse_y
            self.assertFalse(main._is_inside_map_view(world))
        for mouse_x, mouse_y in [(0, 0), (MAP_WIDTH - 1, MAP_HEIGHT - 1), (5, 5)]:
            world.mouse_x, world.mouse_y = mouse_x, mouse_y
            self.assertTrue(main._is_inside_map_view(world))


class TestWorkAnchorCoords(unittest.TestCase):
    def setUp(self):
        self.workplace = Building(20, 20, 6, 6, building_type="workshop")
        self.npc = NPC(0, 0, "Test NPC")
        self.npc.economic.profession = "Carpenter"

    def test_falls_back_to_the_building_centre_without_anchors(self):
        self.workplace.anchors = []
        coords = get_work_anchor_coords(None, self.npc, self.workplace)
        self.assertEqual(
            coords, (self.workplace.global_center_x, self.workplace.global_center_y)
        )

    def test_prefers_the_anchor_matching_the_profession(self):
        self.workplace.anchors = [
            {"type": "work", "x": 21, "y": 21, "tags": {"role": "workbench"}},
            {"type": "work", "x": 24, "y": 24, "tags": {"role": "counter"}},
        ]
        self.npc.economic.profession = "Merchant"
        world = _StubWorld()
        self.assertEqual(get_work_anchor_coords(world, self.npc, self.workplace), (24, 24))

        self.npc.economic.profession = "Carpenter"
        self.assertEqual(get_work_anchor_coords(world, self.npc, self.workplace), (21, 21))


class _StubWorld:
    """Just enough world for anchor scoring and refinement."""

    entity_positions: dict = {}

    def get_tile_at(self, x, y):
        return _PassableTile()


class _PassableTile:
    passable = True


if __name__ == "__main__":
    unittest.main()
