import unittest

import engine
from config import DAY_LENGTH_TICKS
from engine import NPC, World
from entities.social import KnowledgeComponent, MemoryEvent


class TestCrimeReputationScoring(unittest.TestCase):
    """Item 5: event_type="crime_witnessed" (the type record_crime_event in
    engine.py always uses for theft/assault/etc.) was previously missing from
    REPUTATION_EVENT_SCORES entirely, so a witnessed crime never touched
    reputation - only unpaid_wages and murder did."""

    def test_crime_witnessed_has_a_reputation_penalty(self):
        self.assertIn("crime_witnessed", KnowledgeComponent.REPUTATION_EVENT_SCORES)
        self.assertEqual(KnowledgeComponent.REPUTATION_EVENT_SCORES["crime_witnessed"], -25)

    def test_crime_witnessed_penalty_is_between_unpaid_wages_and_murder(self):
        scores = KnowledgeComponent.REPUTATION_EVENT_SCORES
        # More severe (more negative) than unpaid_wages, a purely civil/
        # economic wrong, but well short of murder.
        self.assertLess(scores["crime_witnessed"], scores["unpaid_wages"])
        self.assertGreater(scores["crime_witnessed"], scores["murder"])

    def test_get_reputation_towards_applies_crime_witnessed_penalty(self):
        knowledge = KnowledgeComponent()
        memory = MemoryEvent(
            event_type="crime_witnessed",
            subject_id=42,
            target_id=99,
            timestamp=100,
            importance_score=20,
            headline="Witnessed a theft.",
        )
        knowledge.record_event(memory)

        suspect = type("FakeEntity", (), {"id": 42, "is_identity_concealed": lambda self: False})()

        self.assertEqual(knowledge.get_reputation_towards(suspect), -25)

    def test_multiple_witnessed_crimes_stack(self):
        knowledge = KnowledgeComponent()
        for i in range(3):
            knowledge.record_event(MemoryEvent(
                event_type="crime_witnessed",
                subject_id=42,
                target_id=99,
                timestamp=100 + i,
                importance_score=20,
                headline=f"Witnessed crime {i}.",
            ))

        suspect = type("FakeEntity", (), {"id": 42, "is_identity_concealed": lambda self: False})()

        self.assertEqual(knowledge.get_reputation_towards(suspect), -75)

    def test_end_to_end_via_engine_memory_helpers(self):
        """Exercises the real production helpers (World.create_memory_event /
        World.record_memory_event) rather than only the raw dataclasses, to
        confirm the fix reaches an actual witness's opinion of a suspect via
        the same path engine.py's crime-witnessing code uses."""
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        world = World(seed=123)

        suspect = NPC(world.player.x, world.player.y, name="Suspect", dialogue=["Hi"], personality="villager", player_id=world.player.id)
        witness = NPC(world.player.x, world.player.y, name="Witness", dialogue=["Hi"], personality="villager", player_id=world.player.id)

        memory = world.create_memory_event(
            event_type="crime_witnessed",
            subject_id=suspect.id,
            target_id=witness.id,
            importance_score=20,
            headline=f"{witness.name} witnessed {suspect.name} committing theft.",
        )
        self.assertTrue(world.record_memory_event(witness, memory))

        self.assertEqual(witness.knowledge.get_reputation_towards(suspect), -25)


