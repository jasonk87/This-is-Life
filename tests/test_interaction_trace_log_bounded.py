"""The trace log has to stop growing.

The world keeps three diagnostic buffers. Validation warnings stop at 500 and
decision explanations at 400. The interaction trace log stopped at nothing: it
took roughly 550 entries a tick with ninety villagers on the map, and nothing ever
removed any of them.

Measured over 6000 ticks - under half a game day - it reached 3,282,865 entries
and the process 1,988 MB, both climbing in a straight line. A full day of play
would not have fitted in memory. The log is also pickled into saves, so every save
carried the entire history of the game to that point.

After bounding: 20,000 entries and about 70 MB, flat across the same run.

Nothing in the game reads the log. `build_world_debug_snapshot` takes a tail
slice, and the sandbox scenarios - which assert on traces from thousands of ticks
earlier - set `interaction_trace_log_limit = 0` and keep everything. Both of those
are covered below, because a bound that broke the sandbox would have been swapped
for one leak in place of another.
"""

import unittest

TICKS = 700  # about 25k traces at ~36/tick, so the 20k bound is actually crossed

from engine import NPC
from simulation.systems.tick import run_world_tick
from simulation.validation import MAX_STORED_INTERACTION_TRACES, trim_interaction_traces
from tools.simulation_scenarios import _create_headless_world, _create_village


def _busy_world(seed=1):
    """A world under the game's bound, with enough going on to fill the log.

    An empty headless world emits no traces at all, so a bound test built on one
    passes while proving nothing - which is what the first version of this file
    did until test_it_is_actually_being_exercised caught it. Six labourers and a
    stockpile that wants logs produce about 36 traces a tick.
    """
    world, chunk = _create_headless_world(seed)
    _create_village(world, chunk, center=(8, 8))
    del world.interaction_trace_log_limit   # the sandbox sets 0; want the default
    for i in range(6):
        worker = NPC(5 + i, 5, name=f"Worker {i}")
        worker.economic.profession = "Laborer"
        world.village_npcs.append(worker)
    stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log"},
                                       max_item_count=200)
    world.create_production_task(
        "produce_logs",
        metadata={"stockpile_id": stockpile.stockpile_id, "item_key": "raw_log",
                  "target_quantity": 5, "priority": 5, "urgency": 5},
        expiration_ticks=5000)
    return world


class TestTheLogStopsGrowing(unittest.TestCase):
    def test_it_stays_within_the_bound_while_ticking(self):
        world = _busy_world()
        for _ in range(TICKS):
            run_world_tick(world)
            # created lazily on first append, so do not assume it exists yet
            self.assertLessEqual(
                len(getattr(world, "interaction_trace_log", []) or []),
                MAX_STORED_INTERACTION_TRACES,
                "trace log went past its bound during a tick",
            )

    def test_it_is_actually_being_exercised(self):
        """A log that never fills would satisfy the bound and prove nothing."""
        world = _busy_world()
        for _ in range(TICKS):
            run_world_tick(world)
        self.assertEqual(
            len(getattr(world, "interaction_trace_log", []) or []),
            MAX_STORED_INTERACTION_TRACES,
            "the log never reached its bound, so the trimming was never exercised")

    def test_the_oldest_entries_are_the_ones_dropped(self):
        world = _busy_world()
        world.interaction_trace_log = [{"trace_type": f"marker_{i}"} for i in range(50)]
        world.interaction_trace_log_limit = 10
        trim_interaction_traces(world)

        kept = [entry["trace_type"] for entry in world.interaction_trace_log]
        self.assertEqual(kept, [f"marker_{i}" for i in range(40, 50)])


class TestTheSandboxKeepsEverything(unittest.TestCase):
    """Scenarios assert on traces from thousands of ticks ago."""

    def test_a_limit_of_zero_means_unbounded(self):
        world, chunk = _create_headless_world(1)
        _create_village(world, chunk, center=(8, 8))
        self.assertEqual(getattr(world, "interaction_trace_log_limit", None), 0)

        world.interaction_trace_log = [{"trace_type": f"marker_{i}"} for i in range(50)]
        trim_interaction_traces(world)
        self.assertEqual(len(world.interaction_trace_log), 50)

    def test_the_sandbox_really_does_accumulate_past_the_game_bound(self):
        world, chunk = _create_headless_world(1)
        _create_village(world, chunk, center=(8, 8))
        world.interaction_trace_log = [{"trace_type": "x"}] * (MAX_STORED_INTERACTION_TRACES + 5)
        trim_interaction_traces(world)
        self.assertEqual(len(world.interaction_trace_log),
                         MAX_STORED_INTERACTION_TRACES + 5)


class TestTrimmingIsSafe(unittest.TestCase):
    def test_a_world_with_no_log_is_left_alone(self):
        world, _chunk = _create_headless_world(1)
        world.interaction_trace_log = None
        trim_interaction_traces(world)  # must not raise

    def test_a_nonsense_limit_falls_back_to_the_default(self):
        world, chunk = _create_headless_world(1)
        _create_village(world, chunk, center=(8, 8))
        world.interaction_trace_log_limit = "not a number"
        world.interaction_trace_log = [{"trace_type": "x"}] * (MAX_STORED_INTERACTION_TRACES + 100)
        trim_interaction_traces(world)
        self.assertEqual(len(world.interaction_trace_log), MAX_STORED_INTERACTION_TRACES)


if __name__ == "__main__":
    unittest.main()
