"""Offices come up for election again.

evaluate_elections skipped any office that already had a holder, and the only
forced election in the game ran once, at world creation. So the entire political
system was settled on day zero and frozen. Measured over 120 days - more than a
full in-game year - neither the Mayor nor the Captain of the Guard ever changed
hands, and PoliticalOffice.last_elected_day was written once and read by nothing.

The player has always been in the candidate list, so the only way they could hold
office was to win that first election, on the day they arrive with no standing
and no job. That left three player actions - Adjust Taxes, Issue Bounty, Issue
Arrest Warrant - which no ordinary game could reach.

With a term, the same 120 days hold four elections and each office passes through
three different holders, and a player the village thinks well of is elected at the
first term boundary.

The sitting holder stands again like any other candidate: this is a term limit on
the office, not on the person.
"""

import random
import unittest

import engine
from config import DAY_LENGTH_TICKS, DAYS_PER_SEASON
from engine import ELECTION_TERM_DAYS, World


def _run_governance_on(world, day):
    """Run a day's governance, at an hour when it actually runs.

    _run_daily_governance fires at or after DAILY_GOVERNANCE_TICK_OFFSET, so a
    probe that sets game_time to the very start of the day sees nothing happen -
    which is how the first measurement of this came back as zero elections.
    """
    world.game_time = day * DAY_LENGTH_TICKS + engine.DAILY_GOVERNANCE_TICK_OFFSET
    world._run_daily_governance()


class TestTermLength(unittest.TestCase):
    def test_a_term_is_one_season(self):
        self.assertEqual(ELECTION_TERM_DAYS, DAYS_PER_SEASON)

    def test_it_is_short_enough_to_matter_in_a_run(self):
        """Long enough that an election is an event, short enough that a player
        can realistically stand for office."""
        self.assertGreater(ELECTION_TERM_DAYS, 7)
        self.assertLess(ELECTION_TERM_DAYS, 200)


class TestOfficesAreContestedAgain(unittest.TestCase):
    def setUp(self):
        random.seed(5)
        self.world = World(player_first_name="Candidate")
        self.world._pre_simulate_world()
        if self.world.get_town_hall_building() is None:
            self.skipTest("this world generated no town hall")
        self.offices = self.world.politics.offices
        if not self.offices:
            self.skipTest("this world defined no political offices")

    def test_offices_are_filled_at_world_creation(self):
        self.assertTrue(
            any(o.holder_id is not None for o in self.offices.values()),
            "no office was filled when the world was made",
        )

    def test_nothing_is_re_run_before_the_term_is_out(self):
        before = {name: o.last_elected_day for name, o in self.offices.items()}
        for day in range(1, ELECTION_TERM_DAYS - 1):
            _run_governance_on(self.world, day)
        after = {name: o.last_elected_day for name, o in self.offices.items()}
        self.assertEqual(after, before, "an election was held before the term ended")

    def test_an_election_is_held_once_the_term_expires(self):
        before = {name: o.last_elected_day for name, o in self.offices.items()}
        for day in range(1, ELECTION_TERM_DAYS + 3):
            _run_governance_on(self.world, day)
        after = {name: o.last_elected_day for name, o in self.offices.items()}
        self.assertNotEqual(after, before, "the term expired and nothing was contested")

    def test_last_elected_day_is_actually_used_now(self):
        for day in range(1, ELECTION_TERM_DAYS + 3):
            _run_governance_on(self.world, day)
        for name, office in self.offices.items():
            self.assertGreater(
                office.last_elected_day, 0,
                f"{name} was never re-elected, so the field is still write-only",
            )

    def test_offices_stay_filled_across_elections(self):
        """Turnover must not leave the village ungoverned."""
        for day in range(1, ELECTION_TERM_DAYS * 3):
            _run_governance_on(self.world, day)
        for name, office in self.offices.items():
            self.assertIsNotNone(
                office.holder_id, f"{name} was left vacant after re-election"
            )


class TestThePlayerCanStand(unittest.TestCase):
    def test_a_well_regarded_player_can_be_elected(self):
        random.seed(5)
        world = World(player_first_name="Candidate")
        world._pre_simulate_world()
        if world.get_town_hall_building() is None:
            self.skipTest("this world generated no town hall")

        # Someone the village knows and thinks well of. Without terms this made
        # no difference at all - there was never another election to stand in.
        world.player.social.fame = 90
        world.player.social.infamy = 0
        for npc in world.village_npcs:
            if npc.physical.is_dead:
                continue
            knowledge = getattr(npc, "knowledge", None)
            setter = getattr(knowledge, "set_reputation_towards", None)
            if setter is not None:
                try:
                    setter(world.player, 100)
                except Exception:
                    pass
            npc.social.relationships[world.player.id] = 100

        for day in range(1, ELECTION_TERM_DAYS * 3):
            _run_governance_on(world, day)
            if world.player_has_governance_access():
                break

        self.assertTrue(
            world.player_has_governance_access(),
            "a player the whole village likes never won an office in three terms",
        )

    def test_holding_office_unlocks_the_governance_actions(self):
        """The three actions this was really about. They are wired to the
        governance menu and gated on holding office, so before terms existed no
        ordinary game could reach them."""
        random.seed(5)
        world = World(player_first_name="Candidate")
        world._pre_simulate_world()
        if not world.politics.offices:
            self.skipTest("this world defined no political offices")

        for office in world.politics.offices.values():
            office.holder_id = world.player.id

        actions = world.get_governance_actions()
        self.assertIn("Adjust Taxes", actions)
        self.assertIn("Issue Bounty", actions)
        self.assertIn("Issue Arrest Warrant", actions)


if __name__ == "__main__":
    unittest.main()
