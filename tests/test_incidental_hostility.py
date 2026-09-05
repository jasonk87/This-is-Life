import unittest
from unittest import mock

import engine
from engine import NPC, World
from entities.base import NPC_HOSTILITY_GRACE_TICKS
from simulation.systems.illness import SICK_STATUS_EFFECT, WORSENING_INTERVAL_TICKS
from simulation.systems.survival import apply_temperature_effects
from tests.world_cache import fresh_world


class TestTakeDamageHostilityFlag(unittest.TestCase):
    """Regression tests for the bug found during the population-balance
    simulation: NPC.take_damage's generic fallback used to flag ANY
    non-lethal hit on a non-Creature NPC as is_hostile_to_player, with no
    regard for what actually caused the damage. Status-effect damage
    (illness worsening, Freezing/Overheating) routed through this exact
    path, so a sick or cold villager could become permanently "hostile" to
    a player who was never involved."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=61, pre_simulate=False)

    def _make_npc(self, name="Villager"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.economic.profession = "Farmer"
        return npc

    def test_apply_hostility_false_does_not_flag_hostile(self):
        npc = self._make_npc()
        self.assertFalse(npc.combat.is_hostile_to_player)

        npc.take_damage(1, world=self.world, apply_hostility=False)

        self.assertFalse(npc.combat.is_hostile_to_player)
        self.assertIsNone(npc.combat.hostility_grace_expires_tick)

    def test_default_still_flags_hostile_for_real_combat(self):
        """Control case: the default (apply_hostility=True) must keep
        working exactly as before for genuine combat damage."""
        npc = self._make_npc()
        self.assertFalse(npc.combat.is_hostile_to_player)

        npc.take_damage(1, world=self.world)

        self.assertTrue(npc.combat.is_hostile_to_player)

    def test_default_combat_hit_sets_a_grace_expiry(self):
        npc = self._make_npc()
        self.world.game_time = 5000

        npc.take_damage(1, world=self.world)

        self.assertEqual(npc.combat.hostility_grace_expires_tick, 5000 + NPC_HOSTILITY_GRACE_TICKS)

    def test_lethal_hit_does_not_touch_hostility_flag(self):
        npc = self._make_npc()
        npc.combat.hp = 1

        killed = npc.take_damage(999, world=self.world, apply_hostility=False)

        self.assertTrue(killed)
        self.assertTrue(npc.physical.is_dead)
        self.assertFalse(npc.combat.is_hostile_to_player)

    def test_illness_worsening_damage_does_not_flag_hostile(self):
        """End-to-end: an untreated sick NPC taking worsening damage via the
        real illness.py code path must not become hostile to the player."""
        from simulation.systems.illness import update_entity_illness

        npc = self._make_npc()
        npc.physical.status_effects.append(SICK_STATUS_EFFECT)
        npc.physical.sickness = 70
        self.world.game_time = WORSENING_INTERVAL_TICKS

        with mock.patch("simulation.systems.illness.random.random", return_value=0.0):
            update_entity_illness(self.world, npc)

        self.assertFalse(npc.combat.is_hostile_to_player)

    def test_freezing_damage_does_not_flag_npc_hostile(self):
        npc = self._make_npc()
        npc.physical.status_effects.append("Freezing")
        self.world.game_time = 0  # ticks_for_temp_damage divides 0 evenly

        apply_temperature_effects(self.world, npc, is_player=False)

        self.assertFalse(npc.combat.is_hostile_to_player)

    def test_overheating_damage_does_not_flag_npc_hostile(self):
        npc = self._make_npc()
        npc.physical.status_effects.append("Overheating")
        self.world.game_time = 0

        apply_temperature_effects(self.world, npc, is_player=False)

        self.assertFalse(npc.combat.is_hostile_to_player)

    def test_freezing_damage_on_player_does_not_crash(self):
        """Player.take_damage now accepts (but ignores) apply_hostility, so
        the shared apply_temperature_effects call site works for both entity
        types without an is_player branch."""
        self.world.player.physical.status_effects.append("Freezing")
        self.world.game_time = 0

        try:
            apply_temperature_effects(self.world, self.world.player, is_player=True)
        except TypeError as exc:
            self.fail(f"apply_temperature_effects raised TypeError on the player: {exc}")


class TestDecayIncidentalNpcHostility(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=63, pre_simulate=False)
        self.world.player.x = 500
        self.world.player.y = 500

    def _make_hostile_npc(self, *, grace_expires_tick, task=engine.TaskType.IDLE):
        npc = NPC(0, 0, name="Villager", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.economic.profession = "Farmer"
        npc.combat.is_hostile_to_player = True
        npc.combat.hostility_grace_expires_tick = grace_expires_tick
        npc.schedule.current_task = task
        return npc

    def test_clears_hostility_once_grace_expires_and_npc_is_far_from_player(self):
        npc = self._make_hostile_npc(grace_expires_tick=100, task="combat_action_hold_position")
        self.world.game_time = 200  # past expiry
        npc.x, npc.y = 0, 0  # far from player at (500, 500)

        self.world._decay_incidental_npc_hostility(npc)

        self.assertFalse(npc.combat.is_hostile_to_player)
        self.assertIsNone(npc.combat.hostility_grace_expires_tick)
        self.assertEqual(npc.schedule.current_task, engine.TaskType.IDLE)

    def test_does_not_clear_before_grace_expires(self):
        npc = self._make_hostile_npc(grace_expires_tick=100000)
        self.world.game_time = 200
        npc.x, npc.y = 0, 0

        self.world._decay_incidental_npc_hostility(npc)

        self.assertTrue(npc.combat.is_hostile_to_player)

    def test_does_not_clear_while_still_near_the_player(self):
        npc = self._make_hostile_npc(grace_expires_tick=100)
        self.world.game_time = 200
        npc.x, npc.y = self.world.player.x + 1, self.world.player.y  # well within the safe radius

        self.world._decay_incidental_npc_hostility(npc)

        self.assertTrue(npc.combat.is_hostile_to_player)

    def test_deliberate_hostility_with_no_grace_field_never_decays(self):
        """Raider/wanted-pursuit/guard-bounty/wolf-desperation hostility sets
        is_hostile_to_player directly and never populates
        hostility_grace_expires_tick - this must be left alone forever,
        regardless of how much game time passes or how far the NPC is."""
        npc = NPC(0, 0, name="Raider", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.economic.profession = "Farmer"
        npc.combat.is_hostile_to_player = True
        npc.combat.hostility_grace_expires_tick = None
        self.world.game_time = 10_000_000
        npc.x, npc.y = 0, 0

        self.world._decay_incidental_npc_hostility(npc)

        self.assertTrue(npc.combat.is_hostile_to_player)

    def test_non_hostile_npc_is_a_no_op(self):
        npc = NPC(0, 0, name="Peaceful", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.combat.is_hostile_to_player = False
        npc.combat.hostility_grace_expires_tick = 1
        self.world.game_time = 10

        self.world._decay_incidental_npc_hostility(npc)  # no exception

        self.assertFalse(npc.combat.is_hostile_to_player)

    def test_wired_into_update_npc_schedules(self):
        """Full pipeline: _update_npc_schedules calls the decay check for
        every living NPC each pass."""
        npc = self._make_hostile_npc(grace_expires_tick=100, task="combat_action_hold_position")
        npc.x, npc.y = 0, 0
        self.world.village_npcs.append(npc)
        self.world.game_time = 200
        # Keep this test scoped to the decay wiring - pin the schedule's
        # last-updated tick so the low-frequency scheduling block further
        # down _update_npc_schedules (job assignment, FOV recompute, etc.,
        # unrelated to this fix) doesn't also run against a minimally
        # constructed NPC with no home/work building.
        npc.schedule.game_time_last_updated = self.world.game_time

        self.world._update_npc_schedules()

        self.assertFalse(npc.combat.is_hostile_to_player)


if __name__ == "__main__":
    unittest.main()
