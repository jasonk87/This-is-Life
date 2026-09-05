import unittest
from unittest.mock import patch, MagicMock

from config import SECONDS_PER_GAME_TICK
from engine import World, NPC
from main import handle_playing_input
import tcod.event
from tests.world_cache import fresh_world


class TestRealtimeSimulation(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=42, pre_simulate=False)
        self.world.is_paused = False
        self.world.simulation_speed = 1.0

    def test_default_simulation_speed_and_pause_state(self):
        self.assertEqual(self.world.simulation_speed, 1.0)
        self.assertFalse(self.world.is_paused)

    def test_pause_toggle_via_space_or_p(self):
        # Space key toggles pause
        event = MagicMock(spec=tcod.event.KeyDown)
        event.sym = tcod.event.KeySym.SPACE
        handle_playing_input(event, self.world, None)
        self.assertTrue(self.world.is_paused)

        # Space key toggles resume
        handle_playing_input(event, self.world, None)
        self.assertFalse(self.world.is_paused)

        # P key toggles pause
        event.sym = getattr(tcod.event.KeySym, 'p', 112)
        handle_playing_input(event, self.world, None)
        self.assertTrue(self.world.is_paused)

    def test_speed_keys_1_2_3_0(self):
        event = MagicMock(spec=tcod.event.KeyDown)

        # '2' sets 2x Fast
        event.sym = getattr(tcod.event.KeySym, 'N2', 50)
        handle_playing_input(event, self.world, None)
        self.assertEqual(self.world.simulation_speed, 2.0)
        self.assertFalse(self.world.is_paused)

        # '3' sets 4x Ultra
        event.sym = getattr(tcod.event.KeySym, 'N3', 51)
        handle_playing_input(event, self.world, None)
        self.assertEqual(self.world.simulation_speed, 4.0)
        self.assertFalse(self.world.is_paused)

        # '0' sets Paused
        event.sym = getattr(tcod.event.KeySym, 'N0', 48)
        handle_playing_input(event, self.world, None)
        self.assertTrue(self.world.is_paused)

        # '1' sets 1x Normal
        event.sym = getattr(tcod.event.KeySym, 'N1', 49)
        handle_playing_input(event, self.world, None)
        self.assertEqual(self.world.simulation_speed, 1.0)
        self.assertFalse(self.world.is_paused)

    def test_single_step_while_paused(self):
        self.world.is_paused = True
        initial_time = self.world.game_time
        event = MagicMock(spec=tcod.event.KeyDown)
        event.sym = getattr(tcod.event.KeySym, 'PERIOD', 46)
        turn_taken = handle_playing_input(event, self.world, None)
        self.assertTrue(turn_taken)
        self.assertGreater(self.world.game_time, initial_time)
        self.assertTrue(self.world.is_paused)

    def test_realtime_accumulator_ticks_in_playing_state(self):
        """Simulate time passage and verify ticks occur at proper rate."""
        initial_time = self.world.game_time
        dt = 0.5  # Half a second at 10 ticks/s = 5 ticks
        speed = 1.0
        tick_accumulator = dt * speed
        ticks_executed = 0

        while tick_accumulator >= SECONDS_PER_GAME_TICK:
            self.world.update()
            tick_accumulator -= SECONDS_PER_GAME_TICK
            ticks_executed += 1

        self.assertEqual(ticks_executed, 5)
        self.assertEqual(self.world.game_time, initial_time + 5)


if __name__ == "__main__":
    unittest.main()
