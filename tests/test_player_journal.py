"""The player's log as their knowledge, not the world's database.

It used to state facts:

    The baker killed Clara.

The player holds the same KnowledgeComponent as every villager, so their log
should read like knowledge:

    You saw the baker attack Clara.
    Mara told you the baker attacked Clara.
    Word going round is that the miller attacked Clara.

The third one can be wrong, and staying wrong until something better arrives is
the point. Two people can now live in the same village and read different
accounts of the same afternoon.

The property that matters most here is that **a journal line is never rewritten**.
Its wording is chosen when the line is written, from the confidence held at that
moment, and frozen. If entries re-rendered against current confidence, then
learning the truth on Friday would reach back and change what Monday's entry says
you believed - a journal that edits its own past is worse than no journal.
TestTheJournalDoesNotRewriteThePast is that guarantee.
"""

import pickle
import unittest

from entities.social import Claim, claim_from_record
from presentation.message_log import LogEntry, append_knowledge_message
from presentation.player_journal import describe_claim, journal_line
from tests.world_cache import fresh_world

BAKER, CLARA, MILLER = 101, 103, 102
NAMES = {BAKER: "the baker", CLARA: "Clara", MILLER: "the miller", 7: "Mara"}


def _claim(subject=BAKER, record_type="crime_recorded"):
    return Claim(source_record_id="assault-1", believed_record_type=record_type,
                 believed_subject_ids=(subject,), believed_target_id=CLARA)


class _Assault:
    def __init__(self):
        self.id = "assault-1"
        self.type = "crime_recorded"
        self.timestamp = 100
        self.subject_id = BAKER
        self.target_id = CLARA
        self.settlement_id = "village-1"
        self.tags = ()


class TestHowALineReads(unittest.TestCase):
    def test_seeing_it_yourself(self):
        self.assertEqual(
            journal_line(_claim(), source_type="witnessed", confidence=1.0, names=NAMES),
            "You saw the baker attack Clara.")

    def test_being_told_by_somebody(self):
        self.assertEqual(
            journal_line(_claim(), source_type="told", teller_name="Mara",
                         confidence=0.8, names=NAMES),
            "Mara told you the baker attacked Clara.")

    def test_being_told_by_somebody_unsure(self):
        line = journal_line(_claim(), source_type="told", teller_name="Mara",
                            confidence=0.5, names=NAMES)
        self.assertEqual(line, "Mara says the baker attacked Clara.")

    def test_hearsay_with_no_teller_hedges(self):
        line = journal_line(_claim(), source_type="told", confidence=0.5, names=NAMES)
        self.assertIn("Word going round", line)

    def test_the_record_speaks_plainly(self):
        self.assertEqual(
            journal_line(_claim(), source_type="official_record", confidence=1.0, names=NAMES),
            "The record says the baker attacked Clara.")

    def test_a_wrong_belief_names_the_wrong_person(self):
        line = journal_line(_claim(subject=MILLER), source_type="told",
                            teller_name="Mara", confidence=0.8, names=NAMES)
        self.assertIn("the miller", line)
        self.assertNotIn("the baker", line)

    def test_an_unknown_name_does_not_leak_an_id(self):
        line = journal_line(_claim(subject=999), source_type="witnessed",
                            confidence=1.0, names=NAMES)
        self.assertNotIn("999", line)

    def test_describe_claim_on_nothing(self):
        self.assertEqual(describe_claim(None, NAMES), "something happened")


