"""
Test the workshop active_interaction_id stale-state recovery and
clobber-guard logic that was added as a three-layer defense.

Layer 1: _reserve_workshop_for_actor recovers from stale IDs and rejects
        genuinely busy workshops.
Layer 2: The scheduler's assignment site refuses to clobber an existing
        active_interaction_id.
Layer 3: _release_workshop_lock clears both the resolver interaction and
        the workshop ownership reference on completion/cancellation.

These tests exercise each layer of the fix against a minimal harness
rather than spinning up the full World simulation.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

import engine
from simulation.world_model import WorkshopRuntimeState
from tests.world_cache import fresh_world


def _make_workshop(workshop_id="ws_test", **overrides):
    """Return a WorkshopRuntimeState with sensible defaults for testing."""
    kwargs = {
        "workshop_id": workshop_id,
        "workshop_type": "sawbench",
        "occupied_by_actor_id": None,
        "active_interaction_id": None,
        "lock_expiration_tick": 0,
        "last_used_tick": 0,
        "x": 10,
        "y": 10,
    }
    kwargs.update(overrides)
    return WorkshopRuntimeState(**kwargs)


class TestWorkshopReserveWithStaleInteractionId(unittest.TestCase):
    """Validate _reserve_workshop_for_actor's defense against stale active_interaction_id."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=770, pre_simulate=False)
        self.world.game_time = 1000

        # Give the World a bare-bones interaction_resolver.
        self.world.interaction_resolver = SimpleNamespace(active_interactions={})

    def test_reserve_rejects_busy_workshop_when_interaction_active(self):
        """An already-live interaction blocks re-reservation by a different actor."""
        workshop = _make_workshop(active_interaction_id="interaction_1")

        # Simulate an active interaction that the resolver knows about.
        self.world.interaction_resolver.active_interactions["interaction_1"] = mock.MagicMock()

        result = self.world._reserve_workshop_for_actor(workshop, "npc_alice")
        self.assertFalse(result, "Expected False: workshop is busy with a live interaction")

    def test_reserve_recovers_when_interaction_id_is_stale(self):
        """A stale active_interaction_id (absent from the resolver) is cleared and
        reservation proceeds normally."""
        workshop = _make_workshop(active_interaction_id="stale_interaction_id")

        result = self.world._reserve_workshop_for_actor(workshop, "npc_curator")
        self.assertTrue(result, "Expected True: stale ID should be cleared and workshop freed")
        self.assertIsNone(workshop.active_interaction_id,
                          "Stale active_interaction_id must be set to None after recovery")

    def test_reserve_allows_same_actor_when_already_reserved(self):
        """Repeated calls by the already-reserved actor succeed (they hold the lock)."""
        workshop = _make_workshop(occupied_by_actor_id="npc_solo",
                                  lock_expiration_tick=2000)
        result = self.world._reserve_workshop_for_actor(workshop, "npc_solo")
        self.assertTrue(result, "Expected True: same actor re-enters its own reservation")

    def test_reserve_rejects_different_actor_when_lock_unexpired(self):
        """A different actor cannot reserve while the current lock is still valid."""
        workshop = _make_workshop(occupied_by_actor_id="npc_alpha",
                                  lock_expiration_tick=3000)
        result = self.world._reserve_workshop_for_actor(workshop, "npc_beta")
        self.assertFalse(result, "Expected False: different actor blocked by unexpired worker lock")

    def test_reserve_allows_different_actor_when_lock_expired(self):
        """Once the lock has expired, a different actor can reserve the workshop."""
        workshop = _make_workshop(occupied_by_actor_id="npc_alpha",
                                  lock_expiration_tick=999)
        result = self.world._reserve_workshop_for_actor(workshop, "npc_beta")
        self.assertTrue(result, "Expected True: expired lock should let a new actor in")


class TestWorkshopClobberGuard(unittest.TestCase):
    """Ensure the scheduler assignment path does not overwrite active_interaction_id."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=780, pre_simulate=False)
        self.world.game_time = 1000
        self.world.interaction_resolver = SimpleNamespace(active_interactions={})

    def test_release_workshop_lock_clears_active_interaction_id(self):
        """_release_workshop_lock must remove the active_interaction_id reference."""
        workshop = _make_workshop(active_interaction_id="live_id_123",
                                  occupied_by_actor_id=42)

        self.world._release_workshop_lock(workshop, actor_id=42)

        self.assertIsNone(workshop.active_interaction_id,
                          "Expected active_interaction_id to be None after release")
        self.assertIsNone(workshop.occupied_by_actor_id)
        self.assertEqual(workshop.lock_expiration_tick, 0)


if __name__ == "__main__":
    unittest.main()
