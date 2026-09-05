import itertools
import unittest
from unittest.mock import MagicMock, patch

import engine
from engine import NPC, World
from simulation.systems import illness
from simulation.systems.illness import (
    SICK_STATUS_EFFECT,
    SICKNESS_THRESHOLD_FEVERISH,
    SICKNESS_THRESHOLD_SICK,
    recover_from_sickness,
    spread_contagion,
    update_entity_illness,
)
from simulation.systems.medical import update_npc_medical_state
from tests.world_cache import fresh_world


class TestSicknessMeterAndStatus(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=41, pre_simulate=False)

    def _make_npc(self, name="Patient", sickness=0):
        npc = NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.physical.sickness = sickness
        return npc

    def test_default_sickness_is_zero(self):
        npc = self._make_npc()
        self.assertEqual(npc.physical.sickness, 0)
        self.assertEqual(npc.physical.max_sickness, 100)

    def test_below_feverish_threshold_has_no_message_or_status(self):
        npc = self._make_npc(sickness=10)
        update_entity_illness(self.world, npc)
        self.assertEqual(npc.physical.sickness_level_msg, "")
        self.assertNotIn(SICK_STATUS_EFFECT, npc.physical.status_effects)

    def test_feverish_threshold_sets_message_only(self):
        npc = self._make_npc(sickness=SICKNESS_THRESHOLD_FEVERISH)
        update_entity_illness(self.world, npc)
        self.assertEqual(npc.physical.sickness_level_msg, "Feverish")
        self.assertNotIn(SICK_STATUS_EFFECT, npc.physical.status_effects)

    def test_sick_threshold_applies_status_effect_and_halves_speed(self):
        npc = self._make_npc(sickness=SICKNESS_THRESHOLD_SICK)
        npc.speed = 1.0
        update_entity_illness(self.world, npc)
        self.assertIn(SICK_STATUS_EFFECT, npc.physical.status_effects)
        self.assertEqual(npc.physical.sickness_level_msg, "Very Sick")
        self.assertEqual(npc.speed, 0.5)

    def test_becoming_sick_only_applies_status_effect_once(self):
        npc = self._make_npc(sickness=SICKNESS_THRESHOLD_SICK)
        update_entity_illness(self.world, npc)
        update_entity_illness(self.world, npc)
        self.assertEqual(npc.physical.status_effects.count(SICK_STATUS_EFFECT), 1)

    def test_recover_from_sickness_clears_status_and_resets_meter(self):
        npc = self._make_npc(sickness=90)
        npc.speed = 1.0
        update_entity_illness(self.world, npc)
        self.assertIn(SICK_STATUS_EFFECT, npc.physical.status_effects)

        recover_from_sickness(npc)

        self.assertNotIn(SICK_STATUS_EFFECT, npc.physical.status_effects)
        self.assertEqual(npc.physical.sickness, 0)
        self.assertEqual(npc.physical.sickness_level_msg, "")
        self.assertEqual(npc.speed, 1.0)

    def test_sickness_never_rises_passively_without_contagion(self):
        npc = self._make_npc(sickness=0)
        for _ in range(50):
            update_entity_illness(self.world, npc)
        self.assertEqual(npc.physical.sickness, 0)


