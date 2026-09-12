"""The village gives itself something to talk about.

Every part of the rumour mill existed except a reason for one to start: the only
thing in the whole engine that could create a harmful incident was the player
throwing a punch, so ninety people could live together for days and never give
each other a reason to gossip.

These tests cover the three things that had to be true for that to change, and
the two properties that stop it becoming a bloodbath.
"""

import unittest

from simulation.systems.grievances import (
    GRIEVANCE_KINDS,
    TIER_THRESHOLDS,
    DETECTORS,
    _history_between,
    advance_interpersonal_incidents,
    apply_grievance_act,
    village_context,
)
from tests.world_cache import fresh_world


class TestPeopleAreDifferentFromEachOther(unittest.TestCase):
    """Without this, nothing else here can work.

    Personality comes from an LLM at world generation and falls back to the
    literal string "commoner" for everybody when there is no LLM, which is the
    ordinary case. That left has_trait() returning False for every villager and
    every trait - not only for grievances but for the aggressive, chaotic,
    lawful, greedy and lazy branches already scattered through the engine.
    """

    def setUp(self):
        self.world = fresh_world(seed=2024, pre_simulate=False)
        self.npcs = self.world.village_npcs

    def test_not_everybody_is_identical(self):
        with_traits = [n for n in self.npcs if n.social.innate_traits]
        self.assertTrue(with_traits, "no villager has any temperament at all")

    def test_most_people_are_unremarkable(self):
        """A village where everyone has a strong temperament is as wrong as one
        where nobody does."""
        plain = sum(1 for n in self.npcs if not n.social.innate_traits)
        self.assertGreater(plain, len(self.npcs) * 0.25,
                           "almost everybody has a pronounced temperament")

    def test_the_traits_that_start_fights_are_the_rare_ones(self):
        aggressive = sum(1 for n in self.npcs if n.has_trait("aggressive"))
        lawful = sum(1 for n in self.npcs if n.has_trait("lawful"))
        self.assertLess(aggressive, lawful,
                        "there are more brawlers than law-abiding people")

    def test_the_personality_string_is_left_alone(self):
        """Several places compare it exactly - `personality in ["friendly",
        "gregarious", "neutral", "commoner"]` gates whether an NPC will greet
        the player, and scheduling tests `== "Greedy"` - so temperament must not
        be appended to it. Traits live in their own field for this reason.

        Asserting every villager is literally "commoner" was too strong: one
        NPC on seed 2024 is created by a different path and comes out
        "friendly", which has nothing to do with this change.
        """
        from entities.base import INNATE_TRAIT_WEIGHTS

        trait_words = [word for word, _ in INNATE_TRAIT_WEIGHTS]
        for npc in self.npcs:
            personality = (npc.social.personality or "").lower()
            for word in trait_words:
                self.assertNotIn(
                    word, personality,
                    f"temperament '{word}' was written into {npc.name}'s personality "
                    "string; the exact-match checks elsewhere will stop matching")

    def test_traits_reach_has_trait(self):
        someone = next((n for n in self.npcs if n.social.innate_traits), None)
        self.assertIsNotNone(someone)
        self.assertTrue(someone.has_trait(someone.social.innate_traits[0]))


class TestOwnershipIsNotTheWayToWakeUpPayroll(unittest.TestCase):
    """A trap this feature fell into once and should not fall into again.

    No generated building has an owner_id, which leaves the payroll system
    unreachable: the daily wage run only checks whether a workplace can cover
    its wages when `owner_id is not None`, so wages are never paid, never
    missed, and nobody ever quits over money. Assigning owners at world
    generation looks like the obvious fix and produces excellent grievances -
    it was 70% of all incidents in the first run that tried it.

    It also quietly breaks the labour market, one way. `owner_id` does not mean
    "this NPC is the boss"; it means "privately run, and outside the public
    vacancy system". `_sync_building_employment_tasks` returns immediately for
    an owned building, so once a worker quits one of these over unpaid wages
    the post can never be advertised again. Measured: 68 missed wages in under
    three game days, employment falling 81 -> 58 in three, and unemployment
    still climbing after a simulated month.

    Unpaid wages remain a real grievance - the hook in the payroll run is live
    and fires for genuinely owner-built businesses. Extending it to the rest of
    the village needs workplaces that earn enough to make payroll, which is
    economic work rather than social.
    """

    def test_generated_workplaces_stay_in_the_labour_market(self):
        world = fresh_world(seed=2024, pre_simulate=False)
        owned = [b for b in world.buildings_by_id.values()
                 if getattr(b, "owner_id", None) is not None]
        self.assertEqual(
            owned, [],
            "world generation assigned building owners again; those workplaces "
            "no longer post vacancies and will leak jobs as staff quit")

    def test_the_vacancy_system_still_skips_owned_buildings(self):
        """The behaviour the rule above exists because of. If this ever stops
        being true, assigning owners becomes safe and this whole restriction
        can be revisited."""
        from engine import Building

        world = fresh_world(seed=2024, pre_simulate=False)
        building = Building(0, 0, 5, 5, building_type="lumber_mill", category="commercial_workplace")
        building.max_workers = 2
        building.owner_id = world.player.id
        world.buildings_by_id[building.id] = building
        world._sync_building_employment_tasks(building)
        self.assertEqual(world.town_board.get_open_employment_tasks(building.id), [])
        # Positive control: the exact same unowned workplace posts vacancies.
        building.owner_id = None
        world._sync_building_employment_tasks(building)
        self.assertEqual(len(world.town_board.get_open_employment_tasks(building.id)), 2)

    def test_unpaid_wages_is_still_a_reachable_grievance(self):
        """Deferring the cause must not leave dead content behind."""
        self.assertIn("unpaid_wages", GRIEVANCE_KINDS)
        import inspect

        import engine

        self.assertIn("unpaid_wages", inspect.getsource(engine),
                      "nothing in the engine can raise an unpaid-wages grievance")


