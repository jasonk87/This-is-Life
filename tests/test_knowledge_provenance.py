"""Who told you that.

`KnownHistoryFact.source_type` has always said *how* somebody came to know
something - witnessed, family, official_record, told. It never said *who* told
them, and the teller was being thrown away at the one point that knew it:
`KnowledgeSystem.share_event` takes `source` and `recipient` and passed only the
event on.

That field is small and buys a lot. "Who did you hear that from?" becomes a
question the simulation can answer, which is the verb an investigation runs on;
and telling a lie apart from repeating one later needs to know whose belief was
transmitted.

It also lets repetition be told apart from corroboration, which are not the same
thing and should not have the same weight:

    Thomas, Thomas, Thomas   -> one source
    Mara, Owen, Thomas       -> three sources

Only the second should make a belief sturdier. Callers that do not name a teller
- witnessing something, reading a record - keep the old unconditional behaviour,
because there is nobody there to be repetitive.
"""

import pickle
import unittest
from dataclasses import replace

from entities.social import KnownHistoryFact
from tests.world_cache import fresh_world


class _Record:
    """Minimal stand-in for a HistoryLedger record."""

    def __init__(self, record_id="rec-1", record_type="crime_recorded"):
        self.id = record_id
        self.type = record_type
        self.timestamp = 100
        self.subject_id = 1
        self.target_id = 2
        self.tags = ()


def _knowledge(world, index=0):
    return world.village_npcs[index].knowledge


class TestTheTellerIsRecorded(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=11, pre_simulate=False)
        self.knowledge = _knowledge(self.world)
        self.record = _Record()

    def test_a_told_fact_remembers_who_told_it(self):
        self.knowledge.learn_history_record(self.record, "told", 0.8, 100,
                                            source_entity_id=42)
        fact = self.knowledge.known_history_facts["rec-1"]
        self.assertEqual(fact.source_entity_id, 42)
        self.assertEqual(fact.heard_from_ids, (42,))

    def test_witnessing_something_names_no_teller(self):
        self.knowledge.learn_history_record(self.record, "witnessed", 1.0, 100)
        fact = self.knowledge.known_history_facts["rec-1"]
        self.assertIsNone(fact.source_entity_id)
        self.assertEqual(fact.heard_from_ids, ())

    def test_a_second_teller_is_added(self):
        self.knowledge.learn_history_record(self.record, "told", 0.8, 100, source_entity_id=42)
        self.knowledge.learn_history_record(self.record, "told", 0.8, 110, source_entity_id=77)
        fact = self.knowledge.known_history_facts["rec-1"]
        self.assertEqual(fact.heard_from_ids, (42, 77))
        self.assertEqual(fact.source_entity_id, 77, "should track the most recent teller")


class TestRepetitionIsNotCorroboration(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=11, pre_simulate=False)
        self.knowledge = _knowledge(self.world)
        self.record = _Record()

    def _strength_after(self, teller_ids):
        self.knowledge.known_history_facts.clear()
        for tick, teller in enumerate(teller_ids, start=100):
            self.knowledge.learn_history_record(self.record, "told", 0.8, tick,
                                                source_entity_id=teller)
        return self.knowledge.known_history_facts["rec-1"].memory_strength

    def test_one_person_saying_it_three_times_does_not_strengthen_it(self):
        once = self._strength_after([42])
        thrice = self._strength_after([42, 42, 42])
        self.assertEqual(thrice, once,
                         "repetition from a single teller made the memory sturdier")

    def test_three_different_people_do_strengthen_it(self):
        once = self._strength_after([42])
        three = self._strength_after([42, 77, 91])
        self.assertGreater(three, once,
                           "three separate tellers did not corroborate anything")

    def test_a_repeat_teller_is_not_counted_twice(self):
        self._strength_after([42, 42, 77])
        self.assertEqual(self.knowledge.known_history_facts["rec-1"].heard_from_ids, (42, 77))


class TestSharingRecordsTheSource(unittest.TestCase):
    """The seam this whole field exists for."""

    def test_share_event_names_the_speaker(self):
        world = fresh_world(seed=11, pre_simulate=False)
        speaker, listener = world.village_npcs[0], world.village_npcs[1]
        record = _Record(record_id="rec-share")
        speaker.knowledge.learn_history_record(record, "witnessed", 1.0, 100)
        speaker.knowledge.known_events[record.id] = record

        world.knowledge_system.share_event(speaker, listener, record)

        fact = listener.knowledge.known_history_facts["rec-share"]
        self.assertEqual(fact.source_entity_id, speaker.id)
        self.assertEqual(fact.heard_from_ids, (speaker.id,))
        self.assertEqual(fact.source_type, "told")


class TestOldSavesStillLoad(unittest.TestCase):
    """Pickle replays a saved __dict__ and never calls __init__.

    A fact written before these fields existed comes back without them, and the
    next line to touch one raises AttributeError - on a player's save file. The
    frozen dataclass had no __setstate__ at all, unlike its siblings.
    """

    def test_a_fact_pickled_without_the_new_fields_backfills_them(self):
        fact = KnownHistoryFact(
            source_record_id="rec-old",
            record_type="crime_recorded",
            subject_entity_ids=(1,),
            known_at_tick=50,
            source_type="told",
            confidence=0.7,
        )
        state = dict(fact.__dict__)
        state.pop("source_entity_id")
        state.pop("heard_from_ids")

        restored = KnownHistoryFact.__new__(KnownHistoryFact)
        restored.__setstate__(state)

        self.assertIsNone(restored.source_entity_id)
        self.assertEqual(restored.heard_from_ids, ())
        self.assertEqual(restored.confidence, 0.7, "existing fields must survive")

    def test_a_fact_round_trips_through_pickle(self):
        fact = KnownHistoryFact(
            source_record_id="rec-rt",
            record_type="crime_recorded",
            subject_entity_ids=(1,),
            known_at_tick=50,
            source_type="told",
            confidence=0.7,
            source_entity_id=42,
            heard_from_ids=(42, 77),
        )
        restored = pickle.loads(pickle.dumps(fact))
        self.assertEqual(restored.source_entity_id, 42)
        self.assertEqual(restored.heard_from_ids, (42, 77))

    def test_the_fact_is_still_immutable(self):
        fact = KnownHistoryFact(
            source_record_id="rec-frozen", record_type="crime_recorded",
            subject_entity_ids=(1,), known_at_tick=50, source_type="told", confidence=0.7,
        )
        with self.assertRaises(Exception):
            fact.confidence = 0.9
        self.assertEqual(replace(fact, confidence=0.9).confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