class TestUntreatedIllnessWorsening(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=43, pre_simulate=False)

    def _make_npc(self, sickness=SICKNESS_THRESHOLD_SICK):
        npc = NPC(0, 0, name="Patient", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.physical.sickness = sickness
        return npc

    def test_worsens_and_can_damage_on_the_worsening_tick(self):
        npc = self._make_npc(sickness=80)
        hp_before = npc.combat.hp
        self.world.game_time = illness.WORSENING_INTERVAL_TICKS  # lands exactly on a worsening tick

        with patch("simulation.systems.illness.random.random", return_value=0.0):
            update_entity_illness(self.world, npc)

        self.assertEqual(npc.physical.sickness, min(100, 80 + illness.WORSENING_SICKNESS_GAIN))
        self.assertLess(npc.combat.hp, hp_before)

    def test_worsening_is_rate_limited_rather_than_every_tick(self):
        """Asserted as elapsed time, not as boundary alignment.

        This used to set game_time one tick past the interval and assert nothing
        happened - which was true, and was the bug: the check only ever fired
        when the clock landed exactly on a multiple, and game_time jumps whenever
        the player sleeps or takes a costly action. An illness stopped
        progressing entirely once the clock drifted off the boundaries. What the
        test is really protecting is that worsening is rate-limited, so that is
        what it now checks.
        """
        npc = self._make_npc(sickness=80)
        self.world.game_time = illness.WORSENING_INTERVAL_TICKS

        with patch("simulation.systems.illness.random.random", return_value=0.99):
            update_entity_illness(self.world, npc)
        after_first = npc.physical.sickness
        self.assertGreater(after_first, 80, "the illness never worsened at all")

        self.world.game_time += 1
        with patch("simulation.systems.illness.random.random", return_value=0.99):
            update_entity_illness(self.world, npc)

        self.assertEqual(
            npc.physical.sickness, after_first,
            "the illness worsened again one tick later, so it is not rate-limited",
        )

    def test_unlucky_damage_roll_still_worsens_meter_without_damage(self):
        npc = self._make_npc(sickness=80)
        hp_before = npc.combat.hp
        self.world.game_time = illness.WORSENING_INTERVAL_TICKS

        with patch("simulation.systems.illness.random.random", return_value=0.99):
            update_entity_illness(self.world, npc)

        self.assertEqual(npc.physical.sickness, min(100, 80 + illness.WORSENING_SICKNESS_GAIN))
        self.assertEqual(npc.combat.hp, hp_before)


class TestContagionSpread(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=47, pre_simulate=False)
        self.world.game_time = illness.CONTAGION_CHECK_INTERVAL_TICKS  # on-cadence

    def _make_npc(self, x, y, sick=False):
        npc = NPC(x, y, name="Villager", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        if sick:
            npc.physical.sickness = SICKNESS_THRESHOLD_SICK
            npc.physical.status_effects.append(SICK_STATUS_EFFECT)
        return npc

    def test_contagion_is_rate_limited_rather_than_every_tick(self):
        """See the worsening test above for why this is no longer asserted as
        landing exactly on a boundary."""
        sick = self._make_npc(0, 0, sick=True)
        healthy = self._make_npc(1, 0)
        self.world.village_npcs = [sick, healthy]
        self.world.game_time = illness.CONTAGION_CHECK_INTERVAL_TICKS

        with patch("simulation.systems.illness.random.random", return_value=0.0):
            spread_contagion(self.world)
        after_first = healthy.physical.sickness

        healthy.physical.sickness = 0
        self.world.game_time += 1
        with patch("simulation.systems.illness.random.random", return_value=0.0):
            spread_contagion(self.world)

        self.assertGreater(after_first, 0, "contagion never ran at all")
        self.assertEqual(
            healthy.physical.sickness, 0,
            "contagion ran again one tick later, so it is not rate-limited",
        )

    def test_nearby_healthy_npc_can_be_infected(self):
        sick = self._make_npc(0, 0, sick=True)
        healthy = self._make_npc(1, 0)
        self.world.village_npcs = [sick, healthy]

        # First random.random() call (the proximity check) succeeds; every
        # call after (including the separate ambient-onset pass) fails, so
        # this isolates proximity infection from the ambient-onset roll.
        with patch("simulation.systems.illness.random.random", side_effect=itertools.chain([0.0], itertools.repeat(1.0))):
            spread_contagion(self.world)

        self.assertEqual(healthy.physical.sickness, illness.SICKNESS_INFECTION_GAIN)

    def test_out_of_radius_npc_is_not_infected(self):
        sick = self._make_npc(0, 0, sick=True)
        far_healthy = self._make_npc(50, 50)
        self.world.village_npcs = [sick, far_healthy]

        # The radius gate excludes this pair before any random() call is
        # made, so a value that would fail every roll (including ambient
        # onset) confirms no infection happens through either path.
        with patch("simulation.systems.illness.random.random", return_value=1.0):
            spread_contagion(self.world)

        self.assertEqual(far_healthy.physical.sickness, 0)

    def test_unlucky_roll_does_not_infect(self):
        sick = self._make_npc(0, 0, sick=True)
        healthy = self._make_npc(1, 0)
        self.world.village_npcs = [sick, healthy]

        with patch("simulation.systems.illness.random.random", return_value=0.99):
            spread_contagion(self.world)

        self.assertEqual(healthy.physical.sickness, 0)

    def test_already_sick_npc_is_not_reinfected(self):
        sick_a = self._make_npc(0, 0, sick=True)
        sick_b = self._make_npc(1, 0, sick=True)
        self.world.village_npcs = [sick_a, sick_b]
        sickness_before = sick_b.physical.sickness

        with patch("simulation.systems.illness.random.random", return_value=0.0):
            spread_contagion(self.world)

        self.assertEqual(sick_b.physical.sickness, sickness_before)

    def test_dead_npc_does_not_spread_or_catch_illness(self):
        sick = self._make_npc(0, 0, sick=True)
        dead = self._make_npc(1, 0)
        dead.physical.is_dead = True
        self.world.village_npcs = [sick, dead]

        with patch("simulation.systems.illness.random.random", return_value=0.0):
            spread_contagion(self.world)

        self.assertEqual(dead.physical.sickness, 0)

    def test_player_can_be_infected_by_nearby_sick_npc(self):
        sick = self._make_npc(self.world.player.x, self.world.player.y + 1, sick=True)
        self.world.village_npcs = [sick]

        with patch("simulation.systems.illness.random.random", side_effect=itertools.chain([0.0], itertools.repeat(1.0))):
            spread_contagion(self.world)

        self.assertEqual(self.world.player.physical.sickness, illness.SICKNESS_INFECTION_GAIN)

    def test_ambient_onset_can_start_a_patient_zero(self):
        healthy = self._make_npc(0, 0)
        self.world.village_npcs = [healthy]

        # First call (contagion loop) would use the same mocked value, so
        # patch random.random to always return a value below the tiny
        # ambient-onset chance but above nothing else matters here since
        # there's no sick entity yet to run the pairwise loop against.
        with patch("simulation.systems.illness.random.random", return_value=0.0):
            spread_contagion(self.world)

        self.assertEqual(healthy.physical.sickness, illness.SICKNESS_INFECTION_GAIN)


class TestMedicalSystemHandlesSickness(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=53, pre_simulate=False)
        self.world._update_entity_temperature = MagicMock()
        self.world._apply_temperature_effects = MagicMock()
        self.world._update_npc_fov = MagicMock()
        self.world.calculate_path = MagicMock(return_value=[])

    def _make_npc(self, name, x=10, y=10):
        npc = NPC(x, y, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.physical.temperature = 37.0
        return npc

    def test_sick_patient_is_routed_to_seek_healer(self):
        patient = self._make_npc("Patient")
        patient.physical.status_effects.append(SICK_STATUS_EFFECT)

        update_npc_medical_state(self.world, patient)

        self.assertEqual(patient.schedule.current_task, "resting_in_bed")

    def test_healer_picks_up_sick_patient_alongside_broken_leg_patients(self):
        patient = self._make_npc("Sick Patient", x=10, y=10)
        patient.physical.status_effects.append(SICK_STATUS_EFFECT)

        healer = self._make_npc("Healer NPC", x=11, y=10)
        healer.economic.profession = "Healer"

        self.world.village_npcs = [patient, healer]
        self.world.npcs = []
        self.world.game_time += engine.NPC_SCHEDULE_UPDATE_INTERVAL

        self.world._update_npc_schedules()

        self.assertEqual(healer.schedule.current_task, "treating_patient")
        self.assertEqual(healer.task_target_entity_id, patient.id)

    def test_healer_treats_sick_patient_and_cures_them(self):
        patient = self._make_npc("Sick Patient", x=10, y=10)
        patient.physical.status_effects.append(SICK_STATUS_EFFECT)
        patient.economic.money = 20

        healer = self._make_npc("Healer NPC", x=10, y=11)
        healer.economic.profession = "Healer"
        healer.economic.money = 0
        healer.schedule.current_task = "treating_patient"
        healer.task_target_entity_id = patient.id
        healer.task_timer = 0

        self.world.village_npcs = [patient, healer]

        update_npc_medical_state(self.world, healer)

        self.assertNotIn(SICK_STATUS_EFFECT, patient.physical.status_effects)
        self.assertEqual(patient.physical.sickness, 0)
        self.assertEqual(healer.schedule.current_task, "idle")
        self.assertEqual(healer.economic.money, 10)  # paid from patient's money

    def test_healer_crafts_herbal_remedy_when_low_on_stock(self):
        healer = self._make_npc("Healer NPC")
        healer.economic.profession = "Healer"
        healer.economic.npc_inventory["healing_salve"] = 5  # already stocked
        healer.economic.npc_inventory["medicinal_herb"] = 4

        self.world.village_npcs = [healer]
        self.world.npcs = []

        update_npc_medical_state(self.world, healer)
        self.assertEqual(healer.schedule.current_task, "crafting_medical_supplies")
        self.assertEqual(healer.task_context_data, {"remedy": "herbal_remedy"})
        self.assertEqual(healer.schedule.current_destination_coords, (healer.x, healer.y))

        # Mirrors the existing healer-crafting test pattern: task_timer=1
        # means the next call decrements it to 0 and completes the craft.
        healer.task_timer = 1
        update_npc_medical_state(self.world, healer)

        self.assertEqual(healer.economic.npc_inventory.get("herbal_remedy", 0), 1)
        self.assertEqual(healer.schedule.current_task, "idle")


class TestHerbalRemedyItemDefinition(unittest.TestCase):
    def test_herbal_remedy_is_defined_and_distinct_from_healing_salve(self):
        from data.items import ITEM_DEFINITIONS

        self.assertIn("herbal_remedy", ITEM_DEFINITIONS)
        remedy = ITEM_DEFINITIONS["herbal_remedy"]
        self.assertEqual(remedy["crafting_recipe"], {"medicinal_herb": 2})
        self.assertTrue(remedy["on_use"]["cures_sickness"])
        self.assertNotEqual(remedy, ITEM_DEFINITIONS["healing_salve"])


class TestPlayerUsesHerbalRemedy(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=59, pre_simulate=False)

    def test_using_herbal_remedy_cures_sick_player(self):
        self.world.player.physical.status_effects.append(SICK_STATUS_EFFECT)
        self.world.player.physical.sickness = 90
        self.world.player.add_item("herbal_remedy", 1)

        self.world.use_item("herbal_remedy")

        self.assertNotIn(SICK_STATUS_EFFECT, self.world.player.physical.status_effects)
        self.assertEqual(self.world.player.physical.sickness, 0)
        self.assertFalse(self.world.player.has_item("herbal_remedy"))

    def test_using_herbal_remedy_while_not_sick_does_not_consume_it(self):
        self.world.player.add_item("herbal_remedy", 1)

        self.world.use_item("herbal_remedy")

        self.assertTrue(self.world.player.has_item("herbal_remedy"))

    def test_using_food_item_without_heal_amount_does_not_crash(self):
        # Regression test for the pre-existing `consumed` UnboundLocalError:
        # any on_use dict without heal_amount (e.g. pure reduces_hunger)
        # used to be able to hit `if not consumed:` before `consumed` was
        # ever assigned.
        self.world.player.physical.hunger = 50
        self.world.player.add_item("bread", 1)

        try:
            self.world.use_item("bread")
        except UnboundLocalError:
            self.fail("use_item raised UnboundLocalError on a heal_amount-less item")


if __name__ == "__main__":
    unittest.main()
