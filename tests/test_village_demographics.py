"""A generated village already contains families, so the population can turn over.

_simulate_village_population_lifecycle gates every birth behind a real married
couple - deliberately, so children have actual parents rather than appearing from
a random pairing. The only way to become married is the live courtship pipeline,
which needs a villager in an active chunk to roll a 1% leisure check and then
build a relationship past 70. World generation married nobody.

So a fresh village had 33 adults of childbearing age, no couples, and no route to
any: driving the daily abstract simulation across 60 in-game days produced zero
births and zero deaths, with the median age frozen. A village that existed before
the player arrived should already have families in it.
"""

import unittest
from unittest.mock import patch

from config import DAY_LENGTH_TICKS
from engine import (
    MARRIAGE_SEED_MAX_AGE,
    MARRIAGE_SEED_MIN_AGE,
    MARRIAGE_SEED_RATE,
    World,
)


def _partner_id(npc):
    ties = npc.social.family_ties if isinstance(npc.social.family_ties, dict) else {}
    return ties.get("partner_id") or ties.get("spouse_id")


def _couples(world):
    alive = {npc.id: npc for npc in world.village_npcs if not npc.physical.is_dead}
    found = set()
    for npc in alive.values():
        partner = _partner_id(npc)
        if partner in alive and _partner_id(alive[partner]) == npc.id:
            found.add(frozenset((npc.id, partner)))
    return found, alive


class TestVillagesStartWithFamilies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()
        cls.couples, cls.alive = _couples(cls.world)

    def test_a_generated_world_has_married_couples(self):
        self.assertGreater(len(self.couples), 0, "nobody in the world is married")

    def test_marriages_point_both_ways(self):
        for couple in self.couples:
            first, second = (self.alive[i] for i in couple)
            self.assertEqual(_partner_id(first), second.id)
            self.assertEqual(_partner_id(second), first.id)

    def test_nobody_is_married_to_themselves(self):
        for npc in self.alive.values():
            self.assertNotEqual(_partner_id(npc), npc.id)

    def test_nobody_holds_two_spouses(self):
        spouses = [_partner_id(npc) for npc in self.alive.values() if _partner_id(npc)]
        self.assertEqual(len(spouses), len(set(spouses)), "someone is listed as two people's spouse")

    def test_seeded_spouses_are_adults(self):
        for couple in self.couples:
            for npc_id in couple:
                age = int(getattr(self.alive[npc_id], "age", 0) or 0)
                # Courtship can marry people outside the seeding window later on;
                # at world generation nobody should be outside it.
                self.assertGreaterEqual(age, MARRIAGE_SEED_MIN_AGE - 1)

    def test_some_couples_can_actually_have_children(self):
        """The precondition the lifecycle needs, and the one that was missing."""
        childbearing = [
            couple for couple in self.couples
            if all(18 <= int(getattr(self.alive[i], "age", 0) or 0) <= 50 for i in couple)
        ]
        self.assertGreater(len(childbearing), 0, "no couple is of childbearing age")

    def test_not_everyone_is_married(self):
        """A whole village of couples would be as odd as none."""
        self.assertLess(MARRIAGE_SEED_RATE, 1.0)
        unmarried = [npc for npc in self.alive.values() if not _partner_id(npc)]
        self.assertGreater(len(unmarried), 0)


class TestThePopulationTurnsOver(unittest.TestCase):
    """Asserted deterministically rather than by waiting on a 5%-a-day roll.

    Watching for a birth over enough in-game days to be reliable costs minutes of
    test time and is still a dice throw; forcing the roll asks the real question,
    which is whether an eligible couple actually results in a child.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def _village_with_a_childbearing_couple(self):
        """A village with an eligible couple AND room for the child."""
        couples, alive = _couples(self.world)
        for couple in couples:
            if not all(18 <= int(getattr(alive[i], "age", 0) or 0) <= 50 for i in couple):
                continue
            village = self.world._get_npc_settlement(alive[next(iter(couple))])
            if village is None:
                continue
            residents = [
                npc for npc in self.world.village_npcs
                if not npc.physical.is_dead and self.world._get_npc_settlement(npc) is village
            ]
            if len(residents) < self.world._village_population_capacity(village):
                return village
        return None

    def test_an_eligible_couple_produces_a_child(self):
        village = self._village_with_a_childbearing_couple()
        if village is None:
            self.skipTest("no childbearing couple in this generated world")

        world = self.world
        residents = [
            npc for npc in world.village_npcs
            if not npc.physical.is_dead and world._get_npc_settlement(npc) is village
        ]
        before = len(residents)

        with patch("engine.random.random", return_value=0.0):
            world._simulate_village_population_lifecycle(
                village, residents, location=(residents[0].x, residents[0].y)
            )

        after = len([
            npc for npc in world.village_npcs
            if not npc.physical.is_dead and world._get_npc_settlement(npc) is village
        ])
        self.assertGreater(after, before, "a certain birth roll produced no child")

    def test_a_village_has_room_to_grow_when_it_is_generated(self):
        """The birth cap used to sit below the size generation produces, so most
        villages could never have a single child."""
        world = self.world
        checked = with_room = 0
        for row in world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is None:
                    continue
                residents = [
                    npc for npc in world.village_npcs
                    if not npc.physical.is_dead and world._get_npc_settlement(npc) is village
                ]
                if not residents:
                    continue
                checked += 1
                if len(residents) < world._village_population_capacity(village):
                    with_room += 1
        self.assertGreater(checked, 0, "no populated villages")
        self.assertEqual(
            with_room, checked,
            f"only {with_room} of {checked} villages can ever have a birth",
        )

    def test_a_village_with_no_couples_has_no_births(self):
        """Children need parents - that is the rule the seeding exists to satisfy."""
        world = self.world
        village = next(
            (chunk.village for row in world.chunks for chunk in row if getattr(chunk, "village", None)),
            None,
        )
        self.assertIsNotNone(village)
        residents = [
            npc for npc in world.village_npcs
            if not npc.physical.is_dead and world._get_npc_settlement(npc) is village
        ]
        if not residents:
            self.skipTest("village has no residents")

        saved = {}
        for npc in residents:
            saved[npc.id] = dict(npc.social.family_ties or {})
            npc.social.family_ties.pop("partner_id", None)
            npc.social.family_ties.pop("spouse_id", None)
        try:
            before = len(residents)
            with patch("engine.random.random", return_value=0.0):
                world._simulate_village_population_lifecycle(
                    village, residents, location=(residents[0].x, residents[0].y)
                )
            after = len([
                npc for npc in world.village_npcs
                if not npc.physical.is_dead and world._get_npc_settlement(npc) is village
            ])
            self.assertEqual(after, before, "a village with no married couples still produced a child")
        finally:
            for npc in residents:
                npc.social.family_ties.clear()
                npc.social.family_ties.update(saved[npc.id])


if __name__ == "__main__":
    unittest.main()
