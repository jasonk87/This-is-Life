"""The capital hall and the jail can employ people.

Every path that hires a villager asks the same question - is "workplace" in this
building's category - and the capital hall and the jail are registered as plain
"civic". Both stand in every village, both declare worker capacity (three and
two), and both map to a real role in BUILDING_ROLE_RULES: capital_hall to Town
Official, jail to Guard. So both had posts nobody could ever be hired into, and
Town Official and Guard were professions the game defines and never fills -
measured over six worlds and then over fourteen simulated days, zero of either.

The fix is a predicate, not a relabel. The category string is also read for
interior generation and for territory claims, where "workplace" in the category
is exactly what makes a claim a business rather than the settlement core - and
the capital hall is the settlement core. Those tests are below too, because they
are the reason the obvious one-word fix was not taken.
"""

import unittest

from engine import World
from simulation.careers import BUILDING_ROLE_RULES, resolve_profession_for_building


def _first(world, building_type):
    return next(
        b for b in world.buildings_by_id.values()
        if b.building_type == building_type
    )


class TestCivicBuildingsCanEmploy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=7)

    def test_the_capital_hall_can_employ(self):
        hall = _first(self.world, "capital_hall")
        self.assertTrue(self.world._building_can_employ(hall))
        self.assertGreater(hall.max_workers, 0)

    def test_the_jail_can_employ(self):
        jail = _first(self.world, "jail")
        self.assertTrue(self.world._building_can_employ(jail))
        self.assertGreater(jail.max_workers, 0)

    def test_they_map_to_the_professions_they_are_meant_to(self):
        self.assertEqual(resolve_profession_for_building("capital_hall"), "Town Official")
        self.assertEqual(resolve_profession_for_building("jail"), "Guard")

    def test_homes_are_still_not_places_of_work(self):
        houses = [b for b in self.world.buildings_by_id.values() if b.category == "residential"]
        self.assertTrue(houses, "no houses in this world to check")
        for house in houses:
            self.assertFalse(self.world._building_can_employ(house))

    def test_the_predicate_adds_exactly_these_two_kinds(self):
        """A guard against the predicate quietly widening. Anything that is not
        already a workplace by category has to be one of the two civic buildings
        that declare capacity and a role."""
        added = {
            b.building_type
            for b in self.world.buildings_by_id.values()
            if self.world._building_can_employ(b) and "workplace" not in b.category
        }
        self.assertEqual(added, {"capital_hall", "jail"})

    def test_every_employable_building_has_a_role_to_offer(self):
        for b in self.world.buildings_by_id.values():
            if not self.world._building_can_employ(b):
                continue
            role = resolve_profession_for_building(b.building_type)
            self.assertTrue(str(role).strip(), f"{b.building_type} employs but offers no role")


class TestTheCategoriesWereLeftAlone(unittest.TestCase):
    """Relabelling these two as civic_workplace would have been a smaller diff and
    a worse one. These pin the reasons."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=7)

    def test_the_capital_hall_is_still_the_settlement_core(self):
        hall = _first(self.world, "capital_hall")
        self.assertNotIn(
            "workplace", hall.category,
            "the capital hall became a workplace by category, which turns its "
            "territory claim from settlement_core into business",
        )

    def test_the_jail_is_still_civic(self):
        self.assertNotIn("workplace", _first(self.world, "jail").category)


class TestAVillagerCanBeHiredIntoTheCapitalHall(unittest.TestCase):
    """A world per test - these mutate it."""

    def setUp(self):
        self.world = World(seed=7)
        self.world._pre_simulate_world()

    def _empty_out(self, building):
        for npc in self.world.village_npcs:
            if npc.schedule.work_building_id == building.id:
                npc.schedule.work_building_id = None
        return building

    def test_an_open_post_at_the_hall_can_be_found(self):
        village = next(
            chunk.village
            for row in self.world.chunks for chunk in row
            if getattr(chunk, "village", None) is not None
            and any(b.building_type == "capital_hall" for b in chunk.village.buildings)
        )
        hall = self._empty_out(
            next(b for b in village.buildings if b.building_type == "capital_hall")
        )
        self.assertEqual(self.world._count_building_workers(hall), 0)

        seeker = next(
            n for n in self.world.village_npcs
            if not n.physical.is_dead
            and self.world._get_npc_settlement(n) is village
        )
        seeker.schedule.work_building_id = None
        seeker.economic.profession = "Unemployed"

        # Every other post in the village is taken, so the hall is the only
        # vacancy left and _find_open_post_for has to be willing to offer it.
        for b in village.buildings:
            if b is hall or not self.world._building_can_employ(b):
                continue
            b.max_workers = 0

        post = self.world._find_open_post_for(seeker)
        self.assertIsNotNone(post, "no vacancy found when the hall had three")
        self.assertEqual(post.building_type, "capital_hall")

    def test_being_hired_there_makes_a_town_official(self):
        village = next(
            chunk.village
            for row in self.world.chunks for chunk in row
            if getattr(chunk, "village", None) is not None
            and any(b.building_type == "capital_hall" for b in chunk.village.buildings)
        )
        hall = self._empty_out(
            next(b for b in village.buildings if b.building_type == "capital_hall")
        )
        seeker = next(
            n for n in self.world.village_npcs
            if not n.physical.is_dead and self.world._get_npc_settlement(n) is village
        )

        self.world._assign_job(seeker, hall, reason="test")

        self.assertEqual(seeker.schedule.work_building_id, hall.id)
        self.assertEqual(seeker.economic.profession, "Town Official")


class TestTheRolesExistInTheTable(unittest.TestCase):
    def test_both_civic_buildings_are_in_the_rules(self):
        self.assertIn("capital_hall", BUILDING_ROLE_RULES)
        self.assertIn("jail", BUILDING_ROLE_RULES)


class TestTradesThatWereDefinedButNeverBuilt(unittest.TestCase):
    """An audit of building types the game defines against the ones generation
    actually asks for turned up several with a profession already mapped to them
    and no try_place_building call anywhere - so those professions could not
    exist in any world. This covers the ones that have since been wired up.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=7)

    def test_a_butcher_has_somewhere_to_work(self):
        shops = [
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "butcher_shop"
        ]
        self.assertTrue(shops, "no butcher shop was generated in this world")
        self.assertEqual(resolve_profession_for_building("butcher_shop"), "Butcher")

    def test_the_butcher_shop_has_the_zone_its_work_needs(self):
        """Butcher's single work step targets a workbench; without the zone the
        shop exists but no work can happen in it."""
        shop = next(
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "butcher_shop"
        )
        self.assertIn("workbench", shop.work_zone_tiles)
        self.assertTrue(shop.work_zone_tiles["workbench"])

    def test_shared_lodging_is_built(self):
        common = [
            b for b in self.world.buildings_by_id.values()
            if b.building_type == "common_house"
        ]
        self.assertTrue(common, "no common house was generated in this world")
        for house in common:
            self.assertEqual(house.category, "residential")

    def test_most_villagers_have_a_bed(self):
        """Not all - the chunk still cannot hold enough. The ones who do not
        sleep rough rather than walking all night; see test_night_lodging."""
        world = World(player_first_name="Surveyor")
        world._pre_simulate_world()
        alive = [n for n in world.village_npcs if not n.physical.is_dead]
        self.assertTrue(alive)
        housed = [n for n in alive if n.schedule.home_building_id]
        self.assertGreater(
            len(housed) / len(alive), 0.5,
            f"only {len(housed)} of {len(alive)} villagers have a home",
        )


if __name__ == "__main__":
    unittest.main()
