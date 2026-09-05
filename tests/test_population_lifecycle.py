import unittest
from unittest.mock import patch

import config
from simulation.systems import aging
import engine
from engine import NPC, World
from tests.world_cache import fresh_world


class TestPopulationLifecycle(unittest.TestCase):
    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=123, pre_simulate=False)

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

    def _marry(self, npc_a, npc_b):
        npc_a.social.family_ties["partner_id"] = npc_b.id
        npc_a.social.family_ties["spouse_id"] = npc_b.id
        npc_b.social.family_ties["partner_id"] = npc_a.id
        npc_b.social.family_ties["spouse_id"] = npc_a.id

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
        parent1 = self._make_npc("Parent One", age=25)
        parent2 = self._make_npc("Parent Two", age=27)
        self._marry(parent1, parent2)
        village_npcs = [parent1, parent2]
        starting_world_count = len(self.world.village_npcs)

        with patch("random.random", return_value=0.0):
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
        # Include a married couple so there IS an eligible birth that would
        # happen if not for the cap - otherwise this test wouldn't actually
        # exercise the cap at all now that unmarried pairing is gone.
        self._marry(village_npcs[0], village_npcs[1])

        with patch("random.random", return_value=0.0):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=village_npcs, location=(0, 0)
            )

        self.assertEqual(len(village_npcs), config.MAX_NPCS_PER_VILLAGE)

    def test_unmarried_pair_never_produces_a_birth(self):
        """Core of this change: births now require an actual married couple.
        Two single adults living in the same village no longer spontaneously
        have a child together, even with the daily-chance roll forced to
        succeed."""
        single1 = self._make_npc("Single One", age=25)
        single2 = self._make_npc("Single Two", age=27)
        village_npcs = [single1, single2]

        with patch("random.random", return_value=0.0):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=village_npcs, location=(0, 0)
            )

        self.assertEqual(len(village_npcs), 2)

    def test_one_sided_partner_tie_does_not_count_as_married(self):
        npc_a = self._make_npc("A", age=25)
        npc_b = self._make_npc("B", age=27)
        # Stale/one-sided tie: A considers itself partnered to B, but B's
        # own ties don't point back - should not be treated as a real couple.
        npc_a.social.family_ties["partner_id"] = npc_b.id
        village_npcs = [npc_a, npc_b]

        with patch("random.random", return_value=0.0):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=village_npcs, location=(0, 0)
            )

        self.assertEqual(len(village_npcs), 2)

    def test_married_partner_outside_age_range_excludes_the_couple(self):
        npc_a = self._make_npc("A", age=25)
        npc_b = self._make_npc("B", age=60)  # outside the 18-50 eligible range
        self._marry(npc_a, npc_b)
        village_npcs = [npc_a, npc_b]

        with patch("random.random", return_value=0.0):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=village_npcs, location=(0, 0)
            )

        self.assertEqual(len(village_npcs), 2)

    def test_dead_partner_excludes_the_couple(self):
        npc_a = self._make_npc("A", age=25)
        npc_b = self._make_npc("B", age=27)
        self._marry(npc_a, npc_b)
        npc_b.physical.is_dead = True
        village_npcs = [npc_a, npc_b]

        with patch("random.random", return_value=0.0):
            self.world._simulate_village_population_lifecycle(
                village=None, village_npcs=village_npcs, location=(0, 0)
            )

        self.assertEqual(len(village_npcs), 2)

    def test_find_married_couples_eligible_for_birth_unit(self):
        npc_a = self._make_npc("A", age=25)
        npc_b = self._make_npc("B", age=27)
        self._marry(npc_a, npc_b)
        single = self._make_npc("Single", age=30)

        couples = self.world._find_married_couples_eligible_for_birth([npc_a, npc_b, single])

        self.assertEqual(len(couples), 1)
        self.assertEqual({couples[0][0].id, couples[0][1].id}, {npc_a.id, npc_b.id})

    def _advance_one_year(self):
        """Run the ageing system across a calendar year boundary.

        These two tests used to set game_time to a single day and expect
        everyone to be a year older, which is what the ageing bug did: a year
        of life per day of play, 112 times too fast, and enough to empty a
        village inside two months. They are about the coming-of-age transition,
        not about the clock, so they now advance an actual year.
        """
        self.world.game_time = config.DAY_LENGTH_TICKS
        self.world._update_npc_ages()          # establishes the current year
        self.world.game_time = aging.DAYS_PER_YEAR * config.DAY_LENGTH_TICKS
        self.world._update_npc_ages()          # the year turns over

    def test_child_transitions_to_adult_profession_at_eighteen(self):
        child = self._make_npc("Child Test", age=17)
        self.world._set_entity_profession(child, "Child", reason="test_setup")
        self.world.village_npcs.append(child)

        self._advance_one_year()

        self.assertEqual(child.age, 18)
        self.assertEqual(child.economic.profession, "Unemployed")

    def test_child_under_eighteen_does_not_transition(self):
        child = self._make_npc("Young Child", age=10)
        self.world._set_entity_profession(child, "Child", reason="test_setup")
        self.world.village_npcs.append(child)

        self._advance_one_year()

        self.assertEqual(child.age, 11)
        self.assertEqual(child.economic.profession, "Child")

    def test_a_child_does_not_have_a_birthday_every_day(self):
        child = self._make_npc("Slowly Growing", age=10)
        self.world._set_entity_profession(child, "Child", reason="test_setup")
        self.world.village_npcs.append(child)

        for day in range(1, 31):
            self.world.game_time = day * config.DAY_LENGTH_TICKS
            self.world._update_npc_ages()

        self.assertEqual(child.age, 10, "a month of play aged a child")

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
        # Take any generated village and move the *player* next to it,
        # rather than hoping the generator happened to place one near the
        # player's spawn. Village placement depends on terrain, so that
        # hope was seed- and environment-dependent: it held while the tcod
        # compat shim's noise stub made every map uniformly flat, and broke
        # as soon as real tcod produced real terrain. What this test
        # actually needs is only that the village is inside
        # ABSTRACT_SIMULATION_DISTANCE_CHUNKS of the player.
        near_village = None
        for y in range(self.world.chunk_height):
            for x in range(self.world.chunk_width):
                chunk = self.world.chunks[y][x]
                if not chunk.village or not chunk.village.buildings:
                    continue
                near_village = chunk.village
                self.world.player.x = x * config.CHUNK_SIZE + config.CHUNK_SIZE // 2
                self.world.player.y = y * config.CHUNK_SIZE + config.CHUNK_SIZE // 2
                break
            if near_village is not None:
                break

        self.assertIsNotNone(near_village, "test setup requires at least one generated village")

        player_chunk_x = self.world.player.x // config.CHUNK_SIZE
        player_chunk_y = self.world.player.y // config.CHUNK_SIZE
        village_chunk_x, village_chunk_y = near_village.chunk_coords
        self.assertLessEqual(
            max(abs(village_chunk_x - player_chunk_x), abs(village_chunk_y - player_chunk_y)),
            config.ABSTRACT_SIMULATION_DISTANCE_CHUNKS,
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
