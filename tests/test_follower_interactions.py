import unittest
from unittest.mock import patch, MagicMock
import random

import engine
from simulation.systems.scheduling import run_npc_follower_envelope_policy
from simulation.systems.conversation_topics import _choose_reflection_payload

class TestFollowerInteractions(unittest.TestCase):
    def setUp(self):
        self.world = object.__new__(engine.World)
        self.world.player = engine.Player(10, 10)
        self.world.game_time = 0
        self.world.village_npcs = []
        self.world.npcs = []
        self.world.chunk_width = 2
        self.world.chunk_height = 2
        self.world.get_entity_by_id = lambda eid: next((n for n in self.world.village_npcs + [self.world.player] if n.id == eid), None)
        self.world.get_tile_at = MagicMock(return_value=type('obj', (object,), {'passable': True}))

        self.follower = engine.NPC(x=9, y=10, name="Follower")
        self.world.village_npcs.append(self.follower)
        self.follower.social.follow_target_id = self.world.player.id

    def test_follower_envelope_policy_randomly_initiates_conversation_with_target(self):
        self.follower.conversation_cooldown = 0
        self.world.player.conversation_cooldown = 0
        self.follower.conversation_partner_id = None
        self.world.player.conversation_partner_id = None

        with patch("simulation.systems.scheduling.random.random", return_value=0.001):
            run_npc_follower_envelope_policy(self.world, self.follower)

        self.assertEqual(self.follower.conversation_partner_id, self.world.player.id)
        self.assertEqual(self.world.player.conversation_partner_id, self.follower.id)

    def test_choose_reflection_payload_prefers_shared_events(self):
        # Add a non-shared memory with high score
        self.follower.knowledge.record_event(engine.MemoryEvent("event1", subject_id=999, target_id=None, timestamp=1, importance_score=90, headline="Unrelated high score"))

        # Add a shared memory with lower score
        self.follower.knowledge.record_event(engine.MemoryEvent("event2", subject_id=self.world.player.id, target_id=None, timestamp=2, importance_score=50, headline="Shared experience"))

        payload = _choose_reflection_payload(self.follower, self.world.player)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["memory_text"], "Shared experience")

    def test_choose_reflection_payload_falls_back_when_no_shared_events(self):
        # Add only non-shared memories
        self.follower.knowledge.record_event(engine.MemoryEvent("event1", subject_id=999, target_id=None, timestamp=1, importance_score=90, headline="Unrelated high score"))

        payload = _choose_reflection_payload(self.follower, self.world.player)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["memory_text"], "Unrelated high score")
