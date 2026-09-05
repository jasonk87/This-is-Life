import unittest
from unittest import mock

import engine
from engine import NPC, Building, MemoryEvent, World
from tests.world_cache import fresh_world


class TestScoreCandidateForVoter(unittest.TestCase):
    """Unit tests for World._score_candidate_for_voter, the per-voter
    scoring function that replaced the old pre-summed
    _get_political_support_score formula."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=201, pre_simulate=False)
        self.jitter_patcher = mock.patch("engine.random.uniform", return_value=0.0)
        self.jitter_patcher.start()
        self.addCleanup(self.jitter_patcher.stop)

    def _npc(self, name="NPC"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)

    def test_reputation_flows_through_directly(self):
        voter = self._npc("Voter")
        candidate = self._npc("Candidate")
        voter.knowledge.record_event(MemoryEvent("murder", candidate.id, None, 1, 95))

        score = self.world._score_candidate_for_voter(voter, candidate, "Mayor")

        # murder is -50 in REPUTATION_EVENT_SCORES, and nothing else about
        # this pair should be contributing (different default professions,
        # no relationship data, no family, no fame/infamy).
        self.assertLessEqual(score, -50)

    def test_shared_profession_track_gives_an_affinity_bonus(self):
        voter = self._npc("Voter")
        candidate_same_track = self._npc("Same Track")
        candidate_other_track = self._npc("Other Track")
        voter.economic.profession = "Farmer"
        candidate_same_track.economic.profession = "Miller"  # both "agriculture" in PROFESSION_TRACKS
        candidate_other_track.economic.profession = "Blacksmith"  # "craft"

        score_same = self.world._score_candidate_for_voter(voter, candidate_same_track, "Mayor")
        score_other = self.world._score_candidate_for_voter(voter, candidate_other_track, "Mayor")

        self.assertGreater(score_same, score_other)

    def test_unemployed_voters_get_no_affinity_bonus(self):
        voter = self._npc("Voter")  # default profession is Unemployed
        candidate = self._npc("Candidate")  # also Unemployed - trivially "matches"

        score = self.world._score_candidate_for_voter(voter, candidate, "Mayor")

        self.assertEqual(score, 0.0)

    def test_relationship_score_shifts_the_vote(self):
        voter = self._npc("Voter")
        liked = self._npc("Liked")
        disliked = self._npc("Disliked")
        voter.social.relationships[liked.id] = 90
        voter.social.relationships[disliked.id] = 10

        score_liked = self.world._score_candidate_for_voter(voter, liked, "Mayor")
        score_disliked = self.world._score_candidate_for_voter(voter, disliked, "Mayor")

        self.assertGreater(score_liked, score_disliked)

    def test_neutral_default_relationship_has_no_effect(self):
        voter = self._npc("Voter")
        candidate = self._npc("Candidate")  # no relationship entry -> default 50, centered

        score = self.world._score_candidate_for_voter(voter, candidate, "Mayor")

        self.assertEqual(score, 0.0)

    def test_unmapped_different_professions_do_not_receive_affinity_bonus(self):
        """Bard voter should NOT get affinity toward a Tailor candidate
        just because both profession track lookups return None (None != None fix)."""
        voter = self._npc("Voter")
        candidate = self._npc("Candidate")
        voter.economic.profession = "Bard"
        candidate.economic.profession = "Tailor"
        # Neither profession exists in PROFESSION_TRACKS, so both get None.
        # Without the fix the None == None comparison would incorrectly award
        # VOTER_PROFESSION_AFFINITY_BONUS here. With the fix they get 0.
        score = self.world._score_candidate_for_voter(voter, candidate, "Mayor")
        # Jitter is mocked to 0.0; no reputation, relationship, or shared track
        # should contribute. The only possible contribution is the broken
        # None==None path, so we assert exactly 0.
        self.assertEqual(score, 0.0,
                         "Bard/Tailor with unmapped profession tracks should "
                         "not receive a phantom affinity bonus (None==None guard)")

    def test_employer_amplifies_the_relationship_term(self):
        voter = self._npc("Voter")
        boss = self._npc("Boss")
        stranger = self._npc("Stranger")
        workplace = Building(0, 0, 4, 4, building_type="general_store", category="commercial_workplace")
        workplace.owner_id = boss.id
        self.world.buildings_by_id[workplace.id] = workplace
        voter.schedule.work_building_id = workplace.id
        voter.social.relationships[boss.id] = 90
        voter.social.relationships[stranger.id] = 90

        score_boss = self.world._score_candidate_for_voter(voter, boss, "Mayor")
        score_stranger = self.world._score_candidate_for_voter(voter, stranger, "Mayor")

        self.assertGreater(score_boss, score_stranger)

    def test_family_bonus_applies_for_spouse(self):
        voter = self._npc("Voter")
        spouse = self._npc("Spouse")
        stranger = self._npc("Stranger")
        voter.social.family_ties["spouse_id"] = spouse.id

        score_spouse = self.world._score_candidate_for_voter(voter, spouse, "Mayor")
        score_stranger = self.world._score_candidate_for_voter(voter, stranger, "Mayor")

        self.assertGreater(score_spouse, score_stranger)

    def test_fame_increases_score_infamy_decreases_it(self):
        voter = self._npc("Voter")
        famous = self._npc("Famous")
        infamous = self._npc("Infamous")
        famous.social.fame = 20
        infamous.social.infamy = 20

        score_famous = self.world._score_candidate_for_voter(voter, famous, "Mayor")
        score_infamous = self.world._score_candidate_for_voter(voter, infamous, "Mayor")

        self.assertGreater(score_famous, 0)
        self.assertLess(score_infamous, 0)

    def test_captain_of_guard_bonus_only_applies_to_that_office_and_law_professions(self):
        voter = self._npc("Voter")
        guard = self._npc("Guard")
        guard.economic.profession = "Guard"

        score_for_captain = self.world._score_candidate_for_voter(voter, guard, "Captain of the Guard")
        score_for_mayor = self.world._score_candidate_for_voter(voter, guard, "Mayor")

        self.assertGreater(score_for_captain, score_for_mayor)

    def test_jitter_is_applied_and_bounded(self):
        self.jitter_patcher.stop()  # let real jitter run for this one test
        voter = self._npc("Voter")
        candidate = self._npc("Candidate")

        scores = {self.world._score_candidate_for_voter(voter, candidate, "Mayor") for _ in range(25)}

        self.assertGreater(len(scores), 1)  # not identical every call
        for s in scores:
            self.assertLessEqual(abs(s), engine.VOTER_SCORE_JITTER + 0.001)
        self.jitter_patcher.start()  # keep addCleanup symmetric


class TestEvaluateElectionsIndividualVoting(unittest.TestCase):
    """evaluate_elections should tally one vote per voter (each voter's own
    top-scoring candidate) rather than picking whoever a pre-summed formula
    favors."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=211, pre_simulate=False)
        mock.patch("engine.random.uniform", return_value=0.0).start()
        self.addCleanup(mock.patch.stopall)

    def _npc(self, name, age=30):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.age = age
        return npc

    def test_majority_preference_wins_even_against_one_extreme_score(self):
        """3 voters. Two mildly prefer candidate A (small positive
        reputation each, plus a touch of fame so A also edges out the
        player/self/candidate-B default ties that every voter with no
        opinion otherwise falls back to). One voter has an enormous
        personal relationship with candidate B (a landlord/employer
        situation). Under the old pre-summed formula, B's single huge
        number could out-total A's two modest ones. Under real individual
        voting, A should still win comfortably, since each voter only ever
        casts one vote for their own favorite - this is the qualitative
        behavior change the whole redesign was for."""
        candidate_a = self._npc("Candidate A")
        candidate_b = self._npc("Candidate B")
        voter1 = self._npc("Voter1")
        voter2 = self._npc("Voter2")
        voter3 = self._npc("Voter3")
        self.world.village_npcs = [candidate_a, candidate_b, voter1, voter2, voter3]

        candidate_a.social.fame = 5  # modest local recognition, not a landslide on its own
        voter1.knowledge.record_event(MemoryEvent("heroic_rescue", candidate_a.id, None, 1, 50))
        voter2.knowledge.record_event(MemoryEvent("heroic_rescue", candidate_a.id, None, 1, 50))

        # Voter3 adores candidate B - maximum relationship plus employer tie,
        # by far the single strongest opinion anyone has about anyone here.
        workplace = Building(0, 0, 4, 4, building_type="general_store", category="commercial_workplace")
        workplace.owner_id = candidate_b.id
        self.world.buildings_by_id[workplace.id] = workplace
        voter3.schedule.work_building_id = workplace.id
        voter3.social.relationships[candidate_b.id] = 100

        self.world.evaluate_elections(force=True)

        self.assertEqual(self.world.politics.get_office("Mayor").holder_id, candidate_a.id)

    def test_vote_tally_ties_break_by_summed_score(self):
        """Force an exact 2-2 vote tie between two candidates (mocking
        _score_candidate_for_voter directly so the tie is exact and not at
        the mercy of the real formula's many interacting terms) and confirm
        the candidate with the higher summed score among their own voters
        wins - this is the tie-break path in evaluate_elections itself."""
        candidate_a = self._npc("Candidate A")
        candidate_b = self._npc("Candidate B")
        voter1 = self._npc("Voter1")
        voter2 = self._npc("Voter2")
        self.world.village_npcs = [candidate_a, candidate_b, voter1, voter2]
        player = self.world.player

        def fake_score(voter, candidate, office_name):
            if voter is player:
                return 100 if candidate is player else 0  # player stays out of the A/B race
            if voter is voter1:
                return 100 if candidate is candidate_a else 0
            if voter is voter2:
                return 100 if candidate is candidate_b else 0
            if voter is candidate_a:
                return 60 if candidate is candidate_a else 0  # A's self-vote score
            if voter is candidate_b:
                return 40 if candidate is candidate_b else 0  # B's self-vote score (lower)
            return 0

        with mock.patch.object(engine.World, "_score_candidate_for_voter", side_effect=fake_score):
            self.world.evaluate_elections(force=True)

        # Votes: A gets voter1 + A's own self-vote = 2. B gets voter2 + B's
        # own self-vote = 2. A 2-2 tie, broken by summed score:
        # A = 100 (voter1) + 60 (self) = 160, B = 100 (voter2) + 40 (self) = 140.
        self.assertEqual(self.world.politics.get_office("Mayor").holder_id, candidate_a.id)

    def test_only_fills_vacant_offices_unless_forced(self):
        candidate = self._npc("Sitting Mayor")
        self.world.village_npcs = [candidate]
        self.world.politics.offices["Mayor"].holder_id = candidate.id
        other = self._npc("Challenger")
        other.social.fame = 999
        self.world.village_npcs.append(other)

        self.world.evaluate_elections()  # not forced - Mayor already occupied

        self.assertEqual(self.world.politics.offices["Mayor"].holder_id, candidate.id)

    def test_no_candidates_is_a_no_op(self):
        self.world.village_npcs = []
        try:
            self.world.evaluate_elections(force=True)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"evaluate_elections raised with no NPC candidates (player-only): {exc}")


if __name__ == "__main__":
    unittest.main()
