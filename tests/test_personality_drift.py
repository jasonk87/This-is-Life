import unittest
from unittest import mock

import engine
from engine import NPC, World
from entities.base import TRAIT_DRIFT_ACTIVATION_THRESHOLD, TRAIT_DRIFT_MAX_ACTIVE_TRAITS


class TestTraitDriftMechanism(unittest.TestCase):
    """NPC.has_trait / record_trait_pressure - the underlying gradual,
    bounded, permanent drift mechanism, independent of any specific event."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=501)

    def _npc(self, name="NPC", personality="villager"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality=personality, player_id=self.world.player.id)

    def test_has_trait_matches_base_personality_substring(self):
        npc = self._npc(personality="wise and lawful")
        self.assertTrue(npc.has_trait("lawful"))
        self.assertFalse(npc.has_trait("greedy"))

    def test_trait_pressure_below_threshold_does_not_activate(self):
        npc = self._npc()
        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD - 1):
            activated = npc.record_trait_pressure("chaotic")
            self.assertFalse(activated)
        self.assertFalse(npc.has_trait("chaotic"))

    def test_trait_activates_exactly_at_threshold(self):
        npc = self._npc()
        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD - 1):
            npc.record_trait_pressure("chaotic")
        self.assertFalse(npc.has_trait("chaotic"))

        activated = npc.record_trait_pressure("chaotic")

        self.assertTrue(activated)
        self.assertTrue(npc.has_trait("chaotic"))

    def test_activated_trait_is_permanent_and_does_not_re_trigger(self):
        npc = self._npc()
        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD):
            npc.record_trait_pressure("chaotic")
        self.assertTrue(npc.has_trait("chaotic"))

        # Further pressure on an already-activated trait is a no-op signal
        # (still returns False - "no NEW activation") but doesn't undo it.
        activated_again = npc.record_trait_pressure("chaotic")
        self.assertFalse(activated_again)
        self.assertTrue(npc.has_trait("chaotic"))

    def test_activation_cap_prevents_a_fourth_distinct_trait(self):
        npc = self._npc()
        traits = ["chaotic", "greedy", "withdrawn", "studious"]
        self.assertEqual(len(traits), TRAIT_DRIFT_MAX_ACTIVE_TRAITS + 1)

        for trait_word in traits:
            for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD):
                npc.record_trait_pressure(trait_word)

        active = [t for t in traits if npc.has_trait(t)]
        self.assertEqual(len(active), TRAIT_DRIFT_MAX_ACTIVE_TRAITS)
        # The first three to reach threshold are the ones that stuck.
        self.assertEqual(active, traits[:TRAIT_DRIFT_MAX_ACTIVE_TRAITS])
        self.assertFalse(npc.has_trait("studious"))

    def test_pressure_on_a_capped_out_trait_keeps_counting_but_never_activates(self):
        npc = self._npc()
        for trait_word in ["chaotic", "greedy", "withdrawn"]:
            for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD):
                npc.record_trait_pressure(trait_word)

        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD + 5):
            npc.record_trait_pressure("studious")

        self.assertFalse(npc.has_trait("studious"))
        self.assertEqual(npc.social.trait_pressure["studious"], TRAIT_DRIFT_ACTIVATION_THRESHOLD + 5)


class TestJailReleaseTraitDrift(unittest.TestCase):
    """World._apply_jail_release_trait_drift - character (existing
    anti-authority lean) takes priority over crime severity; severity only
    decides the outcome for a more neutral/lawful-leaning character."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=502)
        self.world._change_map_tile = mock.MagicMock()
        self.world._update_entity_position = mock.MagicMock(
            side_effect=lambda e, x, y: (setattr(e, "x", x), setattr(e, "y", y))
        )

    def _npc(self, name="NPC", personality="villager"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality=personality, player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def _activate(self, npc, trait_word):
        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD):
            npc.record_trait_pressure(trait_word)

    def test_already_chaotic_npc_hardens_further_regardless_of_low_severity(self):
        npc = self._npc(personality="chaotic drifter")
        npc.schedule.jail_intake_bounty = 30  # theft-tier, would normally reform a neutral NPC

        self.world._apply_jail_release_trait_drift(npc)

        self.assertEqual(npc.social.trait_pressure.get("chaotic", 0), 1)
        self.assertEqual(npc.social.trait_pressure.get("lawful", 0), 0)

    def test_already_aggressive_npc_hardens_toward_chaotic_even_with_low_severity(self):
        npc = self._npc(personality="aggressive brute")
        npc.schedule.jail_intake_bounty = 30

        self.world._apply_jail_release_trait_drift(npc)

        self.assertEqual(npc.social.trait_pressure.get("chaotic", 0), 1)

    def test_neutral_npc_with_low_severity_offense_reforms_toward_lawful(self):
        npc = self._npc(personality="villager")
        npc.schedule.jail_intake_bounty = 30  # theft-tier

        self.world._apply_jail_release_trait_drift(npc)

        self.assertEqual(npc.social.trait_pressure.get("lawful", 0), 1)
        self.assertEqual(npc.social.trait_pressure.get("chaotic", 0), 0)

    def test_neutral_npc_with_high_severity_offense_hardens_toward_chaotic(self):
        npc = self._npc(personality="villager")
        npc.schedule.jail_intake_bounty = 100  # murder-tier

        self.world._apply_jail_release_trait_drift(npc)

        self.assertEqual(npc.social.trait_pressure.get("chaotic", 0), 1)
        self.assertEqual(npc.social.trait_pressure.get("lawful", 0), 0)

    def test_lawful_leaning_npc_with_high_severity_offense_still_hardens(self):
        """Even a lawful-leaning character isn't immune to a genuinely
        severe offense's traumatic/hardening effect."""
        npc = self._npc(personality="lawful villager")
        npc.schedule.jail_intake_bounty = 100

        self.world._apply_jail_release_trait_drift(npc)

        self.assertEqual(npc.social.trait_pressure.get("chaotic", 0), 1)

    def test_intake_bounty_is_captured_at_arrest_and_survives_to_release(self):
        """End-to-end: _serve_npc_jail_time captures bounty, economic.bounty
        is zeroed immediately after, and jail_intake_bounty is what
        _release_npc_from_jail's drift call actually sees."""
        npc = self._npc(personality="villager")
        npc.economic.bounty = 100
        sheriff_office = engine.Building(0, 0, 5, 5, building_type="sheriff_office", category="civic")
        self.world.buildings_by_id[sheriff_office.id] = sheriff_office

        self.world._serve_npc_jail_time(npc)

        self.assertEqual(npc.schedule.jail_intake_bounty, 100)
        self.assertEqual(npc.economic.bounty, 0)

        self.world._release_npc_from_jail(npc)

        # High-severity intake bounty (100) on a neutral character -> chaotic.
        self.assertEqual(npc.social.trait_pressure.get("chaotic", 0), 1)


