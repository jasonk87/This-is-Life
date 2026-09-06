"""A story changing in the retelling.

The chain this exists to make possible, none of it scripted:

    Owen sees the baker strike Clara.
    Owen tells Mara across a noisy tavern.
    Mara, who has no time for the miller, hears it as the miller.
    Mara tells Thomas.
    Thomas now believes the miller did it, and so does Mara.

Nobody wrote that story. It falls out of a witness, a telling, and a grudge.

Two properties matter more than the effect itself:

**It is not random.** The tick loop is reproducible from a seed - three separate
bugs have been fixed in this project from real time and uuid4 leaking into it -
so distortion hashes the claim, the two people and the day instead of rolling
dice. The same telling garbles the same way every run.

**It only touches weak evidence.** Somebody who watched it happen is not talked
out of it, and better evidence later corrects a wrong belief rather than being
outvoted by it. TestEvidenceBeatsHearsay is that half.
"""

import unittest
from unittest.mock import patch

from entities.social import Claim, claim_from_record
from simulation import distortion
from simulation.distortion import distort_on_telling
from tests.world_cache import fresh_world

BAKER, CLARA = 101, 103


class _Assault:
    def __init__(self, record_id="assault-1"):
        self.id = record_id
        self.type = "crime_recorded"
        self.timestamp = 100
        self.subject_id = BAKER
        self.target_id = CLARA
        self.settlement_id = "village-1"
        self.tags = ()


def _certain_mishearing():
    """Force the roll, so a test is about the mechanism and not about odds."""
    return patch.object(distortion, "MISHEARING_CHANCE", 100)


class _DistortionTestCase(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=17, pre_simulate=False)
        self.system = self.world.knowledge_system
        self.owen, self.mara, self.thomas = self.world.village_npcs[:3]
        for npc in (self.owen, self.mara, self.thomas):
            npc.knowledge.known_history_facts.clear()
            npc.knowledge.known_events.clear()
        self.record = _Assault()
        self.truth = claim_from_record(self.record)

    def _dislike(self, hater, disliked, severity=60):
        hater.add_grudge(disliked.id, "old business", severity=severity, current_day=0)


class TestItIsNotRandom(_DistortionTestCase):
    def test_the_same_telling_garbles_the_same_way_every_time(self):
        self._dislike(self.mara, self.thomas)
        results = {
            distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                               villagers=self.world.village_npcs,
                               confidence=0.8, day=3).id
            for _ in range(20)
        }
        self.assertEqual(len(results), 1, "the same telling produced different results")

    def test_a_different_day_can_land_differently(self):
        """Not that it must differ - only that the day is part of the hash."""
        self._dislike(self.mara, self.thomas)
        ids = {
            distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                               villagers=self.world.village_npcs,
                               confidence=0.8, day=day).id
            for day in range(40)
        }
        self.assertGreater(len(ids), 1, "the day never mattered, so nothing is varying")

    def test_no_dice_are_rolled(self):
        """random.random() here would quietly cost the seed its reproducibility."""
        self._dislike(self.mara, self.thomas)
        with patch("random.random", side_effect=AssertionError("distortion used random")), \
             patch("random.choice", side_effect=AssertionError("distortion used random")):
            distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                               villagers=self.world.village_npcs, confidence=0.8, day=3)


class TestWhoGetsBlamed(_DistortionTestCase):
    def test_it_is_somebody_the_listener_already_dislikes(self):
        self._dislike(self.mara, self.thomas)
        with _certain_mishearing():
            heard = distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                                       villagers=self.world.village_npcs,
                                       confidence=0.8, day=3)
        self.assertEqual(heard.believed_subject_ids[0], self.thomas.id)

    def test_a_listener_with_no_grudges_hears_it_straight(self):
        """A stranger blamed at random reads as a bug, not as a rumour."""
        with _certain_mishearing():
            heard = distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                                       villagers=self.world.village_npcs,
                                       confidence=0.8, day=3)
        self.assertIs(heard, self.truth)

    def test_the_victim_is_never_blamed(self):
        victim = self.world.village_npcs[4]
        truth = Claim(source_record_id="assault-2", believed_record_type="crime_recorded",
                      believed_subject_ids=(BAKER,), believed_target_id=victim.id)
        self._dislike(self.mara, victim, severity=90)
        with _certain_mishearing():
            heard = distort_on_telling(truth, speaker=self.owen, listener=self.mara,
                                       villagers=self.world.village_npcs,
                                       confidence=0.8, day=3)
        self.assertNotIn(victim.id, heard.believed_subject_ids)

    def test_a_listener_does_not_blame_themselves(self):
        self.mara.add_grudge(self.mara.id, "self-loathing", severity=90, current_day=0)
        with _certain_mishearing():
            heard = distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                                       villagers=self.world.village_npcs,
                                       confidence=0.8, day=3)
        self.assertNotIn(self.mara.id, heard.believed_subject_ids)


