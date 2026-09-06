
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine import World, Building, NPC, Player
from config import DAY_LENGTH_TICKS, CHUNK_SIZE
from runtime_compat import np
from tests.world_cache import fresh_world

class TestSocialImpact(unittest.TestCase):
    def setUp(self):
        # Setup a mock world
        with patch('engine.World._initialize_chunks') as mock_init_chunks, \
             patch('engine.WORLD_WIDTH', new=CHUNK_SIZE), \
             patch('engine.WORLD_HEIGHT', new=CHUNK_SIZE), \
             patch('engine.World._spawn_traveling_merchants'): # Skip merchant spawn to avoid empty village error
            # We need to mock the chunk grid to match the dimensions calculated by World.__init__
            # If WORLD_WIDTH == CHUNK_SIZE, then chunk_width = 1
            mock_init_chunks.return_value = [[MagicMock()]] # 1x1 chunk grid
            # built here rather than through fresh_world: the cache is keyed
            # by seed, and a world made under these patches must not be
            # handed to a test that did not ask for them (nor the other way
            # round)
            self.world = World(seed=42)

        # Mock Ollama to avoid network calls
        self.world._call_llm = MagicMock(return_value="{}")
        self.world.add_message_to_chat_log = MagicMock()

        # Create a workplace
        self.mill = Building(10, 10, 5, 5, "lumber_mill", global_chunk_x_start=0, global_chunk_y_start=0)
        self.world.buildings_by_id[self.mill.id] = self.mill

        # Create Boss
        self.boss = NPC(12, 12, "Bossman", personality="bossy")
        self.boss.economic.profession = "Lumber Mill Foreman"
        self.boss.schedule.work_building_id = self.mill.id
        self.world.village_npcs.append(self.boss)

        # Create Worker
        self.worker = NPC(12, 13, "Worker", personality="hardworking")
        self.worker.economic.profession = "Woodcutter"
        self.worker.schedule.work_building_id = self.mill.id
        self.world.village_npcs.append(self.worker)

        # Create Unemployed
        self.unemployed = NPC(15, 15, "Lazy", personality="lazy")
        self.unemployed.economic.profession = "Unemployed"
        self.world.village_npcs.append(self.unemployed)

    def test_firing_creates_grudge(self):
        # Setup firing condition
        self.worker.economic.work_performance = 0
        self.world.game_time = DAY_LENGTH_TICKS # Ensure daily update runs

        # Force the random firing chance to hit
        with patch('random.random', return_value=0.0):
            self.world._update_npc_careers()

        # Check results
        self.assertEqual(self.worker.economic.profession, "Unemployed")
        self.assertIn(self.boss.id, self.worker.social.grudges)
        self.assertIn("Fired me", self.worker.social.grudges[self.boss.id].reason)
        self.assertGreater(self.worker.social.grudges[self.boss.id].severity, 0)

    def test_attack_creates_structured_grudge_on_victim(self):
        self.world.game_time = DAY_LENGTH_TICKS * 2
        self.world._call_llm = MagicMock(
            return_value=json.dumps(
                {"hit": True, "damage_dealt": 1, "narrative_feedback": "You strike the worker."}
            )
        )
        self.world._get_witnesses_to_action = MagicMock(return_value=[])

        self.world.player_attempt_attack(self.worker)

        self.assertIn(self.world.player.id, self.worker.social.grudges)
        grudge = self.worker.social.grudges[self.world.player.id]
        self.assertEqual(grudge.reason, "attacked_me")
        self.assertGreaterEqual(grudge.severity, 85)
        self.assertEqual(grudge.created_day, 2)

    def test_grudge_suspicion_routes_npc_to_report_crime(self):
        sheriff_office = Building(4, 4, 5, 5, "sheriff_office", global_chunk_x_start=0, global_chunk_y_start=0)
        self.world.buildings_by_id[sheriff_office.id] = sheriff_office
        self.world.game_time = DAY_LENGTH_TICKS * 3
        self.worker.schedule.current_task = "idle"
        self.worker.combat.is_hostile_to_player = False
        self.worker.add_grudge(
            self.world.player.id,
            "witnessed_assault",
            severity=80,
            current_day=3,
            decay_days=10,
        )
        self.worker.x, self.worker.y = 6, 6
        self.world.player.x, self.world.player.y = 7, 6
        self.world.npc_fov_maps[self.worker.id] = np.ones((CHUNK_SIZE, CHUNK_SIZE), dtype=bool)

        self.world._find_nearest_building_of_type = MagicMock(return_value=sheriff_office)
        self.world._run_humanoid_schedule_logic(self.worker)

        self.assertEqual(self.worker.schedule.current_task, "going_to_report_crime")
        self.assertEqual(
            self.worker.task_target_coords,
            (sheriff_office.global_center_x, sheriff_office.global_center_y),
        )

    def test_hiring_improves_relationship(self):
        # Hire the unemployed NPC
        self.world._assign_job(self.unemployed, self.mill)

        # Check results
        self.assertEqual(self.unemployed.economic.profession, "Woodcutter") # Or whatever _assign_job decides based on vacancies logic, but here it defaults/finds role
        # Relationship should increase
        self.assertGreater(self.unemployed.social.relationships.get(self.boss.id, 50), 50)
        self.assertGreater(self.boss.social.relationships.get(self.unemployed.id, 50), 50)

    def test_job_referral_logic(self):
        # Setup: Unemployed NPC needs a job. Player knows about the Mill.
        self.world.player.knowledge.known_locations[self.mill.id] = (self.mill.global_center_x, self.mill.global_center_y)

        # Ensure Mill has vacancy (Boss + Worker = 2, max is usually 4 for mill in gen, but let's force it)
        self.mill.max_workers = 5

        # Mock player input
        player_input = "I know of a job at the lumber mill."

        # Trigger dialogue
        self.world.continue_npc_dialogue(self.unemployed, player_input)

        # Check result: NPC should be applying
        self.assertEqual(self.unemployed.schedule.current_task, "applying_for_job")
        self.assertEqual(self.unemployed.schedule.current_destination_coords, (self.mill.global_center_x, self.mill.global_center_y))

    def test_presence_increases_caution_but_not_hostility(self):
        from simulation.systems.social_reaction import evaluate_social_reaction_stance

        # Baseline evaluation
        baseline_assessment = evaluate_social_reaction_stance(self.world, self.worker, self.boss)

        # High-presence evaluation (change profession to high-status)
        self.boss.economic.profession = "Sheriff"
        high_presence_assessment = evaluate_social_reaction_stance(self.world, self.worker, self.boss)

        # Threat score should increase relative to baseline due to presence
        self.assertGreater(high_presence_assessment.threat_score, baseline_assessment.threat_score)

        # Threat score should not be hostile
        self.assertLess(high_presence_assessment.threat_score, 95.0)

    def test_guarded_figure_biases_stance(self):
        from simulation.systems.social_reaction import evaluate_social_reaction_stance

        baseline_assessment = evaluate_social_reaction_stance(self.world, self.worker, self.unemployed)

        # Make the boss guard the unemployed NPC
        self.boss.social.follow_target_id = self.unemployed.id
        self.boss.social.follow_role = "guard"
        self.boss.x, self.boss.y = self.unemployed.x, self.unemployed.y

        # We need world.get_entities_in_radius to work and return the boss
        self.world.get_entities_in_radius = MagicMock(return_value=[self.boss])

        guarded_assessment = evaluate_social_reaction_stance(self.world, self.worker, self.unemployed)

        # The presence of a guard should increase the perceived threat/caution score
        self.assertGreater(guarded_assessment.threat_score, baseline_assessment.threat_score)
        self.assertLess(guarded_assessment.threat_score, 95.0)

    def test_presence_alone_does_not_force_hostility(self):
        from simulation.systems.social_reaction import evaluate_social_reaction_stance

        # Force baseline threat just below hostile
        self.worker.get_distrust_towards = MagicMock(return_value=94.0)

        # Make boss a Sheriff (high presence)
        self.boss.economic.profession = "Sheriff"

        assessment = evaluate_social_reaction_stance(self.world, self.worker, self.boss)

        # Even with high presence, it shouldn't cross 95 if base threat was < 95
        self.assertLess(assessment.threat_score, 95.0)
        self.assertEqual(assessment.stance, "fearful") # 94 is fearful (>=70, <95)

    def test_presence_reduces_conversation_openness(self):
        from simulation.systems.conversation_foundation import evaluate_conversation_foundation

        # Setup coordinates so they are within conversation distance
        self.worker.x, self.worker.y = 10, 10
        self.unemployed.x, self.unemployed.y = 10, 11

        # Empty radius (no one else around)
        self.world.get_entities_in_radius = MagicMock(return_value=[self.worker, self.unemployed])
        baseline_profile = evaluate_conversation_foundation(self.world, self.worker, self.unemployed)

        # Introduce a high-presence entity nearby
        self.boss.economic.profession = "Sheriff" # High presence
        self.boss.x, self.boss.y = 12, 12 # Nearby but not participating
        self.world.get_entities_in_radius = MagicMock(return_value=[self.worker, self.unemployed, self.boss])

        presence_profile = evaluate_conversation_foundation(self.world, self.worker, self.unemployed)

        # Openness should be reduced
        self.assertLess(presence_profile.openness, baseline_profile.openness)
        # Tone should shift from neutral/warm to guarded/respectful
        if baseline_profile.tone in {"neutral", "warm"} and presence_profile.openness < 0.7:
            self.assertIn(presence_profile.tone, {"guarded", "respectful"})

    def test_presence_does_not_override_strong_relationship(self):
        from simulation.systems.conversation_foundation import evaluate_conversation_foundation

        self.worker.x, self.worker.y = 10, 10
        self.unemployed.x, self.unemployed.y = 10, 11

        # Force a very strong relationship
        self.worker.social.relationships[self.unemployed.id] = 100

        # Introduce a high-presence entity nearby
        self.boss.economic.profession = "Sheriff"
        self.boss.x, self.boss.y = 12, 12
        self.world.get_entities_in_radius = MagicMock(return_value=[self.worker, self.unemployed, self.boss])

        profile = evaluate_conversation_foundation(self.world, self.worker, self.unemployed)

        # Openness should still be relatively high despite presence reduction
        self.assertGreater(profile.openness, 0.5)

    def test_presence_triggers_micro_reaction_pause(self):
        from simulation.systems.scheduling import run_npc_presence_micro_reactions

        self.worker.x, self.worker.y = 10, 10
        self.worker.schedule.current_task = "idle"
        self.world.game_time = 100 # Bypass cooldown

        self.boss.economic.profession = "Sheriff" # High presence
        self.boss.x, self.boss.y = 12, 12

        self.world.get_entities_in_radius = MagicMock(return_value=[self.boss])

        # Force the random check to pass
        with patch('random.random', return_value=0.0):
            result = run_npc_presence_micro_reactions(self.world, self.worker)

        self.assertTrue(result)
        self.assertIn("pause_until_tick", self.worker.task_context_data)
        self.assertGreater(self.worker.task_context_data["pause_until_tick"], self.world.game_time)

    def test_presence_micro_reaction_cooldown_prevents_spam(self):
        from simulation.systems.scheduling import run_npc_presence_micro_reactions

        self.worker.x, self.worker.y = 10, 10
        self.worker.schedule.current_task = "idle"
        self.world.game_time = 100

        self.boss.economic.profession = "Sheriff"
        self.world.get_entities_in_radius = MagicMock(return_value=[self.boss])

        # First trigger
        with patch('random.random', return_value=0.0):
            run_npc_presence_micro_reactions(self.world, self.worker)

        # Try again immediately
        result = run_npc_presence_micro_reactions(self.world, self.worker)
        self.assertFalse(result) # Should fail due to cooldown

    def test_presence_micro_reaction_does_not_interrupt_critical_tasks(self):
        from simulation.systems.scheduling import run_npc_presence_micro_reactions

        self.worker.schedule.current_task = "fleeing_from_player"
        self.boss.economic.profession = "Sheriff"
        self.world.get_entities_in_radius = MagicMock(return_value=[self.boss])

        with patch('random.random', return_value=0.0):
            result = run_npc_presence_micro_reactions(self.world, self.worker)

        self.assertFalse(result) # Should not pause or react while fleeing

if __name__ == '__main__':
    unittest.main()