class TestIllnessRecoveryTraitDrift(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=503)

    def _npc(self, name="NPC", personality="villager"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality=personality, player_id=self.world.player.id)

    def test_greedy_npc_hardens_further_toward_greedy(self):
        npc = self._npc(personality="greedy merchant")
        self.world._apply_illness_recovery_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("greedy", 0), 1)

    def test_brave_npc_becomes_more_studious(self):
        npc = self._npc(personality="brave warrior")
        self.world._apply_illness_recovery_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("studious", 0), 1)

    def test_lazy_npc_gets_a_wake_up_call_toward_lawful(self):
        npc = self._npc(personality="lazy fellow")
        self.world._apply_illness_recovery_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("lawful", 0), 1)

    def test_neutral_npc_defaults_to_greedy_self_preservation(self):
        npc = self._npc(personality="villager")
        self.world._apply_illness_recovery_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("greedy", 0), 1)

    def test_player_is_a_silent_no_op(self):
        try:
            self.world._apply_illness_recovery_trait_drift(self.world.player)
        except Exception as exc:  # noqa: BLE001
            self.fail(f"drift call on player raised: {exc}")


class TestBereavementTraitDrift(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=504)

    def _npc(self, name="NPC", personality="villager"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality=personality, player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def test_aggressive_npc_grief_manifests_as_aggression(self):
        from simulation.systems.social_reaction import _apply_bereavement_trait_drift
        npc = self._npc(personality="aggressive brute")
        _apply_bereavement_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("aggressive", 0), 1)

    def test_lawful_npc_turns_inward_and_withdraws(self):
        from simulation.systems.social_reaction import _apply_bereavement_trait_drift
        npc = self._npc(personality="lawful villager")
        _apply_bereavement_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("withdrawn", 0), 1)

    def test_greedy_npc_sharpens_protective_instinct(self):
        from simulation.systems.social_reaction import _apply_bereavement_trait_drift
        npc = self._npc(personality="greedy merchant")
        _apply_bereavement_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("greedy", 0), 1)

    def test_neutral_npc_defaults_to_withdrawn(self):
        from simulation.systems.social_reaction import _apply_bereavement_trait_drift
        npc = self._npc(personality="villager")
        _apply_bereavement_trait_drift(npc)
        self.assertEqual(npc.social.trait_pressure.get("withdrawn", 0), 1)

    def test_only_fires_for_actual_family_not_just_a_close_friend(self):
        """_store_history_reaction's grief branch should only apply drift
        when the deceased was real family (family_ties), not merely a
        very close friend (the broader _is_close_relation eligibility)."""
        from simulation.systems.social_reaction import _store_history_reaction

        npc = self._npc(personality="villager")
        friend_id = 9999  # not in family_ties at all
        fact = mock.MagicMock()
        reaction = {
            "reaction_type": "grief",
            "target_entity_id": friend_id,
            "score": -20.0,
            "reason": "known_close_death",
        }

        _store_history_reaction(self.world, npc, fact, reaction)

        self.assertEqual(npc.social.trait_pressure, {})

    def test_fires_for_a_real_spouse(self):
        from simulation.systems.social_reaction import _store_history_reaction

        npc = self._npc(personality="villager")
        spouse_id = 12345
        npc.social.family_ties["partner_id"] = spouse_id
        fact = mock.MagicMock()
        reaction = {
            "reaction_type": "grief",
            "target_entity_id": spouse_id,
            "score": -20.0,
            "reason": "known_close_death",
        }

        _store_history_reaction(self.world, npc, fact, reaction)

        self.assertEqual(npc.social.trait_pressure.get("withdrawn", 0), 1)


