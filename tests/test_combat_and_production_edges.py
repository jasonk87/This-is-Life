"""Two faults a long run and a fight turned up.

* The player's own attack was the only combat path in the game adjudicated
  purely by the LLM - NPC-on-player and NPC-on-NPC both resolve on dice. With no
  model reachable it logged a comms error and returned, so the player could not
  hurt anything: measured, forty swings left an unarmoured villager on full
  health while their attacks took the player from 35 to 2.

* `Inventory` drops a key the moment its quantity reaches zero, so
  _produce_sub_task_output writing 0 and then reading the value back raised
  KeyError. A bakery baking its last sack of flour took the whole simulation
  down - found by a multi-day run at tick 21691, and only reachable at all
  because work chains now advance far enough to consume their inputs.
"""

import json
import unittest
from unittest.mock import patch

from data.professions import get_sub_task_data
from engine import World


class TestPlayerCanFightWithoutAModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Fighter")
        cls.world._pre_simulate_world()

    def _victim(self):
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.is_sleeping = False
        npc.combat.hp = npc.combat.max_hp
        self.world._update_entity_position(npc, self.world.player.x + 1, self.world.player.y)
        return npc

    def test_attacks_land_when_no_llm_answers(self):
        target = self._victim()
        start = target.combat.hp
        for _ in range(40):
            self.world.player_attempt_attack(target)
            self.world.game_time += 4  # Attacks now have a simulation-time recovery.
            if target.physical.is_dead:
                break
        self.assertTrue(
            target.physical.is_dead or target.combat.hp < start,
            "forty attacks did nothing at all",
        )

    def test_the_dice_fallback_reports_like_the_model_would(self):
        target = self._victim()
        payload = json.loads(
            self.world._resolve_player_attack_with_dice(target, "Fists", "1d3", 0, 5)
        )
        self.assertIn("hit", payload)
        self.assertIn("damage_dealt", payload)
        self.assertIn("narrative_feedback", payload)
        self.assertIsInstance(payload["hit"], bool)
        self.assertGreaterEqual(payload["damage_dealt"], 0)

    def test_a_hopeless_roll_misses(self):
        target = self._victim()
        target.defense_bonus = 50
        try:
            with patch("engine.random.randint", return_value=1):
                payload = json.loads(
                    self.world._resolve_player_attack_with_dice(target, "Fists", "1d3", 0, 0)
                )
            self.assertFalse(payload["hit"])
            self.assertEqual(payload["damage_dealt"], 0)
        finally:
            target.defense_bonus = 0

    def test_a_natural_twenty_hits_and_doubles(self):
        target = self._victim()
        with patch("engine.random.randint", return_value=20):
            payload = json.loads(
                self.world._resolve_player_attack_with_dice(target, "Stone Axe", "1d6", 2, 5)
            )
        self.assertTrue(payload["hit"])
        # randint is pinned to 20, so the d6 reads 20: (20 + 2) doubled.
        self.assertEqual(payload["damage_dealt"], (20 + 2) * 2)
        self.assertIn("CRITICAL", payload["narrative_feedback"].upper())

    def test_a_dead_target_is_left_alone(self):
        """Asserted on content, not log length - chat_log is capped at 100 entries."""
        target = self._victim()
        target.physical.is_dead = True
        hp_before = target.combat.hp

        self.world.player_attempt_attack(target)

        self.assertEqual(target.combat.hp, hp_before, "a corpse took further damage")
        self.assertIn("already defeated", self.world.chat_log[-1].lower())


class TestUsingTheLastOfAnIngredient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Tester")
        cls.world._pre_simulate_world()

    def _baker_at(self, building):
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.economic.profession = "Baker"
        npc.schedule.work_building_id = building.id
        return npc

    def test_the_last_sack_of_flour_does_not_crash(self):
        """Regression: writing a quantity of 0 and reading it back raised KeyError."""
        building = next(iter(self.world.buildings_by_id.values()))
        npc = self._baker_at(building)
        sub_task = get_sub_task_data("Baker", "bake_bread")
        building.building_inventory["flour"] = 1

        produced = self.world._produce_sub_task_output(npc, building, sub_task)

        self.assertTrue(produced)
        self.assertEqual(building.building_inventory.get("flour", 0), 0)

    def test_running_out_entirely_just_declines(self):
        building = next(iter(self.world.buildings_by_id.values()))
        npc = self._baker_at(building)
        sub_task = get_sub_task_data("Baker", "bake_bread")
        building.building_inventory.pop("flour", None)

        self.assertFalse(self.world._produce_sub_task_output(npc, building, sub_task))

    def test_a_full_larder_is_drawn_down_one_at_a_time(self):
        building = next(iter(self.world.buildings_by_id.values()))
        npc = self._baker_at(building)
        sub_task = get_sub_task_data("Baker", "bake_bread")
        building.building_inventory["flour"] = 3

        for expected in (2, 1, 0):
            self.assertTrue(self.world._produce_sub_task_output(npc, building, sub_task))
            self.assertEqual(building.building_inventory.get("flour", 0), expected)

        self.assertFalse(self.world._produce_sub_task_output(npc, building, sub_task))


if __name__ == "__main__":
    unittest.main()
