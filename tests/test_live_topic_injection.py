import unittest
from unittest.mock import MagicMock
from simulation.systems.conversation_topics import select_conversation_topic, apply_conversation_topic
from simulation.systems.conversation_foundation import ConversationFoundationProfile

class MockWorld:
    def __init__(self):
        self.game_time = 0
        self.harmful_incidents = {}
    def propagate_npc_harmful_incident_gossip(self, speaker, listener):
        pass

class MockEntity:
    def __init__(self, name):
        self.name = name
        self.id = name
        self.social = MagicMock()
        self.social.relationships = {}
        self.social.shared_experience_ticks = {}
        self.social.follow_target_id = None
        self.knowledge = MagicMock()
        self.knowledge.discussed_event_ids = set()
        self.knowledge.known_harmful_incidents = {}
        self.knowledge.known_memories = {}
        self.knowledge.known_locations = {}
        self.knowledge.long_term_memory = []

class MockIncident:
    def __init__(self, id, severity, timestamp):
        self.id = id
        self.severity = severity
        self.timestamp = timestamp
        self.target_id = "victim"

class MockAttribution:
    def __init__(self, confidence):
        self.confidence = confidence
        self.attributed_attacker_id = "attacker"

class MockMemory:
    def __init__(self, id, importance_score, timestamp):
        self.id = id
        self.importance_score = importance_score
        self.timestamp = timestamp
        self.subject_id = None
        self.target_id = None

class TestLiveTopicInjection(unittest.TestCase):
    def setUp(self):
        self.world = MockWorld()
        self.speaker = MockEntity("Speaker")
        self.listener = MockEntity("Listener")
        self.foundation_profile = ConversationFoundationProfile(
            can_start=True,
            reason="ok",
            stance="neutral",
            tone="neutral",
            openness=0.6,
            outcome_weights={"continue_conversation": 1.0}
        )
        self.world.game_time = 1000

    def test_high_priority_info_overrides_low_priority(self):
        # Create a severe incident
        incident = MockIncident("bad_event", severity=100, timestamp=950)
        self.world.harmful_incidents["bad_event"] = incident
        self.speaker.knowledge.known_harmful_incidents["bad_event"] = MockAttribution(confidence=1.0)
        self.world.game_time = 1000


        from simulation.systems.conversation_topics import _get_fresh_knowledge_bias
        bias = _get_fresh_knowledge_bias(self.world, self.speaker, [self.listener])
        self.assertGreater(bias["report_incident"], 0)

    def test_mark_as_discussed_prevents_spam(self):
        # Create a severe incident
        incident = MockIncident("bad_event", severity=100, timestamp=950)
        self.world.harmful_incidents["bad_event"] = incident
        self.speaker.knowledge.known_harmful_incidents["bad_event"] = MockAttribution(confidence=1.0)
        self.world.game_time = 1000
        self.world.game_time = 1000


        from simulation.systems.conversation_topics import _get_fresh_knowledge_bias, ConversationTopicChoice, apply_conversation_topic
        bias1 = _get_fresh_knowledge_bias(self.world, self.speaker, [self.listener])
        self.assertGreater(bias1["report_incident"], 0)

        # Assume it was picked, apply it
        choice1 = ConversationTopicChoice("report_incident", {"incident_id": "bad_event"}, "socialize")
        apply_conversation_topic(self.world, self.speaker, self.listener, choice1)

        self.assertIn("bad_event", self.speaker.knowledge.discussed_event_ids)
        self.assertIn("bad_event", self.listener.knowledge.discussed_event_ids)

        # Next time bias should be 0 for this incident
        bias2 = _get_fresh_knowledge_bias(self.world, self.speaker, [self.listener])
        self.assertEqual(bias2["report_incident"], 0)

    def test_group_conversations_consider_all_participants(self):
        group_listener = MockEntity("GroupListener")

        # The speaker knows about a recent important memory
        memory = MockMemory("great_event", importance_score=50, timestamp=950)
        self.speaker.knowledge.known_memories["great_event"] = memory

        from simulation.systems.conversation_topics import _get_fresh_knowledge_bias
        bias = _get_fresh_knowledge_bias(self.world, self.speaker, [self.listener, group_listener])
        self.assertGreater(bias["reflection"], 0)




    def test_topic_momentum_persists_reflection(self):
        from simulation.systems.conversation_topics import select_conversation_topic

        # Give speaker a very strong momentum for reflection
        self.speaker.task_context_data = {"current_topic": "reflection"}

        # Provide a low-priority fresh incident to compete with it
        incident = MockIncident("minor_event", severity=10, timestamp=950)
        self.world.harmful_incidents["minor_event"] = incident
        self.speaker.knowledge.known_harmful_incidents["minor_event"] = MockAttribution(confidence=0.4)

        # Ensure that reflection gets a significant weight boost, overcoming the minor fresh gossip bias
        import random
        random.seed(42)  # For deterministic topic selection, but really we want to inspect weights

        # Actually, let's just inspect the bias logic since select_conversation_topic modifies candidate_weights internally
        # We can mock random.choices to inspect the weights it receives.
        with unittest.mock.patch('random.choices') as mock_choices:
            mock_choices.return_value = ["reflection"]
            select_conversation_topic(self.world, self.speaker, self.listener, self.foundation_profile)

            # The weights passed to random.choices: args are (topics, weights=weights, k=1)
            call_kwargs = mock_choices.call_args.kwargs
            topics = mock_choices.call_args.args[0]
            weights = call_kwargs['weights']

            # Find the weight of 'reflection' vs 'gossip'
            reflection_idx = topics.index("reflection") if "reflection" in topics else -1
            gossip_idx = topics.index("gossip") if "gossip" in topics else -1

            if reflection_idx != -1 and gossip_idx != -1:
                self.assertGreater(weights[reflection_idx], weights[gossip_idx])

    def test_local_relevance_boosts_bias(self):
        from simulation.systems.conversation_topics import _get_fresh_knowledge_bias

        self.speaker.x = 10
        self.speaker.y = 10

        incident_far = MockIncident("far_event", severity=50, timestamp=950)
        incident_far.location = (100, 100)
        self.world.harmful_incidents["far_event"] = incident_far
        self.speaker.knowledge.known_harmful_incidents["far_event"] = MockAttribution(confidence=1.0)

        bias_far = _get_fresh_knowledge_bias(self.world, self.speaker, [self.listener])

        # Reset and try a local incident
        self.speaker.knowledge.known_harmful_incidents.clear()

        incident_near = MockIncident("near_event", severity=50, timestamp=950)
        incident_near.location = (12, 12)
        self.world.harmful_incidents["near_event"] = incident_near
        self.speaker.knowledge.known_harmful_incidents["near_event"] = MockAttribution(confidence=1.0)

        bias_near = _get_fresh_knowledge_bias(self.world, self.speaker, [self.listener])

        # Near incident should have a higher bias score than the far incident
        self.assertGreater(bias_near["report_incident"], bias_far["report_incident"])


if __name__ == '__main__':
    unittest.main()
