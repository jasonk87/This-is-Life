import unittest
from unittest import mock

import engine
from engine import NPC, World
from simulation.systems.scheduling import (
    GRUDGE_ESCALATION_MIN_AGE_DAYS,
    GRUDGE_ESCALATION_SEVERITY_THRESHOLD,
    GRUDGE_SABOTAGE_SEVERITY_THRESHOLD,
    run_npc_grudge_escalation_policy,
)
from tests.world_cache import fresh_world


class TestGrudgeEscalationEligibility(unittest.TestCase):
    """run_npc_grudge_escalation_policy should only ever act on rare,
    severe, long-held NPC-on-NPC grudges - not player-directed grudges
    (handled elsewhere), fresh grudges, or mild ones."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=401, pre_simulate=False)

    def _npc(self, name="NPC"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def test_player_directed_grudge_is_never_escalated_here(self):
        npc = self._npc("A")
        npc.add_grudge(
            self.world.player.id, "unpaid wages",
            severity=100, current_day=0, decay_days=999, persistent=True,
        )
        # Even with current_day far past the age bar and random forced to
        # always trigger, a player-targeted grudge must be skipped - that's
        # run_npc_grudge_suspicion_policy's job.
        with mock.patch("simulation.systems.scheduling.random.random", return_value=0.0):
            triggered = run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS + 10
            )
        self.assertFalse(triggered)

    def test_grudge_below_severity_threshold_is_not_escalated(self):
        npc = self._npc("A")
        target = self._npc("B")
        npc.add_grudge(
            target.id, "annoyance",
            severity=GRUDGE_ESCALATION_SEVERITY_THRESHOLD - 1,
            current_day=0, decay_days=999, persistent=True,
        )
        with mock.patch("simulation.systems.scheduling.random.random", return_value=0.0):
            triggered = run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS + 10
            )
        self.assertFalse(triggered)

    def test_grudge_younger_than_min_age_is_not_escalated(self):
        npc = self._npc("A")
        target = self._npc("B")
        npc.add_grudge(
            target.id, "betrayal",
            severity=100, current_day=0, decay_days=999, persistent=True,
        )
        with mock.patch("simulation.systems.scheduling.random.random", return_value=0.0):
            triggered = run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS - 1
            )
        self.assertFalse(triggered)

    def test_dead_target_is_skipped(self):
        npc = self._npc("A")
        target = self._npc("B")
        target.physical.is_dead = True
        npc.add_grudge(
            target.id, "betrayal",
            severity=100, current_day=0, decay_days=999, persistent=True,
        )
        with mock.patch("simulation.systems.scheduling.random.random", return_value=0.0):
            triggered = run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS + 10
            )
        self.assertFalse(triggered)

    def test_eligible_grudge_still_needs_the_random_roll_to_succeed(self):
        npc = self._npc("A")
        target = self._npc("B")
        npc.add_grudge(
            target.id, "betrayal",
            severity=100, current_day=0, decay_days=999, persistent=True,
        )
        # random.random() returning 1.0 always fails the
        # "< GRUDGE_ESCALATION_CHANCE_PER_CHECK" style roll.
        with mock.patch("simulation.systems.scheduling.random.random", return_value=1.0):
            triggered = run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS + 10
            )
        self.assertFalse(triggered)


class TestGrudgeEscalationGossip(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=402, pre_simulate=False)

    def _npc(self, name="NPC"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def test_moderate_severity_grudge_escalates_to_gossip_not_sabotage(self):
        npc = self._npc("A")
        target = self._npc("B")
        target.economic.money = 100
        npc.add_grudge(
            target.id, "unpaid wages",
            severity=GRUDGE_ESCALATION_SEVERITY_THRESHOLD,  # below the sabotage tier
            current_day=0, decay_days=999, persistent=True,
        )

        with mock.patch("simulation.systems.scheduling.random.random", return_value=0.0):
            triggered = run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS + 10
            )

        self.assertTrue(triggered)
        # Gossip doesn't touch money.
        self.assertEqual(target.economic.money, 100)
        # The gossiper now personally knows a malicious_gossip memory about the target.
        gossip_memories = [
            m for m in npc.knowledge.known_memories.values()
            if m.event_type == "malicious_gossip" and m.subject_id == target.id
        ]
        self.assertEqual(len(gossip_memories), 1)
        # And it actually damages the target's reputation in the gossiper's eyes.
        self.assertLess(npc.knowledge.get_reputation_towards(target), 0)


class TestGrudgeEscalationSabotage(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=403, pre_simulate=False)

    def _npc(self, name="NPC"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def test_extreme_severity_grudge_can_escalate_to_sabotage(self):
        npc = self._npc("A")
        target = self._npc("B")
        npc.economic.money = 0
        target.economic.money = 100
        npc.add_grudge(
            target.id, "betrayal",
            severity=GRUDGE_SABOTAGE_SEVERITY_THRESHOLD,
            current_day=0, decay_days=999, persistent=True,
        )

        # First random() call is the base escalation-chance roll, second is
        # the sabotage-vs-gossip tier roll - force both to succeed.
        with mock.patch("simulation.systems.scheduling.random.random", return_value=0.0):
            triggered = run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS + 10
            )

        self.assertTrue(triggered)
        self.assertEqual(target.economic.money, 85)  # capped theft of 15
        self.assertEqual(npc.economic.money, 15)
        sabotage_memories = [
            m for m in target.knowledge.known_memories.values()
            if m.event_type == "petty_sabotage" and m.subject_id == npc.id
        ]
        self.assertEqual(len(sabotage_memories), 1)
        self.assertLess(target.knowledge.get_reputation_towards(npc), 0)

    def test_sabotage_never_steals_more_than_the_target_has(self):
        npc = self._npc("A")
        target = self._npc("B")
        npc.economic.money = 0
        target.economic.money = 5  # less than the max steal amount
        npc.add_grudge(
            target.id, "betrayal",
            severity=GRUDGE_SABOTAGE_SEVERITY_THRESHOLD,
            current_day=0, decay_days=999, persistent=True,
        )

        with mock.patch("simulation.systems.scheduling.random.random", return_value=0.0):
            run_npc_grudge_escalation_policy(
                self.world, npc, current_day=GRUDGE_ESCALATION_MIN_AGE_DAYS + 10
            )

        self.assertEqual(target.economic.money, 0)
        self.assertEqual(npc.economic.money, 5)


if __name__ == "__main__":
    unittest.main()
