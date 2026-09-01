"""Wildlife keeps its distance from settlements when it first appears.

The old check only measured against the spawning chunk's own village, and only
out to 8 tiles from each building's centre, so wolves manifested at the edge of
town - close enough to be standing in it.
"""

import unittest

from engine import World
from simulation.ecology import (
    DEFAULT_SETTLEMENT_BUFFER,
    PREDATOR_SETTLEMENT_BUFFER,
    WILDLIFE_SPECIES,
)


def _chebyshev_distance_to_box(x: int, y: int, box: tuple[int, int, int, int]) -> int:
    """0 when the point is inside the box, otherwise tiles to its nearest edge."""
    min_x, min_y, max_x, max_y = box
    return max(max(min_x - x, 0, x - max_x), max(min_y - y, 0, y - max_y))


class TestWildlifeSettlementDistance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.settlements = []
        for row in cls.world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is None:
                    continue
                extent = cls.world._get_settlement_extent(village)
                if extent is not None:
                    cls.settlements.append(extent)
        # Ambient wildlife only. Dungeons stock their own hostile animals at
        # scripted positions (see _generate_dungeon_layout) and those are not
        # governed by the settlement buffer - a wolf in a dungeon is the point.
        cls.animals = [
            npc
            for npc in cls.world.npcs
            if getattr(npc, "wildlife_population_id", None) and not npc.physical.is_dead
        ]

    def _closest_settlement_distance(self, animal) -> int:
        return min(
            (_chebyshev_distance_to_box(animal.x, animal.y, box) for box in self.settlements),
            default=10**6,
        )

    def test_the_world_has_settlements_and_wildlife_to_check(self):
        self.assertGreater(len(self.settlements), 0)
        self.assertGreater(len(self.animals), 0)

    def test_no_animal_spawns_inside_a_settlement(self):
        for animal in self.animals:
            self.assertGreater(
                self._closest_settlement_distance(animal),
                0,
                f"a {animal.animal_type} spawned inside a settlement at {(animal.x, animal.y)}",
            )

    def test_each_species_respects_its_own_buffer(self):
        for animal in self.animals:
            buffer_tiles = self.world._wildlife_settlement_buffer(animal.animal_type)
            self.assertGreater(
                self._closest_settlement_distance(animal),
                buffer_tiles,
                f"a {animal.animal_type} spawned {self._closest_settlement_distance(animal)} "
                f"tiles from town, inside its {buffer_tiles}-tile buffer",
            )

    def test_predators_are_held_further_off_than_grazers(self):
        self.assertGreater(PREDATOR_SETTLEMENT_BUFFER, DEFAULT_SETTLEMENT_BUFFER)
        self.assertEqual(
            self.world._wildlife_settlement_buffer("wolf"), PREDATOR_SETTLEMENT_BUFFER
        )
        self.assertEqual(
            self.world._wildlife_settlement_buffer("deer"), DEFAULT_SETTLEMENT_BUFFER
        )

    def test_unknown_species_fall_back_to_the_default_buffer(self):
        self.assertNotIn("griffon", WILDLIFE_SPECIES)
        self.assertEqual(
            self.world._wildlife_settlement_buffer("griffon"), DEFAULT_SETTLEMENT_BUFFER
        )


class TestSettlementExclusionGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.village = next(
            (
                chunk.village
                for row in cls.world.chunks
                for chunk in row
                if getattr(chunk, "village", None)
            ),
            None,
        )

    def test_extent_covers_every_building(self):
        self.assertIsNotNone(self.village)
        min_x, min_y, max_x, max_y = self.world._get_settlement_extent(self.village)
        for building in self.village.buildings:
            self.assertGreaterEqual(building.global_origin_x, min_x)
            self.assertGreaterEqual(building.global_origin_y, min_y)
            self.assertLessEqual(building.global_origin_x + building.width - 1, max_x)
            self.assertLessEqual(building.global_origin_y + building.height - 1, max_y)

    def test_a_villages_neighbours_are_excluded_too(self):
        """A wolf one tile the far side of a chunk boundary is still next to town."""
        chunk_x, chunk_y = self.village.chunk_coords
        for neighbour_x, neighbour_y in [
            (chunk_x - 1, chunk_y),
            (chunk_x + 1, chunk_y),
            (chunk_x, chunk_y - 1),
            (chunk_x, chunk_y + 1),
        ]:
            if not (
                0 <= neighbour_x < self.world.chunk_width
                and 0 <= neighbour_y < self.world.chunk_height
            ):
                continue
            exclusions = self.world._get_settlement_spawn_exclusions(
                neighbour_x, neighbour_y, PREDATOR_SETTLEMENT_BUFFER
            )
            self.assertGreater(
                len(exclusions),
                0,
                f"chunk {(neighbour_x, neighbour_y)} next to a village has no exclusion",
            )


if __name__ == "__main__":
    unittest.main()
