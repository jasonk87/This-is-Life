import unittest
from types import SimpleNamespace
from unittest.mock import patch

import engine
from engine import World, Building, NPC
from entities.social import AspirationType
from simulation.world_model import Village


class TestNPCOwnedBusinessWiring(unittest.TestCase):
    """Tests for World._maybe_trigger_npc_owned_construction, the new call
    site that wires the previously-dead _npc_maybe_start_construction_project
    into live daily simulation via process_macro_daily_tick."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=123)
        # Only the candidate each test builds should be considered. _run patches
        # _get_village_for_npc to return this village for everybody, so the whole
        # generated population would otherwise be weighed for eligibility too -
        # and these tests then depend on no generated villager happening to be a
        # non-unemployed, 300-coin, wealth-aspiring one. Under seed 123 that was
        # true until an unrelated change to village generation shifted the random
        # stream, at which point one villager qualified and the four
        # "not eligible" tests failed for a reason that had nothing to do with
        # their candidate. It also makes the eligible case deterministic: with a
        # stray qualifying NPC, random.choice could pick the wrong founder.
        self.world.village_npcs.clear()
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(12, 12)]}
        self.world.chunks[0][0].village = self.village
        self.world.chunk_width = 1
        self.world.chunk_height = 1

        # Create genuine housing pressure (residents >= capacity), the same
        # need the pre-existing village-expansion logic already requires.
        house = Building(0, 0, 5, 5, building_type="house", category="residential")
        house.residents = [SimpleNamespace(), SimpleNamespace()]
        self.village.add_building(house)

    def _make_candidate(self, money=400, aspiration_type=AspirationType.WEALTH, profession="Merchant", dead=False):
        npc = NPC(5, 5, name="Candidate", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.economic.profession = profession
        npc.economic.money = money
        npc.aspiration.aspiration_type = aspiration_type
        npc.physical.is_dead = dead
        self.world.village_npcs.append(npc)
        return npc

    def _run(self, random_value=0.0):
        with patch.object(self.world, "_get_village_for_npc", return_value=self.village), \
             patch.object(self.world, "_find_valid_building_spot", return_value=(14, 14)), \
             patch("random.random", return_value=random_value):
            self.world._maybe_trigger_npc_owned_construction(self.village)

    def test_eligible_npc_founds_business_on_lucky_roll(self):
        candidate = self._make_candidate()

        self._run(random_value=0.0)  # 0.0 < 0.03 daily-chance gate

        blueprint = self.world.get_blueprint_at(14, 14)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.owner_id, candidate.id)
        self.assertEqual(blueprint.requester_id, candidate.id)
        self.assertEqual(blueprint.target_build, "house")
        self.assertEqual(blueprint.settlement_id, self.village.id)

    def test_unlucky_roll_prevents_business_even_when_eligible(self):
        self._make_candidate()

        self._run(random_value=0.5)  # 0.5 >= 0.03 daily-chance gate

        self.assertIsNone(self.world.get_blueprint_at(14, 14))

    def test_poor_npc_is_not_eligible(self):
        self._make_candidate(money=50)

        self._run(random_value=0.0)

        self.assertIsNone(self.world.get_blueprint_at(14, 14))

    def test_non_wealth_aspiration_npc_is_not_eligible(self):
        self._make_candidate(aspiration_type=AspirationType.PEACE)

        self._run(random_value=0.0)

        self.assertIsNone(self.world.get_blueprint_at(14, 14))

    def test_unemployed_npc_is_not_eligible_even_if_wealthy(self):
        self._make_candidate(profession="Unemployed")

        self._run(random_value=0.0)

        self.assertIsNone(self.world.get_blueprint_at(14, 14))

    def test_dead_npc_is_not_eligible(self):
        self._make_candidate(dead=True)

        self._run(random_value=0.0)

        self.assertIsNone(self.world.get_blueprint_at(14, 14))

    def test_no_village_need_means_no_construction_even_with_eligible_npc(self):
        self.village.buildings[0].residents = []  # relieve housing pressure
        self._make_candidate()

        self._run(random_value=0.0)

        self.assertIsNone(self.world.get_blueprint_at(14, 14))

    def test_existing_blueprint_blocks_new_npc_owned_project(self):
        self.world.place_construction_blueprint("house", 8, 8, settlement_id=self.village.id)
        self._make_candidate()

        self._run(random_value=0.0)

        self.assertIsNone(self.world.get_blueprint_at(14, 14))

    def test_process_macro_daily_tick_calls_the_new_wiring(self):
        candidate = self._make_candidate()
        self.world.game_time = engine.DAY_LENGTH_TICKS

        # process_macro_daily_tick iterates self.villages (atlas-managed),
        # not the chunk grid our lightweight test Village lives in - wire it
        # in directly, and no-op the two unrelated per-settlement steps that
        # already run there so this test stays focused on confirming the new
        # _maybe_trigger_npc_owned_construction call site actually fires.
        with patch.object(self.world, "villages", [self.village]), \
             patch.object(self.world, "_sync_village_employment_tasks"), \
             patch.object(self.world, "_seed_settlement_macro_knowledge"), \
             patch.object(self.world, "_get_village_for_npc", return_value=self.village), \
             patch.object(self.world, "_find_valid_building_spot", return_value=(14, 14)), \
             patch("random.random", return_value=0.0):
            self.world.process_macro_daily_tick()

        blueprint = self.world.get_blueprint_at(14, 14)
        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.owner_id, candidate.id)


if __name__ == "__main__":
    unittest.main()
