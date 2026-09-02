"""A generated village contains the trades it is built to contain.

_generate_village_structure asks for seventeen kinds of building, and most of
them used not to appear. Measured over 24 villages before this was fixed: the
carpenter shop placed in none, the clinic in one, the library in four, the farm
in five, the mill in nine, the mine in ten - so Healer and Scribe were
professions no generated world contained, and half the work chains in the
economy had nowhere to happen.

The chunk was not too small. It was being spent badly, in three ways, all in
try_place_building:

  * a building that found no room gave up after checking 67 hand-picked offsets
    around one corner - 4% of the positions in the chunk - and 20 random darts;
  * a yard was reserved exclusively, so two neighbours each paid for the gap
    between them, though nothing anywhere draws a yard;
  * a road counted as a building, costing every structure a full yard of setback
    from both roads, in a chunk the roads already quarter.

These tests pin the outcome and the invariants that outcome must not break.
"""

import collections
import random
import unittest

from config import CHUNK_SIZE
from engine import World

# Types generation actually asks for. church and guard_tower are deliberately
# absent: they have no try_place_building call at all, so they are not a packing
# question and asserting on them would only encode that gap as expected.
ALWAYS_EXPECTED = [
    "capital_hall", "general_store", "tavern", "house", "jail",
    "sheriff_office", "lumber_mill", "mill", "bakery", "mine",
    "blacksmith_shop", "farm", "library", "butcher_shop", "hunting_lodge",
]

# Deliberately not asserted on, and each for its own reason:
#   carpenter_shop - generation asks for it and the chunk has no room left by the
#     time it does. A scale decision, recorded in VILLAGE_LAYOUT_NOTE.
#   church, guard_tower - no try_place_building call exists at all, so no amount
#     of packing produces them. Asserting on these would encode a gap as expected.
#   clinic - a village has room for exactly two buildings that reserve a yard.
#     The tavern takes one and a house takes the other, and housing wins that
#     contest because it is load-bearing. See VILLAGE_LAYOUT_NOTE.
NOT_YET_PLACED = ["clinic", "carpenter_shop", "church", "guard_tower"]


def _villages(world):
    return [
        chunk.village
        for row in world.chunks
        for chunk in row
        if getattr(chunk, "village", None) is not None
    ]


class TestGeneratedVillagesAreFullyBuilt(unittest.TestCase):
    """Two worlds, built once and only ever read.

    Shared setup is safe here in a way it was not for the help-quest tests:
    nothing below mutates the world, so no test can decide the answer for
    another. Seeded so a failure is reproducible rather than a coin toss.
    """

    @classmethod
    def setUpClass(cls):
        cls.villages = []
        for seed in (11, 12):
            random.seed(seed)
            cls.villages.extend(_villages(World(player_first_name="Surveyor")))
        assert cls.villages, "the probe generated no villages at all"

    def test_every_expected_trade_has_somewhere_to_happen(self):
        present = collections.Counter()
        for village in self.villages:
            for b_type in {b.building_type for b in village.buildings}:
                present[b_type] += 1

        total = len(self.villages)
        missing = {
            b_type: present[b_type]
            for b_type in ALWAYS_EXPECTED
            if present[b_type] < total
        }
        self.assertEqual(
            missing, {},
            f"of {total} villages, these placed in fewer than all of them: {missing}",
        )

    def test_no_two_buildings_overlap(self):
        for village in self.villages:
            claimed = {}
            for b in village.buildings:
                for y in range(b.y, b.y + b.height):
                    for x in range(b.x, b.x + b.width):
                        previous = claimed.get((x, y))
                        self.assertIsNone(
                            previous,
                            f"{b.building_type} overlaps {previous} at {(x, y)}",
                        )
                        claimed[(x, y)] = b.building_type

    def test_every_building_is_inside_its_chunk(self):
        for village in self.villages:
            for b in village.buildings:
                self.assertGreaterEqual(b.x, 0)
                self.assertGreaterEqual(b.y, 0)
                self.assertLessEqual(
                    b.x + b.width, CHUNK_SIZE,
                    f"{b.building_type} runs off the east edge of its chunk",
                )
                self.assertLessEqual(
                    b.y + b.height, CHUNK_SIZE,
                    f"{b.building_type} runs off the south edge of its chunk",
                )

    def test_nothing_is_built_on_the_crossroads(self):
        """Yards may lie across a street now; footprints still may not."""
        road = CHUNK_SIZE // 2
        for village in self.villages:
            for b in village.buildings:
                on_main = b.y <= road < b.y + b.height
                on_cross = b.x <= road < b.x + b.width
                self.assertFalse(
                    on_main and on_cross,
                    f"{b.building_type} sits on the crossroads at {(b.x, b.y)}",
                )
                self.assertFalse(on_main, f"{b.building_type} blocks the main road")
                self.assertFalse(on_cross, f"{b.building_type} blocks the cross road")

    def test_every_village_has_somewhere_to_live(self):
        """Housing is load-bearing: a villager without a home has no settling
        anchor and no household, and the birth system needs somewhere to put a
        child. So this asserts at least one home, which is what the chunk
        currently has room for.

        Generation asks for three to five and gets one - before this work and
        after it alike. That is a real shortfall and it is written up in
        VILLAGE_LAYOUT_NOTE rather than asserted here, because a test that
        demanded three would fail on a world nobody has agreed to change yet,
        and one that asserts exactly one would enshrine the shortfall as correct.
        """
        for village in self.villages:
            houses = [b for b in village.buildings if b.category == "residential"]
            self.assertGreaterEqual(
                len(houses), 1,
                "a village generated with nowhere at all to live",
            )


if __name__ == "__main__":
    unittest.main()
