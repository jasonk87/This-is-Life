import unittest

import engine
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


if __name__ == "__main__":
    unittest.main()
