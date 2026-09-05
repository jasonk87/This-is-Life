import unittest
from unittest import mock

import engine
from engine import NPC, World
from entities.behaviors import StarvationBehavior
from tests.world_cache import fresh_world


class TestStarvationBehaviorSetsIsDead(unittest.TestCase):
    """Bug-hunt audit item 3b: StarvationBehavior used to kill an entity
    (remove it from village_npcs/npcs via handle_npc_death) without ever
    setting physical.is_dead - confirmed live before this fix. Every other
    death path sets it: NPC.take_damage sets it the instant combat.hp<=0 in
    combat, and the predator-kills-prey/elder-death call sites in engine.py
    set it explicitly right before calling handle_npc_death."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=701, pre_simulate=False)

    def _starving_npc(self):
        npc = NPC(0, 0, name="Starving", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        npc.physical.hunger = npc.physical.max_hunger
        npc.combat.hp = 1
        return npc

    def test_starvation_death_sets_is_dead_true(self):
        npc = self._starving_npc()
        behavior = StarvationBehavior()

        with mock.patch("entities.behaviors.random.random", return_value=0.0):
            killed = behavior.take_turn(npc, self.world)

        self.assertTrue(killed)
        self.assertTrue(npc.physical.is_dead)
        self.assertNotIn(npc, self.world.village_npcs)

    def test_a_stale_reference_after_starvation_death_correctly_reports_dead(self):
        """The whole point of the fix: some OTHER object that still holds a
        reference to this NPC (a relationship dict entry, a memory event
        subject, etc.) should see is_dead=True, not silently treat a
        removed-from-the-world entity as still alive."""
        npc = self._starving_npc()
        witness = NPC(0, 0, name="Witness", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        witness.social.relationships[npc.id] = 50
        stale_reference = npc  # simulates any lingering handle to the entity

        behavior = StarvationBehavior()
        with mock.patch("entities.behaviors.random.random", return_value=0.0):
            behavior.take_turn(npc, self.world)

        self.assertTrue(stale_reference.physical.is_dead)

    def test_below_threshold_hunger_does_not_trigger_starvation(self):
        npc = self._starving_npc()
        npc.physical.hunger = 0
        behavior = StarvationBehavior()

        killed = behavior.take_turn(npc, self.world)

        self.assertFalse(killed)
        self.assertFalse(npc.physical.is_dead)

    def test_starvation_tick_that_does_not_kill_leaves_is_dead_false(self):
        """A starvation-damage tick that DOESN'T bring hp to 0 shouldn't
        touch is_dead at all - only the actual killing blow should."""
        npc = self._starving_npc()
        npc.combat.hp = 100  # survives one -1 tick easily

        with mock.patch("entities.behaviors.random.random", return_value=0.0):
            killed = StarvationBehavior().take_turn(npc, self.world)

        self.assertFalse(killed)
        self.assertFalse(npc.physical.is_dead)
        self.assertIn(npc, self.world.village_npcs)


if __name__ == "__main__":
    unittest.main()