class TestCrimeVictimizationTraitDrift(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=505)

    def _npc(self, name="NPC", personality="villager"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality=personality, player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def test_lawful_victim_seeks_more_order(self):
        victim = self._npc(personality="lawful villager")
        self.world._apply_crime_victimization_trait_drift(victim)
        self.assertEqual(victim.social.trait_pressure.get("lawful", 0), 1)

    def test_chaotic_victim_hardens_toward_self_reliance_not_the_system(self):
        victim = self._npc(personality="chaotic drifter")
        self.world._apply_crime_victimization_trait_drift(victim)
        self.assertEqual(victim.social.trait_pressure.get("aggressive", 0), 1)
        self.assertEqual(victim.social.trait_pressure.get("lawful", 0), 0)

    def test_brave_victim_hardens_toward_fighting_back(self):
        victim = self._npc(personality="brave adventurer")
        self.world._apply_crime_victimization_trait_drift(victim)
        self.assertEqual(victim.social.trait_pressure.get("aggressive", 0), 1)

    def test_neutral_victim_defaults_to_lawful(self):
        victim = self._npc(personality="villager")
        self.world._apply_crime_victimization_trait_drift(victim)
        self.assertEqual(victim.social.trait_pressure.get("lawful", 0), 1)

    def test_repeated_victimization_via_record_crime_event_eventually_activates(self):
        victim = self._npc(personality="villager")
        suspect = self._npc(name="Suspect", personality="villager")

        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD):
            self.world.record_crime_event(
                crime_kind="theft",
                suspect_id=suspect.id,
                description="Theft witnessed.",
                victim_id=victim.id,
            )

        self.assertTrue(victim.has_trait("lawful"))

    def test_record_crime_event_with_no_victim_does_not_crash(self):
        suspect = self._npc(name="Suspect", personality="villager")
        try:
            self.world.record_crime_event(
                crime_kind="theft",
                suspect_id=suspect.id,
                description="Unattributed theft.",
                victim_id=None,
            )
        except Exception as exc:  # noqa: BLE001
            self.fail(f"record_crime_event with no victim raised: {exc}")


class TestDriftFlowsThroughToExistingGates(unittest.TestCase):
    """Confirms activated (drift-only) traits actually change behavior in
    the pre-existing utility-AI / job-suitability gates, not just internal
    bookkeeping."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=506)

    def _npc(self, name="NPC", personality="villager"):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality=personality, player_id=self.world.player.id)
        self.world.village_npcs.append(npc)
        return npc

    def test_drift_activated_aggressive_trait_boosts_sheriff_job_suitability(self):
        npc_plain = self._npc(name="Plain", personality="villager")
        npc_drifted = self._npc(name="Drifted", personality="villager")
        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD):
            npc_drifted.record_trait_pressure("aggressive")

        sheriff_office = engine.Building(0, 0, 5, 5, building_type="sheriff_office", category="civic")

        with mock.patch("engine.random.randint", return_value=0):
            plain_score = self.world._evaluate_job_suitability(npc_plain, sheriff_office)
            drifted_score = self.world._evaluate_job_suitability(npc_drifted, sheriff_office)

        self.assertGreater(drifted_score, plain_score)

    def test_drift_activated_chaotic_trait_increases_steal_food_appeal(self):
        from simulation.systems.utility_ai import evaluate_needs_utility
        import simulation.systems.utility_ai as utility_ai

        npc = self._npc(personality="villager")
        for _ in range(TRAIT_DRIFT_ACTIVATION_THRESHOLD):
            npc.record_trait_pressure("chaotic")
        npc.economic.money = 0  # no money -> buy_food option unavailable, isolates forage vs steal
        npc.physical.hunger = npc.physical.max_hunger

        with mock.patch.object(utility_ai, "_set_steal_goal") as mock_steal, \
             mock.patch.object(utility_ai, "_set_forage_goal") as mock_forage:
            evaluate_needs_utility(self.world, npc)

        mock_steal.assert_called_once()
        mock_forage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
