import unittest

import engine
from engine import NPC, World
from tests.world_cache import fresh_world


class TestCareerLevelPromotion(unittest.TestCase):
    """Unit tests for World._maybe_advance_career_level, the new tenure/
    performance-driven promotion path for CareerState.level (previously
    set once by set_role() and never advanced again)."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=123, pre_simulate=False)

    def _make_worker(self, role="Farmer", tenure_days=30, work_performance=60, level=0):
        npc = NPC(
            self.world.player.x,
            self.world.player.y,
            name="Worker",
            dialogue=["Hi."],
            personality="villager",
            player_id=self.world.player.id,
        )
        self.world._set_entity_profession(npc, role, reason="test_setup")
        npc.career.level = level
        npc.career.tenure_days = tenure_days
        npc.economic.work_performance = work_performance
        return npc

    def test_promotes_after_tenure_interval_with_good_performance(self):
        worker = self._make_worker(tenure_days=30, work_performance=60, level=0)

        promoted = self.world._maybe_advance_career_level(worker)

        self.assertTrue(promoted)
        self.assertEqual(worker.career.level, 1)

    def test_no_promotion_below_performance_threshold(self):
        worker = self._make_worker(tenure_days=30, work_performance=40, level=0)

        promoted = self.world._maybe_advance_career_level(worker)

        self.assertFalse(promoted)
        self.assertEqual(worker.career.level, 0)

    def test_no_promotion_off_interval(self):
        worker = self._make_worker(tenure_days=15, work_performance=90, level=0)

        promoted = self.world._maybe_advance_career_level(worker)

        self.assertFalse(promoted)
        self.assertEqual(worker.career.level, 0)

    def test_promotion_capped_at_max_level(self):
        worker = self._make_worker(tenure_days=180, work_performance=95, level=5)

        promoted = self.world._maybe_advance_career_level(worker)

        self.assertFalse(promoted)
        self.assertEqual(worker.career.level, 5)

    def test_unemployed_npc_is_never_promoted(self):
        worker = self._make_worker(role="Unemployed", tenure_days=30, work_performance=90, level=0)

        promoted = self.world._maybe_advance_career_level(worker)

        self.assertFalse(promoted)
        self.assertEqual(worker.career.level, 0)

    def test_quitting_resets_accumulated_level_via_existing_set_role_path(self):
        """Confirms the documented interaction: leaving a job (which already
        routes through _set_entity_profession -> career.set_role()) wipes
        out any tenure-based level gained, so quit-and-rehire no longer
        beats staying and advancing."""
        worker = self._make_worker(tenure_days=30, work_performance=60, level=0)
        self.assertTrue(self.world._maybe_advance_career_level(worker))
        self.assertEqual(worker.career.level, 1)

        self.world._set_entity_profession(worker, "Unemployed", reason="quit_job")

        self.assertEqual(worker.career.level, 0)
        self.assertEqual(worker.career.tenure_days, 0)

    def test_update_npc_careers_promotes_real_npc_end_to_end(self):
        # tenure_days starts at 29: _update_npc_careers() below calls
        # career.advance_day() first (29 -> 30), then the promotion check,
        # matching how a real NPC would accumulate tenure day by day.
        worker = self._make_worker(tenure_days=29, work_performance=60, level=0)
        self.world.village_npcs.append(worker)
        self.world.game_time = engine.DAY_LENGTH_TICKS

        self.world._update_npc_careers()

        self.assertEqual(worker.career.level, 1)
        self.assertEqual(worker.career.tenure_days, 30)

    def test_player_career_advancement_promotes_via_update_player_career(self):
        player = self.world.player
        self.world._set_entity_profession(player, "Farmer", reason="test_setup")
        player.career.level = 0  # set_role() seeds this from infer_career_level("Farmer") == 1; reset for a clean baseline
        player.economic.job_building_id = "nonexistent_building_id_for_test"
        player.career.tenure_days = 29  # advance_day() below bumps this to 30
        player.economic.work_performance = 60
        self.world.game_time = engine.DAY_LENGTH_TICKS

        self.world._update_player_career()

        self.assertEqual(player.career.level, 1)


if __name__ == "__main__":
    unittest.main()
