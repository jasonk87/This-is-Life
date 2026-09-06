"""Assertions about what happened, which may be wrong.

Three layers now:

    record  - what happened.            The world's, in the HistoryLedger.
    claim   - an assertion about it.    Shared; many people may hold the same one.
    fact    - somebody believing one.   Personal (KnownHistoryFact).

Before this a belief pointed straight at a record, so a villager could be
uncertain, vague or forgetful, but never actually wrong. There was nowhere to
put "I heard it was the miller" when it was the baker.

The claim id hashes the assertion and nothing else - not the teller, not
confidence, not memory strength. Two people who arrive at the same wrong story
separately therefore land on the same claim, so a rumour converges instead of
splintering into one private variant per person, and "who believes this" has an
answer.

The part that makes it cheap: every consumer of a belief's subject -
get_known_records_about_entity, dialogue_surface, ambient_info, social_reaction -
already reads `subject_entity_ids` off the *fact*. Populating that from the claim
rather than the record makes all of them epistemic without any of them changing.
TestAWrongBeliefReachesTheThingsThatReadBeliefs is the one that proves it.
"""

import unittest

from entities.social import Claim, KnownHistoryFact, claim_from_record
from tests.world_cache import fresh_world

BAKER, MILLER, CLARA = 101, 102, 103


class _Assault:
    """Stand-in for a HistoryLedger record: the baker assaulted Clara."""

    def __init__(self, record_id="assault-1", subject_id=BAKER, record_type="crime_recorded"):
        self.id = record_id
        self.type = record_type
        self.timestamp = 100
        self.subject_id = subject_id
        self.target_id = CLARA
        self.settlement_id = "village-1"
        self.tags = ()


def _blame(record, who):
    """The same event, but somebody else is held responsible."""
    truth = claim_from_record(record)
    return Claim(
        source_record_id=truth.source_record_id,
        believed_record_type=truth.believed_record_type,
        believed_subject_ids=tuple(who if i == record.subject_id else i
                                   for i in truth.believed_subject_ids),
        believed_target_id=truth.believed_target_id,
        believed_location_id=truth.believed_location_id,
    )


class TestClaimIdentity(unittest.TestCase):
    def test_the_same_assertion_is_the_same_claim(self):
        a = claim_from_record(_Assault())
        b = claim_from_record(_Assault())
        self.assertEqual(a.id, b.id)

    def test_blaming_someone_else_is_a_different_claim(self):
        truth = claim_from_record(_Assault())
        rumour = _blame(_Assault(), MILLER)
        self.assertNotEqual(truth.id, rumour.id)

    def test_two_people_inventing_the_same_rumour_converge(self):
        """The reason the id hashes the assertion and nothing else."""
        thomas_version = _blame(_Assault(), MILLER)
        owen_version = _blame(_Assault(), MILLER)
        self.assertEqual(thomas_version.id, owen_version.id)

    def test_a_claim_about_a_different_event_is_different(self):
        self.assertNotEqual(
            claim_from_record(_Assault(record_id="assault-1")).id,
            claim_from_record(_Assault(record_id="assault-2")).id,
        )

    def test_the_truth_is_just_the_claim_that_happens_to_be_right(self):
        record = _Assault()
        truth = claim_from_record(record)
        self.assertIn(BAKER, truth.believed_subject_ids)
        self.assertEqual(truth.believed_target_id, CLARA)
        self.assertEqual(truth.source_record_id, "assault-1")


class TestAWrongBeliefReachesTheThingsThatReadBeliefs(unittest.TestCase):
    """The point of the whole layer."""

    def setUp(self):
        self.world = fresh_world(seed=13, pre_simulate=False)
        self.knowledge = self.world.village_npcs[0].knowledge
        self.knowledge.known_history_facts.clear()
        self.record = _Assault()

    def test_believing_the_wrong_person_is_recorded_against_that_person(self):
        self.knowledge.learn_history_record(
            self.record, "told", 0.6, 100, source_entity_id=99,
            claim=_blame(self.record, MILLER))

        about_miller = self.knowledge.get_known_records_about_entity(MILLER)
        about_baker = self.knowledge.get_known_records_about_entity(BAKER)

        self.assertEqual(len(about_miller), 1,
                         "the innocent miller should be who this holder blames")
        self.assertEqual(about_baker, [],
                         "the actual culprit should not be attached to this belief")

    def test_the_victim_survives_the_distortion(self):
        self.knowledge.learn_history_record(
            self.record, "told", 0.6, 100, claim=_blame(self.record, MILLER))
        self.assertEqual(self.knowledge.get_known_records_about_entity(CLARA)[0].source_record_id,
                         "assault-1")

    def test_the_belief_still_points_at_the_real_event(self):
        """Wrong about who; not unmoored from what happened."""
        self.knowledge.learn_history_record(
            self.record, "told", 0.6, 100, claim=_blame(self.record, MILLER))
        fact = self.knowledge.known_history_facts["assault-1"]
        self.assertEqual(fact.source_record_id, "assault-1")
        self.assertEqual(fact.claim_id, _blame(self.record, MILLER).id)

    def test_learning_without_a_claim_believes_the_truth(self):
        self.knowledge.learn_history_record(self.record, "witnessed", 1.0, 100)
        fact = self.knowledge.known_history_facts["assault-1"]
        self.assertEqual(fact.claim_id, claim_from_record(self.record).id)
        self.assertIn(BAKER, fact.subject_entity_ids)


