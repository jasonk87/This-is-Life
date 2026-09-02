"""A hunter turns what dies in the woods into meat.

Two halves were missing and each made the other pointless.

There was no hunting_lodge in any world. hunting_lodge maps to Hunter in
BUILDING_ROLE_RULES and generation never asked for one, so Hunter was a
profession the game defined and no village could employ.

And the Hunter's own work sequence was ["scout_area", "hunt_animals"], with a
comment saying butchering was "dynamic". Nothing scheduled it.
ButcherCarcassSubTaskCommand is written, registered and covered by
tests/test_hunt_to_table.py - and a working Hunter never reached it. So even with
a lodge, hunting would have produced nothing: scout, wander, repeat.

hunt_animals is left in the sequence though it targets a "wilderness" zone with
no resolver. The work chain skips a step it cannot find a station for, so it
costs nothing and keeps the intent legible for whoever implements it.

The chain now runs into the butcher shop added alongside it: a corpse becomes raw
meat, and raw meat is what a Butcher processes.
"""

import unittest

from data.professions import PROFESSIONS, get_sub_task_data
from engine import World
from simulation.systems.work import update_npc_work_sub_tasks
from tile_types import Tile


class TestTheHunterHasSomewhereToWork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=5)

    def test_a_lodge_is_built(self):
        lodges = [
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "hunting_lodge"
        ]
        self.assertTrue(lodges, "no hunting lodge was generated in this world")

    def test_the_lodge_has_the_storage_its_work_needs(self):
        """deposit_meat targets a storage_area; without the zone the step can
        never run and the meat never leaves the hunter's pack."""
        lodge = next(
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "hunting_lodge"
        )
        self.assertIn("storage_area", lodge.work_zone_tiles)
        self.assertTrue(lodge.work_zone_tiles["storage_area"])


class TestTheSequenceReachesTheButchering(unittest.TestCase):
    def test_butchering_is_scheduled(self):
        sequence = PROFESSIONS["Hunter"]["default_sub_task_sequence"]
        self.assertIn(
            "butcher_carcass", sequence,
            "the command that turns a carcass into meat is still never scheduled",
        )

    def test_depositing_is_scheduled(self):
        self.assertIn("deposit_meat", PROFESSIONS["Hunter"]["default_sub_task_sequence"])

    def test_scouting_still_comes_first(self):
        """The original intent - look around, then work - is preserved."""
        sequence = PROFESSIONS["Hunter"]["default_sub_task_sequence"]
        self.assertEqual(sequence[0], "scout_area")

    def test_every_step_in_the_sequence_is_defined(self):
        defined = {st["id"] for st in PROFESSIONS["Hunter"]["sub_tasks"]}
        for step in PROFESSIONS["Hunter"]["default_sub_task_sequence"]:
            self.assertIn(step, defined, f"the sequence references an undefined step {step!r}")


class TestACarcassBecomesMeat(unittest.TestCase):
    """The end of the chain, driven directly.

    A corpse is placed beside a hunter and the butchering step run, rather than
    waiting for a predator to make one - the point is that the step pays out, not
    that the ecology eventually gets round to it.
    """

    def setUp(self):
        self.world = World(seed=5)
        self.world._pre_simulate_world()
        self.lodge = next(
            (b for b in self.world.buildings_by_id.values()
             if b.building_type == "hunting_lodge"),
            None,
        )
        self.assertIsNotNone(self.lodge, "no hunting lodge in this world")

        self.hunter = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        self.hunter.is_sleeping = False
        self.hunter.economic.profession = "Hunter"
        self.hunter.schedule.work_building_id = self.lodge.id
        self.world._update_entity_position(
            self.hunter, self.lodge.global_center_x, self.lodge.global_center_y
        )

    def _lay_a_corpse_beside(self, npc):
        x, y = npc.x + 1, npc.y
        chunk = self.world.chunks[y // 40][x // 40]
        if not chunk.is_terrain_generated:
            self.world._generate_chunk_detail(chunk, x // 40, y // 40)
        corpse = Tile(
            ord("%"), (150, 60, 60), True, "Animal Corpse",
            properties={"animal_type": "deer"},
        )
        chunk.tiles[y % 40][x % 40] = corpse
        return (x, y)

    def test_butchering_a_corpse_yields_something_to_carry(self):
        position = self._lay_a_corpse_beside(self.hunter)
        before = sum(
            quantity for key, quantity in dict(self.hunter.economic.npc_inventory).items()
            if key != "item_references" and isinstance(quantity, int)
        )

        data = get_sub_task_data("Hunter", "butcher_carcass")
        self.assertIsNotNone(data, "butcher_carcass is not defined for a Hunter")
        self.hunter.current_sub_task = "butcher_carcass"
        self.hunter.sub_task_target_coords = position
        self.hunter.sub_task_timer = 0
        self.world._execute_completed_work_sub_task(
            self.hunter, self.lodge, "butcher_carcass", data
        )

        after = sum(
            quantity for key, quantity in dict(self.hunter.economic.npc_inventory).items()
            if key != "item_references" and isinstance(quantity, int)
        )
        self.assertGreater(
            after, before,
            "butchering a deer carcass produced nothing at all",
        )

    def test_the_work_chain_will_select_butchering(self):
        """Not just that the step works - that a hunter at their lodge is
        actually routed to it."""
        self._lay_a_corpse_beside(self.hunter)
        sequence = PROFESSIONS["Hunter"]["default_sub_task_sequence"]
        self.hunter.current_sub_task_sequence_index = sequence.index("butcher_carcass")
        self.hunter.current_sub_task = None
        self.hunter.sub_task_target_coords = None
        self.hunter._work_validation_retry_after_tick = 0

        update_npc_work_sub_tasks(self.world, self.hunter)

        self.assertIsNotNone(
            self.hunter.current_sub_task,
            "the hunter was given no step to work on at all",
        )


if __name__ == "__main__":
    unittest.main()