class TestOnlyIdentityMoves(_DistortionTestCase):
    def test_everything_except_who_survives_intact(self):
        self._dislike(self.mara, self.thomas)
        with _certain_mishearing():
            heard = distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                                       villagers=self.world.village_npcs,
                                       confidence=0.8, day=3)
        self.assertNotEqual(heard.believed_subject_ids[0], BAKER)
        self.assertEqual(heard.source_record_id, self.truth.source_record_id)
        self.assertEqual(heard.believed_record_type, self.truth.believed_record_type)
        self.assertEqual(heard.believed_target_id, self.truth.believed_target_id)
        self.assertEqual(heard.believed_location_id, self.truth.believed_location_id)


class TestStrongEvidenceIsNotGarbled(_DistortionTestCase):
    def test_a_confident_telling_comes_through_clean(self):
        self._dislike(self.mara, self.thomas)
        with _certain_mishearing():
            heard = distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                                       villagers=self.world.village_npcs,
                                       confidence=1.0, day=3)
        self.assertIs(heard, self.truth, "a first-hand account should not be misheard")


class TestEvidenceBeatsHearsay(_DistortionTestCase):
    """The damping. A rumour must not overturn what somebody saw."""

    def test_seeing_it_yourself_corrects_a_rumour_you_believed(self):
        rumour = self.system.register_claim(
            Claim(source_record_id="assault-1", believed_record_type="crime_recorded",
                  believed_subject_ids=(self.thomas.id,), believed_target_id=CLARA))
        self.mara.knowledge.learn_history_record(self.record, "told", 0.6, 100, claim=rumour)
        self.assertEqual(self.mara.knowledge.known_history_facts["assault-1"].claim_id, rumour.id)

        self.mara.knowledge.learn_history_record(self.record, "witnessed", 1.0, 200)

        fact = self.mara.knowledge.known_history_facts["assault-1"]
        self.assertEqual(fact.claim_id, self.truth.id, "witnessing it did not correct the rumour")
        self.assertIn(BAKER, fact.subject_entity_ids)

    def test_hearsay_does_not_overturn_what_you_saw(self):
        self.mara.knowledge.learn_history_record(self.record, "witnessed", 1.0, 100)
        rumour = self.system.register_claim(
            Claim(source_record_id="assault-1", believed_record_type="crime_recorded",
                  believed_subject_ids=(self.thomas.id,), believed_target_id=CLARA))

        self.mara.knowledge.learn_history_record(self.record, "told", 0.6, 200, claim=rumour)

        fact = self.mara.knowledge.known_history_facts["assault-1"]
        self.assertEqual(fact.claim_id, self.truth.id, "a rumour talked a witness out of it")


class TestTheWholeChain(_DistortionTestCase):
    """Owen saw it. Thomas ends up blamed. Nobody wrote that."""

    def test_a_rumour_forms_and_then_outlives_its_teller(self):
        self._dislike(self.mara, self.thomas)

        # Owen witnesses the truth.
        self.owen.knowledge.learn_history_record(self.record, "witnessed", 1.0, 100)
        self.owen.knowledge.known_events[self.record.id] = self.record
        self.assertIn(BAKER,
                      self.owen.knowledge.known_history_facts["assault-1"].subject_entity_ids)

        # Owen tells Mara, and it comes out wrong.
        with _certain_mishearing():
            self.system.share_event(self.owen, self.mara, self.record)

        mara_fact = self.mara.knowledge.known_history_facts["assault-1"]
        self.assertEqual(mara_fact.subject_entity_ids[0], self.thomas.id)
        self.assertEqual(mara_fact.source_entity_id, self.owen.id)

        # Mara passes on what she now believes. Third parties get her version,
        # not the truth Owen still holds.
        bystander = self.world.village_npcs[5]
        bystander.knowledge.known_history_facts.clear()
        self.system.share_event(self.mara, bystander, self.record)

        self.assertEqual(
            bystander.knowledge.known_history_facts["assault-1"].claim_id,
            mara_fact.claim_id,
            "the rumour did not survive being passed on",
        )
        self.assertEqual(bystander.knowledge.get_known_records_about_entity(BAKER), [],
                         "the truth leaked back in")
        self.assertEqual(len(bystander.knowledge.get_known_records_about_entity(self.thomas.id)), 1,
                         "an innocent man should now be suspected by someone he never met")

        # And Owen, who saw it, is untouched.
        self.assertIn(BAKER,
                      self.owen.knowledge.known_history_facts["assault-1"].subject_entity_ids)

    def test_at_the_real_rate_it_is_occasional_and_reproducible(self):
        """Not every telling garbles, and which ones do is fixed by the seed."""
        self._dislike(self.mara, self.thomas)
        outcomes = [
            distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                               villagers=self.world.village_npcs,
                               confidence=0.8, day=day).id != self.truth.id
            for day in range(200)
        ]
        self.assertTrue(any(outcomes), "no telling was ever misheard in 200 days")
        self.assertFalse(all(outcomes), "every telling was misheard; the gate is not working")

        again = [
            distort_on_telling(self.truth, speaker=self.owen, listener=self.mara,
                               villagers=self.world.village_npcs,
                               confidence=0.8, day=day).id != self.truth.id
            for day in range(200)
        ]
        self.assertEqual(outcomes, again, "the same 200 days garbled differently on a re-run")


if __name__ == "__main__":
    unittest.main()
