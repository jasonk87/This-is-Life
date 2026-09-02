"""One seed, one simulation.

Getting here took three fixes, each found by asking why two runs of the same
seed disagreed:

1. Entities took `id(self)` - a memory address - as their id, and CPython
   reissues addresses the moment an object is freed. Anything ordering by id
   varied run to run. (Worse than a reproducibility problem: a newborn could
   inherit a dead villager's id. See test_entity_identity.)

2. Villages, buildings, claims and records took uuid.uuid4() ids, which draw
   from os.urandom and ignore random.seed. With entity ids fixed the same seed
   produced the same villagers - but placed them in a different village.

3. Ambient speech was gated on `time.time()`: a villager spoke once 10 to 30
   *real-world seconds* had passed. Whether that branch fired changed how much
   of the random stream a tick consumed, so the loop diverged. It also meant how
   talkative a village is depended on how fast the machine ran, and in a
   turn-based game a player who sat thinking for half a minute got a chorus on
   their next keypress.

4. The gossip service gave a queued line 0.75 *real seconds* to come back before
   falling back to canned text. Whether that landed on this tick or the next
   depended on how fast the machine ran - the same fault as the speech gate, one
   layer down. It now counts game ticks when the caller tells it what the clock
   says, and keeps the wall clock for anyone who does not.

Both halves are reproducible now: one seed builds the same world, and running
that world produces the same villagers in the same places doing the same things.

Worth recording how the last one was found, because two earlier answers were
wrong. Comparing aggregate counts said the loop was already deterministic - the
totals happened to agree while individual villagers did not. And an early check
said disabling the gossip service did not help, measured on those same aggregates;
comparing full per-villager state showed that it did, which pointed straight at
the timeout.
"""

import unittest

from config import DAY_LENGTH_TICKS
from engine import World
from simulation.systems.tick import run_world_tick
from simulation.systems.task_types import TaskType


def _world_fingerprint(seed):
    world = World(seed=seed)
    return (
        sorted((n.id, n.name, n.age, n.x, n.y, n.economic.profession)
               for n in world.village_npcs),
        sorted((b.building_type, b.x, b.y) for b in world.buildings_by_id.values()),
    )


class TestWorldGeneration(unittest.TestCase):
    def test_one_seed_builds_one_world(self):
        self.assertEqual(_world_fingerprint(2024), _world_fingerprint(2024))

    def test_different_seeds_build_different_worlds(self):
        """Reproducible must not mean everyone gets the same village."""
        self.assertNotEqual(_world_fingerprint(2024), _world_fingerprint(2025))


def _tick_fingerprint(seed, ticks=400):
    world = World(seed=seed)
    world._pre_simulate_world()
    for _ in range(ticks):
        run_world_tick(world)
    return sorted(
        (n.id, n.x, n.y, str(n.schedule.current_task), int(n.physical.hunger))
        for n in world.village_npcs
        if not n.physical.is_dead
    )


class TestTheTickLoop(unittest.TestCase):
    """Per-villager state, not aggregate counts.

    An earlier version of this compared how many villagers were resting, which
    agreed between runs while the villagers themselves were in different places -
    and reported the loop as deterministic when it was not.
    """

    def test_running_the_world_twice_from_one_seed_matches(self):
        self.assertEqual(_tick_fingerprint(2024), _tick_fingerprint(2024))

    def test_the_world_actually_moved(self):
        """Two identical fingerprints prove nothing if nothing happened."""
        world = World(seed=2024)
        world._pre_simulate_world()
        before = [(n.x, n.y, str(n.schedule.current_task)) for n in world.village_npcs]
        for _ in range(400):
            run_world_tick(world)
        after = [(n.x, n.y, str(n.schedule.current_task)) for n in world.village_npcs]
        self.assertNotEqual(before, after, "400 ticks changed nothing at all")


class TestAmbientSpeechRunsOnGameTime(unittest.TestCase):
    def setUp(self):
        self.world = World(seed=77)

    def test_the_gap_is_measured_in_ticks(self):
        low, high = self.world.AMBIENT_SPEECH_GAP_TICKS
        self.assertLess(low, high)
        # A gap of a handful of ticks would be every few seconds of game time;
        # one of many thousands would be less than once a day.
        self.assertGreater(low, 60)
        self.assertLess(high, DAY_LENGTH_TICKS)

    def test_speech_timing_does_not_read_the_wall_clock(self):
        """The clock a villager checks has to be the one the game runs on.

        Freezing game_time and letting real time pass must not make anybody
        speak - under the old rule it was the only thing that made them.
        """
        import time as real_time

        world = self.world
        world._pre_simulate_world()
        world.game_time = 5000
        for npc in world.village_npcs:
            npc.last_speech_time = world.game_time

        world._handle_npc_speech()
        real_time.sleep(0.05)
        world._handle_npc_speech()

        spoke = [
            npc for npc in world.village_npcs
            if npc.last_speech_time != world.game_time
        ]
        self.assertEqual(
            spoke, [],
            "a villager spoke while game time stood still, so the gate is still "
            "reading real time",
        )

    def test_enough_game_time_does_let_them_speak(self):
        """The other half: the gate must open, not just stay shut."""
        world = self.world
        world._pre_simulate_world()
        world.game_time = 0
        for npc in world.village_npcs:
            npc.last_speech_time = 0

        world.game_time = world.AMBIENT_SPEECH_GAP_TICKS[1] * 4
        world._handle_npc_speech()

        moved_on = [
            npc for npc in world.village_npcs
            if npc.last_speech_time != 0
        ]
        self.assertTrue(
            moved_on,
            "hours of game time passed and not one villager said anything",
        )


if __name__ == "__main__":
    unittest.main()