class TestReputationDecay(unittest.TestCase):
    """Reputation redemption: get_reputation_towards previously summed every
    known memory forever with no way for an NPC who stopped committing
    crimes to ever rebuild trust. current_tick is an opt-in parameter (None
    by default, matching the old always-full-weight behavior) so existing
    fixed-timestamp callers/tests above are unaffected; production
    call-sites in engine.py now pass self.game_time."""

    GRACE_TICKS = KnowledgeComponent.REPUTATION_DECAY_GRACE_DAYS * DAY_LENGTH_TICKS
    HALFLIFE_TICKS = KnowledgeComponent.REPUTATION_DECAY_HALFLIFE_DAYS * DAY_LENGTH_TICKS

    def _suspect(self, entity_id=42):
        return type("FakeEntity", (), {"id": entity_id, "is_identity_concealed": lambda self: False})()

    def test_omitting_current_tick_preserves_old_always_full_weight_behavior(self):
        knowledge = KnowledgeComponent()
        knowledge.record_event(MemoryEvent(
            event_type="murder", subject_id=42, target_id=99,
            timestamp=0, importance_score=95,
        ))
        # An extremely old event, but current_tick is never passed - should
        # be identical to the pre-decay behavior (full -50, no discount).
        self.assertEqual(knowledge.get_reputation_towards(self._suspect()), -50)

    def test_multiplier_is_full_weight_within_grace_period(self):
        knowledge = KnowledgeComponent()
        multiplier = knowledge._reputation_decay_multiplier(
            current_tick=self.GRACE_TICKS - 1, event_tick=0
        )
        self.assertEqual(multiplier, 1.0)

    def test_multiplier_is_roughly_half_after_one_halflife_past_grace(self):
        knowledge = KnowledgeComponent()
        multiplier = knowledge._reputation_decay_multiplier(
            current_tick=self.GRACE_TICKS + self.HALFLIFE_TICKS, event_tick=0
        )
        self.assertAlmostEqual(multiplier, 0.5, places=6)

    def test_multiplier_never_reaches_zero_even_for_an_ancient_event(self):
        knowledge = KnowledgeComponent()
        # ~1000 game-days later - many half-lives out.
        multiplier = knowledge._reputation_decay_multiplier(
            current_tick=1000 * DAY_LENGTH_TICKS, event_tick=0
        )
        self.assertGreater(multiplier, 0.0)

    def test_old_negative_event_carries_less_weight_than_a_fresh_one(self):
        knowledge = KnowledgeComponent()
        knowledge.record_event(MemoryEvent(
            event_type="crime_witnessed", subject_id=42, target_id=99,
            timestamp=0, importance_score=20,
        ))
        suspect = self._suspect()

        fresh_score = knowledge.get_reputation_towards(suspect, current_tick=self.GRACE_TICKS)
        long_decayed_score = knowledge.get_reputation_towards(
            suspect, current_tick=self.GRACE_TICKS + 3 * self.HALFLIFE_TICKS
        )

        self.assertEqual(fresh_score, -25)
        # Still negative (an NPC's crime doesn't get erased outright)...
        self.assertLess(long_decayed_score, 0)
        # ...but meaningfully faded toward neutral, i.e. real redemption.
        self.assertGreater(long_decayed_score, fresh_score)

    def test_positive_and_negative_events_decay_symmetrically(self):
        """Decay is applied the same way regardless of sign - an old good
        deed fades at the same rate as an old bad one, so a single ancient
        crime can't permanently outweigh a lifetime of good behavior."""
        good_knowledge = KnowledgeComponent()
        good_knowledge.record_event(MemoryEvent(
            event_type="quest_complete", subject_id=1, target_id=99,
            timestamp=0, importance_score=15,
        ))
        bad_knowledge = KnowledgeComponent()
        bad_knowledge.record_event(MemoryEvent(
            event_type="crime_witnessed", subject_id=1, target_id=99,
            timestamp=0, importance_score=20,
        ))
        current_tick = self.GRACE_TICKS + 2 * self.HALFLIFE_TICKS

        good_target = self._suspect(entity_id=1)
        good_fresh = good_knowledge.get_reputation_towards(good_target, current_tick=self.GRACE_TICKS)
        good_decayed = good_knowledge.get_reputation_towards(good_target, current_tick=current_tick)
        bad_fresh = bad_knowledge.get_reputation_towards(good_target, current_tick=self.GRACE_TICKS)
        bad_decayed = bad_knowledge.get_reputation_towards(good_target, current_tick=current_tick)

        # Same ratio of decayed-to-fresh magnitude for both, within rounding.
        good_ratio = good_decayed / good_fresh
        bad_ratio = bad_decayed / bad_fresh
        self.assertAlmostEqual(good_ratio, bad_ratio, places=1)

    def test_multiple_memories_each_decay_by_their_own_age(self):
        """A stale crime and a fresh one about the same suspect shouldn't
        decay in lockstep - only the older one should have faded."""
        knowledge = KnowledgeComponent()
        knowledge.record_event(MemoryEvent(
            event_type="crime_witnessed", subject_id=42, target_id=99,
            timestamp=0, importance_score=20, headline="old crime",
        ))
        current_tick = self.GRACE_TICKS + 3 * self.HALFLIFE_TICKS
        knowledge.record_event(MemoryEvent(
            event_type="crime_witnessed", subject_id=42, target_id=99,
            timestamp=current_tick, importance_score=20, headline="fresh crime",
        ))
        suspect = self._suspect()

        total = knowledge.get_reputation_towards(suspect, current_tick=current_tick)
        # The fresh crime alone would be -25; with the faded old one added
        # on top the total should be more negative than -25 but nowhere
        # near double (-50), since the old one barely counts anymore.
        self.assertLess(total, -25)
        self.assertGreater(total, -40)


if __name__ == "__main__":
    unittest.main()
