"""Where an exhausted actor goes to rest.

`_apply_fatigue_override_behavior` called `self._find_nearest_rest_target(actor)`,
and that method did not exist. Not renamed, not moved - never written. So every
tick on which fatigue was the selected survival pressure raised

    AttributeError: 'World' object has no attribute '_find_nearest_rest_target'

from inside `run_world_tick`, taking the whole tick with it.

Nothing in the test suite routed through that branch, which is why 1781 passing
tests said nothing about it. The sandbox's fatigue_rest_override_runtime_soak did,
and had presumably been crashing for as long as the branch had been there - it is
one of the 34 scenarios the suite never runs.

The cold twin, `_apply_cold_override_behavior`, is the model: same shape, same
`campfire:`/`shelter:` id vocabulary, so `_is_valid_survival_target` can check
what comes back.
"""

import unittest

from engine import NPC
from simulation.systems.tick import run_world_tick
from tools.simulation_scenarios import _create_headless_world, _create_village


def _world_with_somewhere_to_rest(seed=1, *, shelter=True, campfire=True):
    world, chunk = _create_headless_world(seed)
    _create_village(world, chunk, center=(8, 8))
    world.ambient_temperature = -1.0
    if shelter:
        world.create_shelter_zone([(7, 7), (7, 8)], exposure_reduction_modifier=0.6,
                                  recovery_modifier=1.2)
    if campfire:
        world.create_campfire_runtime(7, 7, fuel_item_type="raw_log", fuel_quantity=5,
                                      max_fuel_quantity=8, minimum_fuel_quantity=1,
                                      burn_rate_per_tick=1)
    return world


def _exhausted(world, x=20, y=20):
    actor = NPC(x, y, name="Tired Worker")
    actor.fatigue_modifier = 0.95
    world.village_npcs.append(actor)
    return actor


class TestTheTickLoopSurvivesAnExhaustedActor(unittest.TestCase):
    """The regression. Everything else here is about picking a good target."""

    def test_ticking_with_a_tired_actor_does_not_raise(self):
        world = _world_with_somewhere_to_rest()
        _exhausted(world)
        world.create_production_task(
            "produce_logs",
            metadata={"item_key": "raw_log", "target_quantity": 1, "priority": 10, "urgency": 10},
            expiration_ticks=200)

        for _ in range(120):
            run_world_tick(world)  # raised AttributeError on the first fatigue override

    def test_it_still_does_not_raise_with_nowhere_to_rest(self):
        """No shelter, no fire. The caller has a warning path for this; use it."""
        world = _world_with_somewhere_to_rest(shelter=False, campfire=False)
        _exhausted(world)

        for _ in range(120):
            run_world_tick(world)


class TestChoosingSomewhereToRest(unittest.TestCase):
    def test_nothing_to_rest_at_returns_nothing(self):
        world = _world_with_somewhere_to_rest(shelter=False, campfire=False)
        actor = _exhausted(world)
        self.assertEqual(world._find_nearest_rest_target(actor), (None, None))

    def test_a_shelter_is_found(self):
        world = _world_with_somewhere_to_rest(campfire=False)
        actor = _exhausted(world)
        target_id, position = world._find_nearest_rest_target(actor)
        self.assertTrue(str(target_id).startswith("shelter:"))
        self.assertIn(position, [(7, 7), (7, 8)])

    def test_shelter_is_preferred_to_a_fire_at_the_same_distance(self):
        """Sheltered rest recovers faster than rest beside a fire, so break the tie that way."""
        world = _world_with_somewhere_to_rest()
        actor = _exhausted(world)
        target_id, _ = world._find_nearest_rest_target(actor)
        self.assertTrue(str(target_id).startswith("shelter:"),
                        f"picked {target_id} over the shelter at the same spot")

    def test_what_it_returns_passes_the_survival_target_check(self):
        """The two must agree, or the caller re-picks a target every tick forever."""
        world = _world_with_somewhere_to_rest()
        actor = _exhausted(world)
        target_id, position = world._find_nearest_rest_target(actor)
        self.assertTrue(world._is_valid_survival_target(target_id, position))

    def test_a_burnt_out_fire_is_not_offered(self):
        world = _world_with_somewhere_to_rest(shelter=False)
        actor = _exhausted(world)
        for campfire in world.campfires_by_id.values():
            campfire.fuel_quantity = 0
        self.assertEqual(world._find_nearest_rest_target(actor), (None, None))


class TestTheActorActuallyGetsThere(unittest.TestCase):
    """A target that is never walked to would satisfy everything above."""

    def test_a_tired_actor_reaches_shelter_and_rests(self):
        world = _world_with_somewhere_to_rest()
        actor = _exhausted(world)
        world.create_production_task(
            "produce_logs",
            metadata={"item_key": "raw_log", "target_quantity": 1, "priority": 10, "urgency": 10},
            expiration_ticks=200)

        for _ in range(600):
            run_world_tick(world)

        traces = [entry.get("trace_type") for entry in world.interaction_trace_log]
        self.assertIn("fatigue_override_route_started", traces, "never set off towards rest")
        self.assertIn("actor_resting", traces, "arrived but never rested")
        self.assertLessEqual(abs(actor.x - 7) + abs(actor.y - 7), 2,
                             f"ended up at {(actor.x, actor.y)}, nowhere near the shelter")


if __name__ == "__main__":
    unittest.main()