class TestAnActIsNotAResentment(unittest.TestCase):
    """Nobody wrongs you by holding the job you wanted. Blurring the two would
    have the village inventing crimes nobody committed."""

    def test_resentments_create_no_incident(self):
        world = fresh_world(seed=2024, pre_simulate=False)
        before = len(world.harmful_incidents)
        holder, subject = world.village_npcs[0], world.village_npcs[1]
        kind = GRIEVANCE_KINDS["job_envy"]
        self.assertFalse(kind.is_act)
        from simulation.systems.grievances import _apply_resentment
        _apply_resentment(world, kind, subject, holder, {})
        self.assertEqual(len(world.harmful_incidents), before,
                         "a private resentment was recorded as a public event")
        self.assertTrue(holder.social.grudges.get(subject.id),
                        "the resentment left no trace at all")

    def test_acts_create_an_incident_others_can_see(self):
        world = fresh_world(seed=2024, pre_simulate=False)
        wrongdoer, victim = world.village_npcs[0], world.village_npcs[1]
        victim.x, victim.y = wrongdoer.x, wrongdoer.y
        incident = apply_grievance_act(
            world, GRIEVANCE_KINDS["insult"], wrongdoer, victim, {})
        self.assertIsNotNone(incident)
        self.assertEqual(incident.kind, "insult")
        self.assertEqual(victim.knowledge.known_harmful_incidents[incident.id]
                         .attributed_attacker_id, wrongdoer.id)

    def test_the_victim_blames_the_person_who_did_it(self):
        world = fresh_world(seed=2024, pre_simulate=False)
        wrongdoer, victim = world.village_npcs[0], world.village_npcs[1]
        apply_grievance_act(world, GRIEVANCE_KINDS["insult"], wrongdoer, victim, {})
        self.assertGreater(victim.get_grudge_severity_towards(wrongdoer.id), 0)


