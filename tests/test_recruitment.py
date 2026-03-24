import unittest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import engine
from simulation.systems.conversation_foundation import evaluate_service_request, try_recruit_entity

class TestRecruitmentRequests(unittest.TestCase):
    def setUp(self):
        self.world = object.__new__(engine.World)
        self.world.player = engine.Player(10, 10)
        self.world.game_time = 0
        self.world.village_npcs = []
        self.world.npcs = []
        self.world.get_entity_by_id = lambda eid: next((n for n in self.world.village_npcs + [self.world.player] if n.id == eid), None)

        self.npc = engine.NPC(x=9, y=10, name="Recruit")
        self.world.village_npcs.append(self.npc)

        self.mock_profile = SimpleNamespace(stance="neutral", openness=0.7)

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_evaluate_service_request_accepts_accompany_with_good_relationship(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 50

        # Test default distrust (0)
        result = evaluate_service_request(self.world, self.world.player, self.npc, "accompany")
        self.assertEqual(result, "accept")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_evaluate_service_request_refuses_accompany_with_low_relationship(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 20

        result = evaluate_service_request(self.world, self.world.player, self.npc, "accompany")
        self.assertEqual(result, "refuse")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_evaluate_service_request_refuses_accompany_with_high_distrust(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 80
        self.npc.get_distrust_towards = lambda req: 30 # High distrust

        result = evaluate_service_request(self.world, self.world.player, self.npc, "accompany")
        self.assertEqual(result, "refuse")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_evaluate_service_request_guard_requires_higher_relationship_than_accompany(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 50 # Enough for accompany, but not guard for a non-guard
        self.npc.economic.profession = "Farmer"

        accompany_result = evaluate_service_request(self.world, self.world.player, self.npc, "accompany")
        guard_result = evaluate_service_request(self.world, self.world.player, self.npc, "guard")

        self.assertEqual(accompany_result, "accept")
        self.assertEqual(guard_result, "refuse")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_evaluate_service_request_guard_accepts_guards_with_lower_relationship(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 40 # Enough for accompany, but not guard for a non-guard, BUT guard for a guard
        self.npc.economic.profession = "Guard"

        guard_result = evaluate_service_request(self.world, self.world.player, self.npc, "guard")

        self.assertEqual(guard_result, "accept")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_evaluate_service_request_refuses_if_hostile_or_fearful(self, mock_eval):
        self.mock_profile.stance = "hostile"
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 90

        result = evaluate_service_request(self.world, self.world.player, self.npc, "accompany")
        self.assertEqual(result, "refuse")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_try_recruit_entity_applies_state_change_if_accepted(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 60

        success = try_recruit_entity(self.world, self.world.player, self.npc, "accompany")

        self.assertTrue(success)
        self.assertEqual(self.npc.social.follow_target_id, self.world.player.id)
        self.assertEqual(self.npc.social.follow_role, "accompany")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_npc_can_recruit_npc(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        requester_npc = engine.NPC(x=8, y=10, name="Requester")
        self.world.village_npcs.append(requester_npc)

        self.npc.social.relationships[requester_npc.id] = 70 # Needs to be > 65 for guard role for non-guard

        success = try_recruit_entity(self.world, requester_npc, self.npc, "guard")

        self.assertTrue(success)
        self.assertEqual(self.npc.social.follow_target_id, requester_npc.id)
        self.assertEqual(self.npc.social.follow_role, "guard")

    @patch("simulation.systems.conversation_foundation.evaluate_conversation_foundation")
    def test_refuses_if_already_following_someone_else(self, mock_eval):
        mock_eval.return_value = self.mock_profile
        self.npc.social.relationships[self.world.player.id] = 90
        self.npc.social.follow_target_id = 999 # Following someone else

        result = evaluate_service_request(self.world, self.world.player, self.npc, "accompany")
        self.assertEqual(result, "refuse")

    def test_engine_fallback_dialogue_triggers_accompany(self):
        # We need to test the actual engine hook.
        # Set up conditions for acceptance
        self.npc.social.relationships[self.world.player.id] = 80

        # We don't want to run the full evaluate_conversation_foundation as it needs a fully built world
        # We must mock it where it is imported in engine
        with patch("simulation.systems.conversation_foundation.evaluate_service_request", return_value="accept"):
            line, goal = self.world._fallback_dialogue_continue(self.npc, "follow me")

        self.assertEqual(goal, "start_accompany")

        # Test handling the goal
        self.world._handle_npc_social_goal(self.npc, self.world.player, "start_accompany")
        self.assertEqual(self.npc.social.follow_target_id, self.world.player.id)
        self.assertEqual(self.npc.social.follow_role, "accompany")

    def test_engine_fallback_dialogue_triggers_guard(self):
        self.npc.social.relationships[self.world.player.id] = 80

        with patch("simulation.systems.conversation_foundation.evaluate_service_request", return_value="accept"):
            line, goal = self.world._fallback_dialogue_continue(self.npc, "guard me")

        self.assertEqual(goal, "start_guard")

        self.world._handle_npc_social_goal(self.npc, self.world.player, "start_guard")
        self.assertEqual(self.npc.social.follow_target_id, self.world.player.id)
        self.assertEqual(self.npc.social.follow_role, "guard")

    def test_engine_fallback_dialogue_refuses_when_not_accepted(self):
        with patch("simulation.systems.conversation_foundation.evaluate_service_request", return_value="refuse"):
            line, goal = self.world._fallback_dialogue_continue(self.npc, "follow me")
            self.assertEqual(goal, "end_conversation")

            line, goal = self.world._fallback_dialogue_continue(self.npc, "guard me")
            self.assertEqual(goal, "end_conversation")
