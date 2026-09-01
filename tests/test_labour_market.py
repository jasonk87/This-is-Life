"""A villager who wants work and a village with vacancies can find each other.

A generated world starts with roughly half its residents unemployed and more
open posts than people to fill them, and two thirds of those residents are
dormant at any moment. Nothing connected the two: the job-hopping pass skips
anyone unemployed by design (it compares one job against another), arriving on a
LOOKING_FOR_WORK errand just set the villager back to idle, and dormant
villagers never run the scheduling flow at all.
"""

import unittest

from config import DAY_LENGTH_TICKS
from engine import World


def _unemployed(world):
    return [
        npc
        for npc in world.village_npcs
        if not npc.physical.is_dead and npc.economic.profession.lower() == "unemployed"
    ]


def _open_positions(world):
    positions = 0
    for row in world.chunks:
        for chunk in row:
            village = getattr(chunk, "village", None)
            if village is None:
                continue
            for building in village.buildings:
                if "workplace" in building.category:
                    positions += max(0, building.max_workers - world._count_building_workers(building))
    return positions


class TestWalkInHiring(unittest.TestCase):
    """Arriving at a workshop's door on a job hunt should mean something."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def _a_workplace_with_room(self):
        for row in self.world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is None:
                    continue
                for building in village.buildings:
                    if (
                        "workplace" in building.category
                        and not self.world._is_player_owned_workplace(building)
                        and self.world._count_building_workers(building) < building.max_workers
                    ):
                        return building
        return None

    def test_a_job_seeker_at_the_door_is_taken_on(self):
        building = self._a_workplace_with_room()
        self.assertIsNotNone(building, "generated world has no vacancy to test")
        seeker = _unemployed(self.world)[0]
        seeker.x, seeker.y = building.global_center_x, building.global_center_y

        hired_at = self.world._try_walk_in_hire(seeker)

        self.assertIs(hired_at, building)
        self.assertEqual(seeker.schedule.work_building_id, building.id)
        self.assertNotEqual(seeker.economic.profession.lower(), "unemployed")

    def test_a_full_workshop_turns_them_away(self):
        building = self._a_workplace_with_room()
        self.assertIsNotNone(building)
        # Fill every post.
        for npc in _unemployed(self.world)[: building.max_workers]:
            npc.schedule.work_building_id = building.id
        seeker = _unemployed(self.world)[-1]
        seeker.x, seeker.y = building.global_center_x, building.global_center_y

        self.assertIsNone(self.world._try_walk_in_hire(seeker))

    def test_standing_in_open_country_hires_nobody(self):
        seeker = _unemployed(self.world)[0]
        seeker.x, seeker.y = 1, 1
        self.assertIsNone(self.world._try_walk_in_hire(seeker))


class TestAbstractLabourMarket(unittest.TestCase):
    """Off-screen villages have to fill their own posts; nobody is there to watch."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def test_the_world_starts_with_both_idle_hands_and_open_posts(self):
        self.assertGreater(len(_unemployed(self.world)), 0)
        self.assertGreater(_open_positions(self.world), 0)

    def test_a_dormant_villager_can_be_matched_to_a_post(self):
        dormant = [
            npc for npc in _unemployed(self.world) if getattr(npc, "is_sleeping", False)
        ]
        self.assertGreater(len(dormant), 0, "no dormant job-seekers in this world")
        matched = [npc for npc in dormant if self.world._find_open_post_for(npc) is not None]
        self.assertGreater(len(matched), 0, "no dormant job-seeker could reach any vacancy")

    def test_a_post_is_never_double_filled(self):
        seeker = _unemployed(self.world)[0]
        building = self.world._find_open_post_for(seeker)
        self.assertIsNotNone(building)
        before = self.world._count_building_workers(building)
        self.world._assign_job(seeker, building, reason="test")
        self.assertEqual(self.world._count_building_workers(building), before + 1)

    def test_unemployment_falls_over_a_working_day(self):
        """Driven through the abstract pass directly - grinding 3600 world ticks
        to watch an hourly job market is minutes of test time for the same answer."""
        world = self.world
        before = len(_unemployed(world))
        self.assertGreater(before, 0)

        ticks_per_hour = max(1, DAY_LENGTH_TICKS // 24)
        for _ in range(8):
            world.game_time += ticks_per_hour
            self.assertTrue(world._is_sleeping_work_hour(), "stepped outside working hours")
            world.process_abstract_simulation()

        after = len(_unemployed(world))
        self.assertLess(
            after, before,
            f"unemployment did not move across a working day ({before} -> {after})",
        )

    def test_nobody_is_hired_outside_working_hours(self):
        world = World(player_first_name="Tester")
        world._pre_simulate_world()
        # Step to the middle of the night.
        world.game_time = (world.game_time // DAY_LENGTH_TICKS + 1) * DAY_LENGTH_TICKS
        self.assertFalse(world._is_sleeping_work_hour())
        before = len(_unemployed(world))

        ticks_per_hour = max(1, DAY_LENGTH_TICKS // 24)
        for _ in range(4):
            world.game_time += ticks_per_hour
            world.process_abstract_simulation()

        self.assertEqual(len(_unemployed(world)), before, "villagers were hired at night")


if __name__ == "__main__":
    unittest.main()
