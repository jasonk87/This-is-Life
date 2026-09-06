"""What a villager does in the rain when there is nowhere to go.

`update_npc_environmental_tasks` used to set `current_task = "seeking_shelter"`
first and look for somewhere to shelter afterwards. When it found nothing - no
home assigned, no tavern built - the villager was left in that task with an empty
path and no destination, and the branch that would have reconsidered is guarded on
*not already being* in "seeking_shelter". So they stood still until the weather
changed: not working, not eating, and not building the shelter they were missing.

It took a settlement without a tavern to see it, which is exactly the settlement
that most needs its people to keep working. The sandbox's
workshop_transformation_runtime_soak sat at zero progress for two thousand ticks
with its one worker frozen in a field.

The freezing branch a few lines above always had this right: it commits to
"huddling_indoors" only once it has a path. This pins both halves - do not latch
without a destination, and do still go inside when there is somewhere to go - so
the fix cannot be mistaken for "stop sheltering".
"""

import unittest
import unittest.mock

from engine import NPC
from simulation.systems.survival import update_npc_environmental_tasks
from tests.world_cache import fresh_world


def _unsheltered_worker(world, x=6, y=5):
    npc = NPC(x, y, name="Rained On")
    npc.economic.profession = "Laborer"
    npc.schedule.home_building_id = None
    world.village_npcs.append(npc)
    return npc


class TestNowhereToShelter(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=4242, pre_simulate=False)
        self.world.weather = "rain"

    def test_a_villager_with_no_home_and_no_tavern_keeps_their_task(self):
        npc = _unsheltered_worker(self.world)
        npc.schedule.current_task = "working"

        with unittest.mock.patch.object(self.world, "_find_nearest_tavern", return_value=None), \
             unittest.mock.patch.object(self.world, "_check_for_shelter", return_value=False), \
             unittest.mock.patch.object(self.world, "get_building_at", return_value=None):
            for _ in range(50):
                update_npc_environmental_tasks(self.world, npc)

        self.assertNotEqual(
            npc.schedule.current_task, "seeking_shelter",
            "latched into seeking_shelter with nowhere to seek",
        )

    def test_it_never_latches_without_a_destination(self):
        """The precise failure: the task set, the path empty, nothing to re-evaluate."""
        npc = _unsheltered_worker(self.world)
        npc.schedule.current_task = "working"

        with unittest.mock.patch.object(self.world, "_find_nearest_tavern", return_value=None), \
             unittest.mock.patch.object(self.world, "_check_for_shelter", return_value=False), \
             unittest.mock.patch.object(self.world, "get_building_at", return_value=None):
            update_npc_environmental_tasks(self.world, npc)

        latched_nowhere = (
            npc.schedule.current_task == "seeking_shelter"
            and not npc.schedule.current_path
            and npc.schedule.current_destination_coords is None
        )
        self.assertFalse(latched_nowhere,
                         "seeking_shelter with no path and no destination is the livelock")


class TestThereIsSomewhereToShelter(unittest.TestCase):
    """The other half. A fix that simply stopped sheltering would pass the above."""

    def test_a_villager_with_a_reachable_home_still_goes_inside(self):
        # Pre-simulated on purpose: pathfinding needs generated chunks, and in a
        # world built with pre_simulate=False calculate_path returns nothing even
        # for a tile three steps away. An earlier version of this test used one
        # and "proved" that the fix had stopped villagers sheltering at all.
        world = fresh_world(seed=4242)
        world.weather = "rain"

        npc = next((n for n in world.village_npcs
                    if getattr(n.schedule, "home_building_id", None)
                    and world.buildings_by_id.get(n.schedule.home_building_id)), None)
        self.assertIsNotNone(npc, "no villager in this world has a home")
        npc.schedule.current_task = "working"
        npc.schedule.current_path = []
        npc.schedule.current_destination_coords = None

        with unittest.mock.patch.object(world, "_check_for_shelter", return_value=False), \
             unittest.mock.patch.object(world, "get_building_at", return_value=None):
            update_npc_environmental_tasks(world, npc)

        self.assertEqual(npc.schedule.current_task, "seeking_shelter")
        self.assertTrue(npc.schedule.current_path, "went seeking shelter with no path")
        self.assertIsNotNone(npc.schedule.current_destination_coords)


if __name__ == "__main__":
    unittest.main()
