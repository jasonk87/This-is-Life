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

5. The service still handed a result back on whichever tick its worker thread
   happened to finish on. Fix 4 made *falling back* tick-based and left
   *succeeding* on the wall clock, which was the same fault in the half of the
   path nobody had looked at. It mattered because finishing a chronicle rolls
   item quality from `random`: a result landing one tick earlier moved every
   draw after it. Results are now held until the tick the request comes due on,
   arrived or not. See services/llm_gossip.poll_completed.

World generation is reproducible outright, and so is the tick loop - now with the
gossip service running as well as without it. The qualification this file used to
carry is gone because fix 5 removed its cause, not because the claim got louder.

How fast the model answers still decides *what* a villager says - a request that
beats its deadline carries the model's words, one that misses carries the
fallback - and nothing downstream branches on which.

Worth recording how fix 5 was established, because the obvious test does not
establish it. Running the loop twice with the service enabled passes with the fix
and without it: the jitter a worker thread has on this machine is milliseconds
and a tick is far longer, so results land on the same tick either way and the
end-to-end test cannot tell the two versions apart. What pins the mechanism is
tests/test_gossip_release_timing.py, which drives arrival directly and, without
the fix, releases at ticks 100, 105 and 119 where it should release at 120 three
times. TestTheAsynchronousLayerNoLongerLeaksIntoTheSimulation below is kept as a
guard on the property, not as evidence for it.

Worth recording how the earlier ones were established too, because three answers
here were wrong, all from measuring too coarsely:

* comparing aggregate counts said the loop was already deterministic - the totals
  agreed while individual villagers stood in different places;
* an early check said disabling the service did not help, measured on those same
  aggregates;
* and after the timeout fix, three matching runs were taken as proof. They were a
  sample. Later work that put more villagers in more buildings raised the amount
  of gossip in flight and the divergence came back.

Per-villager state, several runs, and a stated condition - not one comparison of
one number.
"""

import random
import time
import unittest

from config import DAY_LENGTH_TICKS
from engine import World
from services.llm_gossip import AsyncLLMGossipService
from tests.world_cache import fresh_world
from simulation.systems.tick import run_world_tick
from simulation.systems.task_types import TaskType
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini


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


# Two hundred and fifty ticks. The divergences this file exists to catch showed
# up inside the first fifty when they were real, and the run length was costing
# the suite two minutes across three tests to keep looking after that.
def _tick_fingerprint(seed, ticks=250):
    world = fresh_world(seed=seed)
    # The gossip service is a real background thread and is deliberately left
    # out of this. It is asynchronous by design; asking it to be reproducible
    # would mean asking it not to be asynchronous.
    world._gossip_llm_service = None
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
        world = fresh_world(seed=2024)
        before = [(n.x, n.y, str(n.schedule.current_task)) for n in world.village_npcs]
        for _ in range(250):
            run_world_tick(world)
        after = [(n.x, n.y, str(n.schedule.current_task)) for n in world.village_npcs]
        self.assertNotEqual(before, after, "250 ticks changed nothing at all")


class TestAmbientSpeechRunsOnGameTime(unittest.TestCase):
    def setUp(self):
        self.world = fresh_world(seed=77, pre_simulate=False)

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


class _JitteryGossipService(AsyncLLMGossipService):
    """A service whose answers come back after a real, and varying, delay.

    Standing in for a model that is quick on one run and slow on the next. The
    jitter is drawn from its own unseeded Random so it differs between runs and
    does not touch the global stream the simulation draws from - the whole point
    is that two runs see *different* thread timing and reach the same world.
    """

    _jitter = random.Random()

    def _generate_text(self, request):
        time.sleep(self._jitter.uniform(0.0, 0.004))
        return f"Word is {request.subject_name} had a hand in it."


class TestTheAsynchronousLayerNoLongerLeaksIntoTheSimulation(unittest.TestCase):
    """The boundary this file used to state as a limitation.

    A result is now released on the tick its request came due rather than the
    tick its thread happened to finish on, so how fast the model answers decides
    what a villager says and not when anything happens.

    This class guards that property; it does not demonstrate it. Measured, it
    passes with the fix and without it, because the jitter a worker thread has
    here is far shorter than a tick. tests/test_gossip_release_timing.py drives
    arrival directly and does fail without the fix - that is the evidence, and
    this is the thing that would notice if the property were lost some other way.
    """

    @staticmethod
    def _run(gossip_enabled):
        world = fresh_world(seed=2024)
        delivered = 0
        if gossip_enabled:
            service = _JitteryGossipService()
            world._gossip_llm_service = service
            poll = service.poll_completed

            def counting_poll(now_ticks=None):
                nonlocal delivered
                results = poll(now_ticks=now_ticks)
                delivered += len(results)
                return results

            service.poll_completed = counting_poll
        else:
            world._gossip_llm_service = None
        for _ in range(200):
            run_world_tick(world)
        state = sorted(
            (n.id, n.x, n.y, str(n.schedule.current_task))
            for n in world.village_npcs if not n.physical.is_dead
        )
        return state, delivered

    def test_without_the_service_two_runs_match(self):
        self.assertEqual(self._run(False)[0], self._run(False)[0])

    def test_with_the_service_two_runs_match(self):
        first, first_delivered = self._run(True)
        second, second_delivered = self._run(True)
        # Without this the test could pass by never exercising the thread at all.
        self.assertGreater(min(first_delivered, second_delivered), 0,
                           "no gossip was delivered, so this proves nothing")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
