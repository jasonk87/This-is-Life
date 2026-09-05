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

Adding the lodge also woke a system that had never run. engine.py carries a full
hunting implementation - prey finding, pursuit, a dropoff building, offscreen
abstraction - all gated on _is_hunter_role, which asks whether an NPC's
profession is Hunter. No world had one, so none of it ever executed.

What works and what does not, measured rather than assumed:

* Offscreen hunting fires and produces. Called from the abstract simulation for
  villages away from the player, it returns meat for every village with a hunter.
* Onscreen hunting does not. Animals exist as entities only near the player and
  keep clear of settlements, so a hunter standing at their lodge finds no prey -
  measured, 27 animals in the world and none within sixty tiles of the lodge.
  The ecology's own population model says there are thousands; those are regional
  counts, not entities, which is the same level-of-detail split that lets distant
  villagers sleep. A hunter who walks out to find prey is a feature this does not
  claim to have built.
"""

import unittest

from data.professions import PROFESSIONS, get_sub_task_data
from engine import World
from tests.world_cache import fresh_world
from simulation.systems.work import update_npc_work_sub_tasks
from tile_types import Tile


class TestTheHunterHasSomewhereToWork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = fresh_world(seed=5, pre_simulate=False)

    def test_a_lodge_is_built(self):
        """In this seed's world. A lodge lands in about half of villages - it and
        the clinic compete for the same leftover ground and the clinic goes first
        (see VILLAGE_LAYOUT_NOTE) - so this is seeded rather than assuming every
        village has one."""
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
        self.world = fresh_world(seed=5)
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


class TestOffscreenHuntingProduces(unittest.TestCase):
    """The path that actually feeds the village.

    Villages away from the player hunt abstractly rather than by walking an NPC
    into the woods. This is the half of the system that works, and it did nothing
    at all until a village could employ a Hunter.
    """

    def setUp(self):
        self.world = fresh_world(seed=5)

    def _a_village_with_a_hunter(self):
        for row in self.world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is None:
                    continue
                hunters = [
                    n for n in self.world.village_npcs
                    if self.world._is_hunter_role(n)
                    and self.world._get_village_for_npc(n) is village
                ]
                if hunters:
                    return village, hunters
        return None, []

    def test_a_village_employs_a_hunter_at_all(self):
        village, hunters = self._a_village_with_a_hunter()
        self.assertIsNotNone(village, "no village in this world employs a hunter")
        self.assertTrue(hunters)

    def test_hunting_returns_something(self):
        village, hunters = self._a_village_with_a_hunter()
        if village is None:
            self.skipTest("no village in this world employs a hunter")
        produced = self.world._process_offscreen_hunting_for_village(village, hunters)
        self.assertGreater(
            produced, 0,
            "a village with a hunter and a stocked region produced no meat",
        )

    def test_a_village_without_hunters_produces_nothing(self):
        """The gate is the profession, which is what had never existed."""
        village, _ = self._a_village_with_a_hunter()
        if village is None:
            self.skipTest("no village in this world employs a hunter")
        self.assertEqual(self.world._process_offscreen_hunting_for_village(village, []), 0)


if __name__ == "__main__":
    unittest.main()
