"""Being talked about changes how people see you - but only so far.

Until now a villager could be certain a man was a thief and think no worse of
him for it. Reputation was fed only by known_memories, which come from having
been there; what somebody had merely been *told* touched nothing.

That is the half that makes an innocent man's problem real. Somebody who
believes the miller did it thinks less of the miller, and since a belief can be
wrong, a man can acquire a reputation he did not earn.

The reason this is dangerous, and the reason it is damped:

    distortion picks its scapegoat from people the listener already dislikes.

So if a single rumour could freely lower somebody's standing, being disliked
would make you likelier to be blamed, which would make you more disliked, which
would make you likelier to be blamed. A village would converge on hating
whoever it already hated least, faster and faster, and every missing chicken
would end up being the miller's fault.

Two things stop that. Hearsay is worth a fraction of having been there, and
until a second independent person says the same thing it is worth half of even
that. One person's grudge cannot compound on its own.

    witnessed          0    (already counted as a memory - not twice)
    official record  -22.5  of -25
    told, two sources -7.0
    told, one source  -3.5
    overheard         -2.0
"""

import unittest

from entities.social import (
    KnownHistoryFact,
    RECORD_REPUTATION_SCORES,
    hearsay_reputation_weight,
)
from tests.world_cache import fresh_world

MILLER = 7


def _fact(**overrides):
    base = dict(
        source_record_id="rec-1", record_type="crime_recorded",
        subject_entity_ids=(MILLER,), known_at_tick=0,
        source_type="told", confidence=0.8, heard_from_ids=(1,),
    )
    base.update(overrides)
    return KnownHistoryFact(**base)


class TestTheEvidenceHierarchy(unittest.TestCase):
    def test_witnessing_adds_nothing_here(self):
        """It is already counted as a memory. Twice would be wrong."""
        self.assertEqual(hearsay_reputation_weight(_fact(source_type="witnessed",
                                                         confidence=1.0)), 0.0)

    def test_stronger_evidence_counts_for_more(self):
        official = hearsay_reputation_weight(_fact(source_type="official_record", confidence=1.0))
        told = hearsay_reputation_weight(_fact(source_type="told"))
        overheard = hearsay_reputation_weight(_fact(source_type="overheard"))
        self.assertGreater(official, told)
        self.assertGreater(told, overheard)
        self.assertGreater(overheard, 0.0)

    def test_corroboration_is_worth_double(self):
        one = hearsay_reputation_weight(_fact(heard_from_ids=(1,)))
        two = hearsay_reputation_weight(_fact(heard_from_ids=(1, 2)))
        self.assertAlmostEqual(two, one * 2, places=6)

    def test_a_written_record_does_not_need_a_second_teller(self):
        """Being written down is what it has instead of a witness."""
        alone = hearsay_reputation_weight(
            _fact(source_type="official_record", confidence=1.0, heard_from_ids=()))
        self.assertAlmostEqual(alone, 0.9, places=6)

    def test_being_less_sure_counts_for_less(self):
        self.assertGreater(hearsay_reputation_weight(_fact(confidence=0.9)),
                           hearsay_reputation_weight(_fact(confidence=0.3)))


class TestTheLoopCannotRunAway(unittest.TestCase):
    """The property the whole damping exists for."""

    def test_one_rumour_cannot_outweigh_having_been_there(self):
        witnessed = abs(RECORD_REPUTATION_SCORES["crime_recorded"])
        rumour = abs(RECORD_REPUTATION_SCORES["crime_recorded"]
                     * hearsay_reputation_weight(_fact(heard_from_ids=(1,))))
        self.assertLess(rumour, witnessed / 4,
                        "a single rumour moves standing too close to what seeing it does")

    def test_even_corroborated_hearsay_stays_below_first_hand(self):
        witnessed = abs(RECORD_REPUTATION_SCORES["crime_recorded"])
        corroborated = abs(RECORD_REPUTATION_SCORES["crime_recorded"]
                           * hearsay_reputation_weight(_fact(heard_from_ids=(1, 2, 3))))
        self.assertLess(corroborated, witnessed)

    def test_a_death_does_not_disgrace_its_subject(self):
        """The subject of a death record is usually the person who died."""
        self.assertNotIn("entity_death", RECORD_REPUTATION_SCORES)
        self.assertNotIn("npc_birth", RECORD_REPUTATION_SCORES)


class TestItActuallyMovesStanding(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=29, pre_simulate=False)
        # Not just the first two villagers: get_reputation_towards returns 0 for
        # anyone whose identity is concealed, and a villager wearing a hood
        # counts. That is a real feature - a disguise works - and it silently
        # made the first version of these tests measure nothing.
        plain = [n for n in self.world.village_npcs if not n.is_identity_concealed()]
        self.observer, self.accused, self.bystander = plain[0], plain[1], plain[2]
        self.observer.knowledge.known_history_facts.clear()
        self.observer.knowledge.known_memories.clear()

    def _believe(self, **overrides):
        fact = _fact(subject_entity_ids=(self.accused.id,), **overrides)
        self.observer.knowledge.known_history_facts[fact.source_record_id] = fact

    def test_hearing_of_a_crime_lowers_your_opinion(self):
        before = self.observer.knowledge.get_reputation_towards(self.accused)
        self._believe()
        after = self.observer.knowledge.get_reputation_towards(self.accused)
        self.assertLess(after, before)

    def test_an_innocent_man_can_acquire_a_reputation(self):
        """The whole point: they need not have done it."""
        self._believe(heard_from_ids=(1, 2))
        self.assertLess(self.observer.knowledge.get_reputation_towards(self.accused), 0)

    def test_hearing_about_a_trade_deal_does_not(self):
        self._believe(record_type="trade_deal")
        self.assertEqual(self.observer.knowledge.get_reputation_towards(self.accused), 0)

    def test_someone_you_have_heard_nothing_about_is_unaffected(self):
        self._believe()
        self.assertEqual(self.observer.knowledge.get_reputation_towards(self.bystander), 0)


if __name__ == "__main__":
    unittest.main()