class TestTheRegistry(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=13, pre_simulate=False)
        self.system = self.world.knowledge_system

    def test_identical_claims_are_interned_to_one_object(self):
        first = self.system.register_claim(_blame(_Assault(), MILLER))
        second = self.system.register_claim(_blame(_Assault(), MILLER))
        self.assertIs(first, second)

    def test_a_claim_can_be_looked_up_by_id(self):
        claim = self.system.register_claim(_blame(_Assault(), MILLER))
        self.assertEqual(self.system.get_claim(claim.id), claim)

    def test_an_unknown_id_is_simply_absent(self):
        self.assertIsNone(self.system.get_claim("nonexistent"))

    def test_believers_can_be_counted(self):
        record = _Assault()
        rumour = _blame(record, MILLER)
        believers = self.world.village_npcs[:3]
        for npc in believers:
            npc.knowledge.known_history_facts.clear()
            npc.knowledge.learn_history_record(record, "told", 0.6, 100, claim=rumour)
        innocent = self.world.village_npcs[3]
        innocent.knowledge.known_history_facts.clear()
        innocent.knowledge.learn_history_record(record, "witnessed", 1.0, 100)

        found = self.system.believers_of(rumour.id, self.world.village_npcs[:4])
        self.assertEqual([n.id for n in found], [n.id for n in believers],
                         "the witness who knows the truth should not be counted")


class TestBeliefTravels(unittest.TestCase):
    """Telling someone passes on what you believe, not what happened.

    Without this a listener was handed the truth however mistaken the speaker
    was, so a wrong belief could never outlive the person who formed it - and
    distortion would have had nothing to distort.
    """

    def setUp(self):
        self.world = fresh_world(seed=13, pre_simulate=False)
        self.system = self.world.knowledge_system
        self.owen, self.mara = self.world.village_npcs[0], self.world.village_npcs[1]
        for npc in (self.owen, self.mara):
            npc.knowledge.known_history_facts.clear()
        self.record = _Assault()

    def test_a_mistaken_speaker_passes_on_their_mistake(self):
        rumour = _blame(self.record, MILLER)
        self.owen.knowledge.learn_history_record(
            self.record, "told", 0.7, 100, claim=self.system.register_claim(rumour))
        self.owen.knowledge.known_events[self.record.id] = self.record

        self.system.share_event(self.owen, self.mara, self.record)

        self.assertEqual(self.mara.knowledge.known_history_facts["assault-1"].claim_id,
                         rumour.id, "Mara was handed the truth instead of Owen's belief")
        self.assertEqual(self.mara.knowledge.get_known_records_about_entity(BAKER), [],
                         "the real culprit leaked through the retelling")

    def test_an_accurate_speaker_passes_on_the_truth(self):
        self.owen.knowledge.learn_history_record(self.record, "witnessed", 1.0, 100)
        self.owen.knowledge.known_events[self.record.id] = self.record

        self.system.share_event(self.owen, self.mara, self.record)

        self.assertEqual(self.mara.knowledge.known_history_facts["assault-1"].claim_id,
                         claim_from_record(self.record).id)

    def test_the_rumour_is_now_believed_by_two_people(self):
        rumour = self.system.register_claim(_blame(self.record, MILLER))
        self.owen.knowledge.learn_history_record(self.record, "told", 0.7, 100, claim=rumour)
        self.owen.knowledge.known_events[self.record.id] = self.record
        self.system.share_event(self.owen, self.mara, self.record)

        believers = self.system.believers_of(rumour.id, [self.owen, self.mara])
        self.assertEqual(len(believers), 2)


class TestOldSavesStillLoad(unittest.TestCase):
    def test_a_fact_without_a_claim_id_backfills_to_empty(self):
        fact = KnownHistoryFact(
            source_record_id="rec-old", record_type="crime_recorded",
            subject_entity_ids=(BAKER,), known_at_tick=50,
            source_type="told", confidence=0.7,
        )
        state = dict(fact.__dict__)
        state.pop("claim_id")
        restored = KnownHistoryFact.__new__(KnownHistoryFact)
        restored.__setstate__(state)
        self.assertEqual(restored.claim_id, "")
        self.assertEqual(restored.subject_entity_ids, (BAKER,))


if __name__ == "__main__":
    unittest.main()
