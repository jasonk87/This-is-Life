"""Nothing sends an NPC to a tile they cannot stand on.

A building's `global_center` is a convenient handle and a poor destination: about
a tenth of a village's buildings have furniture on the middle tile, and every
tavern does - its centre is the table. Pathing at an impassable tile finds no
route, so the caller concludes the building is unreachable. That is how a
freezing villager standing one tile from their tavern decided they could not get
inside, and how anyone hungry enough to visit a tavern failed to arrive.

The same mistake in a different dress - aiming at one exact tile nothing can
occupy - also broke arrival at workplaces, work stations and the noticeboard.
"""

import unittest

from engine import World


class TestStandableBuildingTargets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.buildings = [
            building
            for row in cls.world.chunks
            for chunk in row
            if getattr(chunk, "village", None)
            for building in chunk.village.buildings
        ]

    def test_the_world_has_buildings_to_check(self):
        self.assertGreater(len(self.buildings), 0)

    def test_some_building_centres_really_are_blocked(self):
        """If this ever stops being true the helper is untested, not unnecessary."""
        blocked = [
            building
            for building in self.buildings
            if not (lambda tile: tile is not None and tile.passable)(
                self.world.get_tile_at(building.global_center_x, building.global_center_y)
            )
        ]
        self.assertGreater(
            len(blocked), 0,
            "no building centre is furniture in this world - the premise needs rechecking",
        )

    def test_every_building_offers_somewhere_to_stand(self):
        for building in self.buildings:
            with self.subTest(building=building.building_type):
                spot = self.world.get_standable_tile_in_building(building, None)
                self.assertIsNotNone(spot, "no standable tile offered")
                tile = self.world.get_tile_at(*spot)
                self.assertIsNotNone(tile)
                self.assertTrue(tile.passable, f"offered impassable tile {spot}")

    def test_a_clear_centre_is_used_as_is(self):
        """The helper should not wander off a perfectly good centre tile."""
        for building in self.buildings:
            centre = (building.global_center_x, building.global_center_y)
            tile = self.world.get_tile_at(*centre)
            if tile is not None and tile.passable:
                self.assertEqual(self.world.get_standable_tile_in_building(building, None), centre)
                return
        self.skipTest("no building with a clear centre in this world")

    def test_a_food_source_is_reachable_from_where_people_are(self):
        world = self.world
        checked = reachable = 0
        for npc in [n for n in world.village_npcs if not n.physical.is_dead][:12]:
            sources = [
                b for b in (world._find_nearest_tavern(npc), world._find_nearest_food_vendor(npc)) if b
            ]
            if not sources:
                continue
            checked += 1
            target = world.get_standable_tile_in_building(sources[0], npc)
            if target and world.calculate_path(npc.x, npc.y, target[0], target[1]):
                reachable += 1
        if not checked:
            self.skipTest("no food sources in this generated world")
        self.assertGreaterEqual(
            reachable, int(checked * 0.75),
            f"only {reachable} of {checked} villagers could route to a food source",
        )


if __name__ == "__main__":
    unittest.main()
