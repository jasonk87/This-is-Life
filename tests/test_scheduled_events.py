import unittest
from unittest.mock import patch

import config
import engine
from engine import NPC, World, SCHEDULED_EVENT_DEFINITIONS
from simulation.systems.scheduling import update_npc_daily_goal_policy
from simulation.world_model import Village
from tests.world_cache import fresh_world


class TestScheduledEventDispatcher(unittest.TestCase):
    """Ideation-audit item 6: SCHEDULED_EVENT_DEFINITIONS-driven dispatcher,
    checked once per day (see World._run_scheduled_events). Harvest Festival
    is the first entry; these tests exercise the dispatcher generically
    (start/end/demand/status-effect/messages), not anything Harvest-Festival-
    specific, since the whole point is that a second event could reuse this
    with no changes to the dispatcher itself."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=6001, pre_simulate=False)
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(30, 30)]}
        self.world.villages = [self.village]
        self.world.chunks[0][0].village = self.village

    def _set_to_autumn_day_zero(self):
        self.world.current_season_index = self.world.seasons.index("Autumn")
        self.world.game_time = 0
        self.world.scheduled_events_last_checked_day = -1

    def test_harvest_festival_starts_on_first_autumn_day(self):
        self._set_to_autumn_day_zero()

        self.world._run_scheduled_events()

        self.assertIn("harvest_festival", self.world.active_scheduled_events)

    def test_harvest_festival_does_not_start_mid_autumn(self):
        self.world.current_season_index = self.world.seasons.index("Autumn")
        self.world.game_time = config.DAY_LENGTH_TICKS * 5  # day 5 of Autumn, not day 0
        self.world.scheduled_events_last_checked_day = -1

        self.world._run_scheduled_events()

        self.assertNotIn("harvest_festival", self.world.active_scheduled_events)

    def test_harvest_festival_does_not_start_outside_autumn(self):
        self.world.current_season_index = self.world.seasons.index("Summer")
        self.world.game_time = 0
        self.world.scheduled_events_last_checked_day = -1

        self.world._run_scheduled_events()

        self.assertNotIn("harvest_festival", self.world.active_scheduled_events)

    def test_dispatcher_is_gated_to_once_per_day(self):
        self._set_to_autumn_day_zero()
        self.world._run_scheduled_events()
        self.world._end_scheduled_event("harvest_festival")  # manually end it

        # Same day again - should NOT restart, since the dispatcher already
        # checked today.
        self.world._run_scheduled_events()

        self.assertNotIn("harvest_festival", self.world.active_scheduled_events)

    def test_event_ends_after_its_duration(self):
        self._set_to_autumn_day_zero()
        self.world._run_scheduled_events()
        definition = next(d for d in SCHEDULED_EVENT_DEFINITIONS if d["key"] == "harvest_festival")

        self.world.game_time = config.DAY_LENGTH_TICKS * definition["duration_days"]
        self.world.scheduled_events_last_checked_day = -1
        self.world._run_scheduled_events()

        self.assertNotIn("harvest_festival", self.world.active_scheduled_events)

    def test_start_boosts_village_demand_for_configured_items(self):
        self._set_to_autumn_day_zero()
        definition = next(d for d in SCHEDULED_EVENT_DEFINITIONS if d["key"] == "harvest_festival")

        self.world._run_scheduled_events()

        for item_key in definition["demand_boost_items"]:
            self.assertEqual(self.village.demand.get(item_key, 0), definition["demand_boost_amount"])

    def test_end_reverses_the_demand_boost(self):
        self._set_to_autumn_day_zero()
        self.world._run_scheduled_events()
        definition = next(d for d in SCHEDULED_EVENT_DEFINITIONS if d["key"] == "harvest_festival")

        self.world._end_scheduled_event("harvest_festival")

        for item_key in definition["demand_boost_items"]:
            self.assertEqual(self.village.demand.get(item_key, 0), 0)

    def test_start_applies_status_effect_to_living_npcs_and_player(self):
        villager = NPC(0, 0, name="Villager", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        dead_villager = NPC(0, 0, name="Ghost", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        dead_villager.physical.is_dead = True
        self.world.village_npcs.extend([villager, dead_villager])
        self._set_to_autumn_day_zero()

        self.world._run_scheduled_events()

        self.assertIn("Festive", villager.physical.status_effects)
        self.assertIn("Festive", self.world.player.physical.status_effects)
        self.assertNotIn("Festive", dead_villager.physical.status_effects)

    def test_end_removes_the_status_effect(self):
        villager = NPC(0, 0, name="Villager", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        self.world.village_npcs.append(villager)
        self._set_to_autumn_day_zero()
        self.world._run_scheduled_events()

        self.world._end_scheduled_event("harvest_festival")

        self.assertNotIn("Festive", villager.physical.status_effects)
        self.assertNotIn("Festive", self.world.player.physical.status_effects)

    def test_start_and_end_post_distinct_chat_log_messages(self):
        self._set_to_autumn_day_zero()

        self.world._run_scheduled_events()
        self.assertTrue(any("Harvest Festival has begun" in m for m in self.world.chat_log))

        self.world._end_scheduled_event("harvest_festival")
        self.assertTrue(any("has come to an end" in m for m in self.world.chat_log))

    def test_crowd_drawing_flag_reflects_active_state(self):
        self.assertFalse(self.world._is_crowd_drawing_event_active())

        self._set_to_autumn_day_zero()
        self.world._run_scheduled_events()
        self.assertTrue(self.world._is_crowd_drawing_event_active())

        self.world._end_scheduled_event("harvest_festival")
        self.assertFalse(self.world._is_crowd_drawing_event_active())

    def test_ending_an_inactive_key_is_a_safe_no_op(self):
        self.world._end_scheduled_event("harvest_festival")  # never started
        self.assertNotIn("harvest_festival", self.world.active_scheduled_events)


class TestFestivalDrawsCrowdDuringLeisure(unittest.TestCase):
    """The scheduling.py side of item 6: adults get an elevated chance of
    heading to the town square during leisure hours while a draws_crowd
    event is active, and this has zero effect when no event is running."""

    LEISURE_TIME = int(config.DAY_LENGTH_TICKS * (config.WORK_END_TIME_RATIO + 0.85) / 2)

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = fresh_world(seed=6002, pre_simulate=False)
        self.village = Village()
        self.village.interaction_points = {"town_square_center": [(30, 30)]}
        self.world.villages = [self.village]
        self.world.chunks[0][0].village = self.village

    def _make_adult(self, x, y):
        npc = NPC(x, y, name="Adult", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        npc.age = 30
        npc.economic.profession = "Farmer"
        npc.leisure_timer = 0
        return npc

    def test_heads_to_town_square_when_festival_active(self):
        npc = self._make_adult(2, 2)
        self.world.village_npcs.append(npc)
        self.world.current_season_index = self.world.seasons.index("Autumn")
        self.world.game_time = 0
        self.world.scheduled_events_last_checked_day = -1
        self.world._run_scheduled_events()
        self.world.game_time = self.LEISURE_TIME  # move off day-0 tick without re-triggering dispatcher gating

        with patch("random.random", return_value=0.0):
            update_npc_daily_goal_policy(self.world, npc, self.LEISURE_TIME)

        self.assertEqual(npc.schedule.current_task, "attending_festival")
        self.assertEqual(npc.schedule.current_destination_coords, (30, 30))

    def test_no_special_behavior_when_no_festival_active(self):
        npc = self._make_adult(2, 2)
        self.world.village_npcs.append(npc)

        with patch("random.random", return_value=0.0):
            update_npc_daily_goal_policy(self.world, npc, self.LEISURE_TIME)

        self.assertNotEqual(npc.schedule.current_task, "attending_festival")


if __name__ == "__main__":
    unittest.main()
