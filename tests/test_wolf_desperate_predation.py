import unittest
from types import SimpleNamespace
from unittest.mock import patch

import engine
from engine import NPC, World
from entities.behaviors import PredatorBehavior
from simulation.systems.task_types import TaskType
from tests.world_cache import fresh_world


class TestDesperatePredationUnit(unittest.TestCase):
    """Direct unit tests of PredatorBehavior's new desperate-predation
    escalation, using lightweight SimpleNamespace entities (matching the
    style of the existing TestPredatorPursuit tests in tests/test_engine.py)
    so each gate can be tested in isolation."""

    def _wolf(self, hunger=95, hostile=False):
        return SimpleNamespace(
            id=99,
            x=10,
            y=10,
            animal_type="wolf",
            animal_definition={"prey": ["deer"], "pack_animal": True},
            physical=SimpleNamespace(hunger=hunger, max_hunger=100),
            combat=SimpleNamespace(is_hostile_to_player=hostile, attack_range=1),
            schedule=SimpleNamespace(current_task="hunting", current_path=[], current_destination_coords=None),
            task_target_entity_id=None,
        )

    def _human(self, id_, x, y, dead=False):
        return SimpleNamespace(
            id=id_, x=x, y=y,
            animal_type=None,
            physical=SimpleNamespace(is_dead=dead),
        )

    def _world(self, village_npcs=None, player=None):
        world = object.__new__(engine.World)
        world.village_npcs = village_npcs or []
        world.player = player or SimpleNamespace(id=1, x=100, y=100)
        world.add_message_to_chat_log = lambda msg: None
        world.get_entity_display_name = lambda entity: getattr(entity, "name", "Wolf")
        return world

    def test_below_desperate_threshold_never_escalates(self):
        wolf = self._wolf(hunger=85)  # below the 90% threshold
        human = self._human(2, 11, 10)
        world = self._world(village_npcs=[human])

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertFalse(result)
        self.assertIsNone(wolf.task_target_entity_id)

    def test_desperate_but_unlucky_roll_does_not_escalate(self):
        wolf = self._wolf(hunger=95)
        human = self._human(2, 11, 10)
        world = self._world(village_npcs=[human])

        with patch("random.random", return_value=0.5):  # >= 0.15 chance, fails the roll
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertFalse(result)
        self.assertIsNone(wolf.task_target_entity_id)

    def test_desperate_and_lucky_roll_targets_nearest_human(self):
        wolf = self._wolf(hunger=95)
        near_human = self._human(2, 11, 10)
        far_human = self._human(3, 30, 30)
        world = self._world(village_npcs=[far_human, near_human])

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertTrue(result)
        self.assertEqual(wolf.schedule.current_task, "hunting")
        self.assertEqual(wolf.task_target_entity_id, near_human.id)

    def test_dead_and_animal_npcs_are_never_targeted(self):
        wolf = self._wolf(hunger=95)
        dead_human = self._human(2, 11, 10, dead=True)
        an_animal = self._human(3, 11, 10)
        an_animal.animal_type = "sheep"  # not a human NPC target
        world = self._world(village_npcs=[dead_human, an_animal])

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertFalse(result)

    def test_out_of_radius_human_is_not_targeted(self):
        wolf = self._wolf(hunger=95)
        far_human = self._human(2, 200, 200)
        world = self._world(village_npcs=[far_human])

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertFalse(result)

    def test_no_human_but_player_in_range_sets_hostile_to_player(self):
        wolf = self._wolf(hunger=95)
        player = SimpleNamespace(id=1, x=15, y=10)
        world = self._world(village_npcs=[], player=player)

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertTrue(result)
        self.assertTrue(wolf.combat.is_hostile_to_player)

    def test_no_human_and_player_out_of_range_does_nothing(self):
        wolf = self._wolf(hunger=95)
        player = SimpleNamespace(id=1, x=200, y=200)
        world = self._world(village_npcs=[], player=player)

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertFalse(result)
        self.assertFalse(wolf.combat.is_hostile_to_player)

    def test_already_hostile_to_player_does_not_retrigger(self):
        wolf = self._wolf(hunger=95, hostile=True)
        player = SimpleNamespace(id=1, x=15, y=10)
        world = self._world(village_npcs=[], player=player)

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(wolf, world)

        self.assertFalse(result)

    def test_non_predator_animal_never_escalates(self):
        deer = self._wolf(hunger=99)
        deer.animal_definition = {}  # no "prey" key - herbivore
        human = self._human(2, 11, 10)
        world = self._world(village_npcs=[human])

        with patch("random.random", return_value=0.0):
            result = PredatorBehavior()._try_escalate_to_desperate_predation(deer, world)

        self.assertFalse(result)


