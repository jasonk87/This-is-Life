import unittest
from unittest.mock import patch

import config
import engine
from engine import NPC, World


class TestPopulationLifecycle(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=123)

    def _make_npc(self, name, age):
        npc = NPC(
            self.world.player.x,
            self.world.player.y,
            name=name,
            dialogue=["Hello."],
            personality="villager",
            player_id=self.world.player.id,
        )
        npc.age = age
        return npc

    def test_old_age_death_actually_removes_npc_from_world(self):
        """Regression test for the bug where old-age death only logged a
        DeathRecord and never removed the NPC from village_npcs/npcs."""
        elder = self._make_npc("Elder Test", age=80)
        self.world.village_npcs.append(elder)
        self.world.npcs.append(elder)
        self.world._mark_entity_positions_dirty()

        with patch("random.random", return_value=0.0):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=[elder], location=(elder.x, elder.y)
            )

        self.assertTrue(elder.physical.is_dead)
        self.assertNotIn(elder, self.world.village_npcs)
        self.assertNotIn(elder, self.world.npcs)

    def test_birth_adds_child_with_expected_starting_state(self):
        import random as random_module

        parent1 = self._make_npc("Parent One", age=25)
        parent2 = self._make_npc("Parent Two", age=27)
        village_npcs = [parent1, parent2]
        starting_world_count = len(self.world.village_npcs)

        original_choice = random_module.choice
        picks = iter([parent1, parent2])

        def fake_choice(seq):
            # Only the first two random.choice calls are the parent
            # selection; NPC() construction (e.g. gender) also calls
            # random.choice internally and should use real randomness.
            try:
                return next(picks)
            except StopIteration:
                return original_choice(seq)

        with patch("random.random", return_value=0.0), \
             patch("random.choice", side_effect=fake_choice):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=village_npcs, location=(parent1.x, parent1.y)
            )

        self.assertEqual(len(village_npcs), 3)
        child = village_npcs[-1]
        self.assertEqual(child.age, 0)
        self.assertEqual(child.economic.profession, "Child")
        self.assertEqual(len(self.world.village_npcs), starting_world_count + 1)
        self.assertIn(child, self.world.village_npcs)

    def test_births_respect_max_npcs_per_village_cap(self):
        """New guard: the original code had no population cap at all, which
        was fine when this logic only ran for rarely-observed distant
        villages. Now that it also runs for the player's own visible
        village, an unbounded cap would let it grow forever, so births stop
        once a village is at MAX_NPCS_PER_VILLAGE."""
        village_npcs = [
            self._make_npc(f"Villager {i}", age=25)
            for i in range(config.MAX_NPCS_PER_VILLAGE)
        ]

        with patch("random.random", return_value=0.0):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=village_npcs, location=(0, 0)
            )

        self.assertEqual(len(village_npcs), config.MAX_NPCS_PER_VILLAGE)

    def test_child_transitions_to_adult_profession_at_eighteen(self):
        child = self._make_npc("Child Test", age=17)
        self.world._set_entity_profession(child, "Child", reason="test_setup")
        self.world.village_npcs.append(child)
        self.world.game_time = config.DAY_LENGTH_TICKS

        self.world._update_npc_ages()

        self.assertEqual(child.age, 18)
        self.assertEqual(child.economic.profession, "Unemployed")

    def test_child_under_eighteen_does_not_transition(self):
        child = self._make_npc("Young Child", age=10)
        self.world._set_entity_profession(child, "Child", reason="test_setup")
        self.world.village_npcs.append(child)
        self.world.game_time = config.DAY_LENGTH_TICKS

        self.world._update_npc_ages()

        self.assertEqual(child.age, 11)
        self.assertEqual(child.economic.profession, "Child")

    def test_death_runs_for_players_nearby_village_not_just_distant_ones(self):
        """Regression test for the abstraction gap where birth/death only
        ever ran for villages farther than ABSTRACT_SIMULATION_DISTANCE_CHUNKS
        from the player - meaning the player's own actively-simulated home
        village never had generational turnover. Uses an extremely old NPC
        (age 170, giving a guaranteed (170-70)/100 = 100% daily death chance)
        instead of mocking `random` so the rest of the distance-gated
        economic/trade/diplomacy logic in _update_abstract_simulation runs
        with real randomness rather than a globally forced value.
        """
        player_chunk_x = self.world.player.x // config.CHUNK_SIZE
        player_chunk_y = self.world.player.y // config.CHUNK_SIZE

        # World(seed=...) in this test harness generates village *buildings*
        # up front but not resident NPCs (those are spawned lazily as the
        # player explores), so a resident has to be registered by hand here.
        # Pick any village within the abstract-simulation distance and give
        # it a resident tied to one of its real buildings via home_building_id,
        # exactly as `_get_village_for_npc` expects.
        near_village = None
        for y in range(self.world.chunk_height):
            for x in range(self.world.chunk_width):
                chunk = self.world.chunks[y][x]
                if not chunk.village or not chunk.village.buildings:
                    continue
                dist = max(abs(x - player_chunk_x), abs(y - player_chunk_y))
                if dist <= config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS:
                    near_village = chunk.village
                    break
            if near_village is not None:
                break

        self.assertIsNotNone(
            near_village,
            "test setup requires at least one village within "
            "ABSTRACT_SIMULATION_DISTANCE_CHUNKS of the player's starting position",
        )

        home = near_village.buildings[0]
        elder = self._make_npc("Near Elder", age=170)
        elder.x, elder.y = home.global_center_x, home.global_center_y
        elder.schedule.home_building_id = home.id
        self.world.village_npcs.append(elder)
        self.world.npcs.append(elder)
        self.world._mark_entity_positions_dirty()

        self.assertEqual(self.world._get_village_for_npc(elder), near_village)
        self.world.game_time = config.DAY_LENGTH_TICKS

        self.world._update_abstract_simulation()

        self.assertTrue(elder.physical.is_dead)
        self.assertNotIn(elder, self.world.village_npcs)


if __name__ == "__main__":
    unittest.main()