class TestTheJournalDoesNotRewriteThePast(unittest.TestCase):
    """Monday's entry must still say what Monday believed."""

    def test_learning_the_truth_later_leaves_the_old_entry_alone(self):
        entries = []
        monday = append_knowledge_message(
            entries, journal_line(_claim(subject=MILLER), source_type="told",
                                  teller_name="Mara", confidence=0.5, names=NAMES),
            claim_id=_claim(subject=MILLER).id, knowledge_source="told",
            source_entity_id=7, confidence_at_entry=0.5, tick=100)

        # Friday: the player sees it themselves and now knows better.
        append_knowledge_message(
            entries, journal_line(_claim(), source_type="witnessed",
                                  confidence=1.0, names=NAMES),
            claim_id=_claim().id, knowledge_source="witnessed",
            confidence_at_entry=1.0, tick=500)

        self.assertIn("the miller", monday.text)
        self.assertEqual(monday.confidence_at_entry, 0.5)
        self.assertEqual(entries[0].text, monday.text,
                         "Monday's entry was rewritten by Friday's knowledge")

    def test_two_tellings_are_two_entries_even_when_worded_alike(self):
        """"Mara told you" on Monday and "Owen told you" on Friday are two events."""
        entries = []
        for teller_id, tick in ((7, 100), (8, 500)):
            append_knowledge_message(
                entries, "Someone told you the baker attacked Clara.",
                claim_id="c1", knowledge_source="told",
                source_entity_id=teller_id, confidence_at_entry=0.8, tick=tick)
        self.assertEqual(len(entries), 2)
        self.assertEqual([e.source_entity_id for e in entries], [7, 8])

    def test_provenance_is_kept_for_a_current_knowledge_view(self):
        entries = []
        entry = append_knowledge_message(
            entries, "Mara told you the baker attacked Clara.",
            claim_id="claim-abc", knowledge_source="told",
            source_entity_id=7, confidence_at_entry=0.8, tick=100)
        self.assertEqual(entry.claim_id, "claim-abc")
        self.assertEqual(entry.knowledge_source, "told")
        self.assertEqual(entry.source_entity_id, 7)
        self.assertEqual(entry.confidence_at_entry, 0.8)


class TestOrdinaryMessagesAreUntouched(unittest.TestCase):
    def test_a_plain_entry_has_no_provenance(self):
        entry = LogEntry(text="You pick up 1x Wheat")
        self.assertEqual(entry.claim_id, "")
        self.assertIsNone(entry.confidence_at_entry)

    def test_an_entry_from_an_older_save_backfills(self):
        entry = LogEntry(text="You pick up 1x Wheat", category="gain", tick=5)
        state = dict(entry.__dict__)
        for gone in ("claim_id", "knowledge_source", "source_entity_id", "confidence_at_entry"):
            state.pop(gone)
        restored = LogEntry.__new__(LogEntry)
        restored.__setstate__(state)
        self.assertEqual(restored.claim_id, "")
        self.assertIsNone(restored.confidence_at_entry)
        self.assertEqual(restored.text, "You pick up 1x Wheat")

    def test_an_entry_round_trips_through_pickle(self):
        entry = LogEntry(text="Mara told you", claim_id="c1", knowledge_source="told",
                         source_entity_id=7, confidence_at_entry=0.8)
        restored = pickle.loads(pickle.dumps(entry))
        self.assertEqual(restored.claim_id, "c1")
        self.assertEqual(restored.confidence_at_entry, 0.8)


class TestTheWorldWritesTheJournal(unittest.TestCase):
    """End to end: the player learns something and their log says how."""

    def setUp(self):
        self.world = fresh_world(seed=19, pre_simulate=False)
        self.world.chat_log_entries.clear()
        self.world.player.knowledge.known_history_facts.clear()
        self.record = _Assault()

    def _journal(self):
        return [e for e in self.world.chat_log_entries if e.knowledge_source]

    def test_witnessing_writes_a_first_hand_line(self):
        self.world.knowledge_system.learn_history_record(
            self.world.player, self.record, source_type="witnessed", confidence=1.0, tick=100)
        entries = self._journal()
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].text.startswith("You saw"), entries[0].text)
        self.assertEqual(entries[0].knowledge_source, "witnessed")
        self.assertEqual(entries[0].confidence_at_entry, 1.0)

    def test_being_told_names_the_teller(self):
        teller = self.world.village_npcs[0]
        teller.knowledge.learn_history_record(self.record, "witnessed", 1.0, 100)
        teller.knowledge.known_events[self.record.id] = self.record

        self.world.knowledge_system.share_event(teller, self.world.player, self.record)

        entries = self._journal()
        self.assertEqual(len(entries), 1)
        self.assertIn(teller.name, entries[0].text)
        self.assertEqual(entries[0].source_entity_id, teller.id)

    def test_a_villager_learning_something_writes_nothing(self):
        """Only the player has a journal."""
        self.world.knowledge_system.learn_history_record(
            self.world.village_npcs[0], self.record, source_type="witnessed",
            confidence=1.0, tick=100)
        self.assertEqual(self._journal(), [])


if __name__ == "__main__":
    unittest.main()