class TestDesperatePredationIntegration(unittest.TestCase):
    """End-to-end tests through a real World, PredatorBehavior.take_turn,
    and the real combat path, to confirm the feature actually works when
    wired into the full animal AI loop rather than just in isolation."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=123, pre_simulate=False)
        self.world.npcs = []  # no wild prey anywhere
        self.world.calculate_path = lambda sx, sy, ex, ey: [(sx, sy), (ex, ey)] if (sx, sy) != (ex, ey) else []

    def _make_wolf(self, x, y, hunger=92):
        from entities.animal import Animal
        wolf = Animal(x, y, name="Starving Wolf", animal_type="wolf")
        wolf.physical.hunger = hunger
        self.world.npcs.append(wolf)
        return wolf

    def _make_villager(self, x, y):
        villager = NPC(x, y, name="Villager", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.village_npcs.append(villager)
        return villager

    def test_desperate_wolf_targets_and_then_attacks_human_villager(self):
        wolf = self._make_wolf(10, 10, hunger=92)
        villager = self._make_villager(11, 10)  # adjacent, within attack range

        with patch("random.random", return_value=0.0), \
             patch.object(self.world, "_find_nearest_corpse", return_value=(None, None)):
            took_turn_1 = wolf.ai_brain.take_turn(wolf, self.world)

        self.assertTrue(took_turn_1)
        self.assertEqual(wolf.schedule.current_task, "hunting")
        self.assertEqual(wolf.task_target_entity_id, villager.id)

        hp_before = villager.combat.hp
        with patch("random.random", return_value=0.0), \
             patch.object(self.world, "_find_nearest_corpse", return_value=(None, None)):
            took_turn_2 = wolf.ai_brain.take_turn(wolf, self.world)

        self.assertTrue(took_turn_2)
        self.assertLess(villager.combat.hp, hp_before)

    def test_get_predator_target_resolves_village_npc_targets(self):
        """Regression test for the _get_predator_target widening: it used to
        search only self.npcs (wild animals), which would never find a
        human villager target living in village_npcs."""
        wolf = self._make_wolf(10, 10, hunger=92)
        villager = self._make_villager(20, 20)
        wolf.task_target_entity_id = villager.id

        resolved = self.world._get_predator_target(wolf)

        self.assertIs(resolved, villager)

    def test_not_desperate_enough_wolf_does_not_target_villager(self):
        wolf = self._make_wolf(10, 10, hunger=75)  # hungry but not desperate
        self._make_villager(11, 10)

        with patch("random.random", return_value=0.0), \
             patch.object(self.world, "_find_nearest_corpse", return_value=(None, None)):
            wolf.ai_brain.take_turn(wolf, self.world)

        self.assertIsNone(wolf.task_target_entity_id)

    def test_corpse_takes_priority_over_desperate_predation(self):
        """If a corpse is available, a starving wolf should scavenge it
        rather than attack a villager - the desperate-predation branch is
        only reached after the corpse search fails."""
        wolf = self._make_wolf(10, 10, hunger=92)
        villager = self._make_villager(11, 10)

        with patch("random.random", return_value=0.0), \
             patch.object(self.world, "_find_nearest_corpse", return_value=(15, 15)):
            wolf.ai_brain.take_turn(wolf, self.world)

        self.assertEqual(wolf.schedule.current_task, "eating_corpse")
        self.assertNotEqual(wolf.task_target_entity_id, villager.id)


if __name__ == "__main__":
    unittest.main()