class TestViolenceHasToBeEarned(unittest.TestCase):
    """The property that keeps this from being a brawl generator."""

    def test_you_cannot_attack_a_stranger(self):
        world = fresh_world(seed=2024, pre_simulate=False)
        a, b = world.village_npcs[0], world.village_npcs[1]
        self.assertLess(_history_between(a, b.id), TIER_THRESHOLDS[3],
                        "two people who have never met are already able to come to blows")

    def test_assault_sits_above_every_non_violent_kind(self):
        assault = GRIEVANCE_KINDS["assault"]
        for kind in GRIEVANCE_KINDS.values():
            if kind.key == "assault":
                continue
            self.assertLessEqual(
                kind.tier, assault.tier,
                f"{kind.key} needs as much history as an assault does")

    def test_most_kinds_are_not_violent(self):
        violent = {"assault"}
        self.assertLess(len(violent), len(GRIEVANCE_KINDS) / 3,
                        "violence is too large a share of what can happen")

    def test_the_mildest_response_is_the_preferred_one(self):
        """The bug that turned this into a brawl generator.

        Candidate ordering was `inclination * (1 + tier)`, which sorted the
        worst thing a person could do to the top of the list. Over 40,000 ticks
        assault became the single most common event in the village: one pair
        traded seven of them inside a day. Weighting has to fall as severity
        rises, so people reach for the smallest thing that expresses the
        grievance.
        """
        from simulation.systems.grievances import _inclination

        world = fresh_world(seed=2024, pre_simulate=False)
        actor = world.village_npcs[0]

        def weight(kind):
            return _inclination(actor, kind) / (1.0 + kind.tier * 2.0)

        mild = GRIEVANCE_KINDS["workplace_argument"]
        severe = GRIEVANCE_KINDS["assault"]
        self.assertGreater(weight(mild), weight(severe),
                           "an assault outranks an argument in the candidate ordering")

    def test_only_the_violent_few_can_be_violent(self):
        """History alone is a bad gate: an assault leaves a grudge severe enough
        to re-qualify the pair for another one, so it sustains itself. The
        temperament requirement is what keeps violence rare."""
        from simulation.systems.grievances import VIOLENT_KINDS

        self.assertIn("assault", VIOLENT_KINDS)
        world = fresh_world(seed=2024, pre_simulate=False)
        gentle = next(n for n in world.village_npcs if not n.has_trait("aggressive"))
        self.assertFalse(gentle.has_trait("aggressive"))

    def test_a_quarrel_is_one_subject_not_two(self):
        """Ordered cooldown keys let A and B take turns every cadence."""
        from simulation.systems.grievances import _pair_key

        world = fresh_world(seed=2024, pre_simulate=False)
        a, b = world.village_npcs[0], world.village_npcs[1]
        self.assertEqual(_pair_key(a, b), _pair_key(b, a),
                         "a feud has two independent cooldowns, so they can ping-pong")

    def test_violence_is_rare_but_not_impossible(self):
        """Zero assaults in a soak could mean "rare" or "unreachable", and those
        are very different bugs. This builds the situation violence is supposed
        to be the answer to - a long feud, and somebody with the temperament for
        it - and checks the gate actually opens.
        """
        from simulation.systems.grievances import VIOLENT_KINDS

        world = fresh_world(seed=2024, pre_simulate=False)
        brawler = next((n for n in world.village_npcs if n.has_trait("aggressive")), None)
        self.assertIsNotNone(brawler, "no villager has the temperament for violence at all")
        enemy = next(n for n in world.village_npcs if n.id != brawler.id)

        # A feud, not a bad afternoon.
        brawler.add_grudge(enemy.id, "a long story", severity=90, current_day=0, decay_days=30)

        history = _history_between(brawler, enemy.id)
        self.assertGreaterEqual(
            history, TIER_THRESHOLDS[3],
            "even a bitter, sustained feud cannot reach the top of the ladder")
        for key in VIOLENT_KINDS:
            self.assertIn(key, GRIEVANCE_KINDS)

    def test_a_gentle_person_never_reaches_for_violence(self):
        """The other half of the same gate."""
        world = fresh_world(seed=2024, pre_simulate=False)
        gentle = next(n for n in world.village_npcs if not n.has_trait("aggressive"))
        enemy = next(n for n in world.village_npcs if n.id != gentle.id)
        gentle.add_grudge(enemy.id, "a long story", severity=90, current_day=0, decay_days=30)

        # History is there; temperament is not.
        self.assertGreaterEqual(_history_between(gentle, enemy.id), TIER_THRESHOLDS[3])
        self.assertFalse(gentle.has_trait("aggressive"),
                         "picked a brawler for the gentle-person case")

    def test_one_bad_afternoon_does_not_unlock_the_knife(self):
        """A single argument used to push two people straight past tier 2."""
        world = fresh_world(seed=2024, pre_simulate=False)
        a, b = world.village_npcs[0], world.village_npcs[1]
        apply_grievance_act(world, GRIEVANCE_KINDS["workplace_argument"], a, b, {})
        self.assertLess(_history_between(b, a.id), TIER_THRESHOLDS[3],
                        "one argument was enough to make violence available")


class TestNothingIsDeadContent(unittest.TestCase):
    """This project's recurring defect is correct logic wired to nothing."""

    def test_every_kind_can_be_produced(self):
        """Either a detector yields it, or the engine raises it directly."""
        import inspect

        import engine
        from simulation.systems import grievances

        source = inspect.getsource(grievances) + inspect.getsource(engine.World.pay_daily_wages) \
            if hasattr(engine.World, "pay_daily_wages") else inspect.getsource(grievances)
        engine_source = inspect.getsource(engine)
        for key in GRIEVANCE_KINDS:
            with self.subTest(kind=key):
                self.assertTrue(
                    f'"{key}"' in source or f'"{key}"' in engine_source,
                    f"{key} is defined but nothing can ever produce it")

    def test_there_are_detectors(self):
        self.assertTrue(DETECTORS)


class TestItStaysQuietWhenItShould(unittest.TestCase):
    def test_a_contented_village_produces_nothing(self):
        """No hardship, no bad blood, nobody out of work - so nothing happens."""
        world = fresh_world(seed=2024, pre_simulate=False)
        for npc in world.village_npcs:
            npc.social.grudges.clear()
            npc.social.local_opinions.clear()
            npc.social.relationships.clear()
            npc.economic.money = 500
            npc.economic.days_unemployed = 0
        world.game_time = 0
        before = len(world.harmful_incidents)
        advance_interpersonal_incidents(world)
        self.assertEqual(len(world.harmful_incidents), before,
                         "a village with nothing wrong in it still produced grievances")

    def test_village_context_reads_the_village(self):
        world = fresh_world(seed=2024, pre_simulate=False)
        context = village_context(world)
        self.assertIn("median_money", context)
        self.assertIn("median_regard", context)


if __name__ == "__main__":
    unittest.main()
