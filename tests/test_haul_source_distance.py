"""A villager fetches from the village, not from the other side of the world.

`_find_nearest_haul_source` searched three tiers - stockpiles, then loose items,
then building inventories - and sorted by distance with no upper bound. In a
village that has run out of something, every local tier comes back empty and the
search falls through to every building on the map. It then picks the closest of
those, which in a ten-by-ten chunk world can be a lumber mill in another
settlement 190 tiles away.

That is not a slow haul; it is a permanently stuck one. The worker is handed a
destination outside the loaded chunks, `get_tile_at` returns None for it,
`_update_npc_movement` reads that as impassable and drops the path, and the
villager stands still. The production task that wanted the item reports
`no_available_source_or_actor` on every retry until it expires - a source was
found, it was just unreachable. Traced on the workshop soak with a worker frozen
at (6, 8) while its "source" sat at (124, 155).

The bound is a little over one CHUNK_SIZE, which is roughly a village across.

**The distances below are deliberately literal.** The first version of this file
placed its far source at `MAX_HAUL_SOURCE_DISTANCE + 40` and asserted the result
was within `MAX_HAUL_SOURCE_DISTANCE`. Both halves moved together, so removing
the bound entirely still passed every behavioural test - only the constant guard
noticed. A test for a limit must not measure in units of that limit.
"""

import unittest

from config import CHUNK_SIZE, WORLD_WIDTH
from tests.world_cache import fresh_world

# "Another settlement", in tiles, chosen independently of the constant.
ANOTHER_SETTLEMENT = 150
# The furthest a villager may be sent, in tiles, likewise independent.
FURTHEST_REASONABLE = 80


class TestTheSearchIsBounded(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=11, pre_simulate=False)
        self.npc = self.world.village_npcs[0]
        # Only the sources a test places should be in play. A generated world
        # already stocks lumber mills and general stores with raw_log, and the
        # first version of this file cleared only the ground - so the search
        # kept returning a perfectly legitimate building six tiles away and the
        # distance assertion looked like a failure of the fix.
        self.world.items_on_map.clear()
        for stockpile in self.world.stockpiles_by_id.values():
            stockpile.stored_inventory.clear()
        for building in self.world.buildings_by_id.values():
            inventory = getattr(building, "building_inventory", None)
            if inventory is not None and inventory.get("raw_log", 0):
                inventory.remove_item("raw_log", inventory.get("raw_log", 0))

    def _find(self):
        return self.world._find_nearest_haul_source(self.npc, "raw_log")

    def _far_spot(self):
        """A tile ANOTHER_SETTLEMENT away, on whichever side has room."""
        if self.npc.x > WORLD_WIDTH // 2:
            return (self.npc.x - ANOTHER_SETTLEMENT, self.npc.y)
        return (self.npc.x + ANOTHER_SETTLEMENT, self.npc.y)

    def test_a_source_across_the_world_is_not_chosen(self):
        self.world.drop_item_on_map("raw_log", 1, *self._far_spot())
        self.assertIsNone(
            self._find(),
            "picked a haul source beyond the distance a villager will walk",
        )

    def test_a_source_in_the_village_is_still_chosen(self):
        """The bound must not simply switch hauling off."""
        self.world.drop_item_on_map("raw_log", 1, self.npc.x + 2, self.npc.y)
        source = self._find()
        self.assertIsNotNone(source, "a log two tiles away was not considered")
        self.assertEqual(source["coords"], (self.npc.x + 2, self.npc.y))

    def test_the_near_source_wins_when_both_exist(self):
        near = (self.npc.x + 3, self.npc.y)
        self.world.drop_item_on_map("raw_log", 1, *self._far_spot())
        self.world.drop_item_on_map("raw_log", 1, *near)
        self.assertEqual(self._find()["coords"], near)

    def test_the_bound_is_about_one_village_across(self):
        """Guards the constant against being widened back to the whole map."""
        self.assertGreaterEqual(self.world.MAX_HAUL_SOURCE_DISTANCE, CHUNK_SIZE)
        self.assertLessEqual(self.world.MAX_HAUL_SOURCE_DISTANCE, CHUNK_SIZE * 2)

    def test_the_edge_of_the_bound_is_included(self):
        limit = self.world.MAX_HAUL_SOURCE_DISTANCE
        self.world.drop_item_on_map("raw_log", 1, self.npc.x + limit, self.npc.y)
        self.assertIsNotNone(self._find(), "a source exactly at the limit was rejected")


class TestAgainstTheWorldAsGenerated(unittest.TestCase):
    """The invariant against real generated content, not a cleared world.

    Honest about its own strength: this one passes with the bound removed too,
    because on seed 11 every villager happens to have a stocked building nearby.
    It is a guard against a future fourth source tier being added without a
    bound, not evidence that the current bound works - the cleared-world cases
    above are what actually discriminate.
    """

    def test_nobody_is_sent_to_the_next_settlement(self):
        world = fresh_world(seed=11, pre_simulate=False)
        for npc in world.village_npcs[:12]:
            source = world._find_nearest_haul_source(npc, "raw_log")
            if source is None:
                continue
            distance = abs(npc.x - source["coords"][0]) + abs(npc.y - source["coords"][1])
            self.assertLessEqual(
                distance, FURTHEST_REASONABLE,
                f"{npc.name} was sent {distance} tiles for a raw_log",
            )


if __name__ == "__main__":
    unittest.main()
