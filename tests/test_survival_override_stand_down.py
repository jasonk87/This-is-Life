"""A survival pressure with nothing to aim at must not end someone's working life.

An active survival override scores an actor -9999 for every production task, which
takes them out of the labour pool completely. That is right while they are walking
towards food or a fire. It is wrong when there is nothing to walk to, because the
pressures only fall by being answered: hunger by eating, cold by getting warm. An
actor who cannot reach either never recovers, so the override never lifts, so they
never work again - including at the hauling, farming and fire-building that would
have produced the thing they were missing.

That is a death spiral a settlement cannot climb out of. A bad harvest or a hard
winter stops the village dead, permanently, and the work that would have fixed it
is exactly the work nobody is doing any more.

Found in the sandbox: a lone worker two tiles from a felled log, starving in a
world with no food in it, cycling between "assigned a haul" and "idle" every
eighty ticks and never moving. With the fix, `actor_skipped_survival_override`
went from 7 to 0 over the same run.

Both halves matter. Standing down when there is no target must not turn into
never seeking food at all - TestSeekingStillHappens is what stops the fix
degenerating that way.
"""

import unittest

from engine import NPC
from simulation.systems.tick import run_world_tick
from tools.simulation_scenarios import (_create_headless_world, _create_village,
                                        _make_it_winter)


def _starving_world(seed=1):
    world, chunk = _create_headless_world(seed)
    _create_village(world, chunk, center=(8, 8))
    return world, chunk


def _hungry_actor(world, hunger=0.85, x=6, y=5):
    actor = NPC(x, y, name="Hungry Worker")
    actor.economic.profession = "Laborer"
    actor.hunger = hunger
    world.village_npcs.append(actor)
    return actor


class TestNothingToEat(unittest.TestCase):
    def test_the_override_stands_down_instead_of_latching(self):
        world, _ = _starving_world()
        actor = _hungry_actor(world)

        for _ in range(150):
            run_world_tick(world)

        self.assertFalse(
            getattr(actor, "survival_override_active", False),
            "still held under a hunger override with no food anywhere in the world",
        )

    def test_it_says_so_in_the_trace(self):
        world, _ = _starving_world()
        _hungry_actor(world)

        for _ in range(150):
            run_world_tick(world)

        traces = [entry.get("trace_type") for entry in world.interaction_trace_log]
        self.assertIn("survival_override_stood_down", traces)

    def test_the_actor_is_not_skipped_by_the_scheduler(self):
        """The -9999 is the actual harm, so name it.

        Needs the whole arrangement, not just a hungry actor and a task: the
        scheduler only reaches the suitability check when there is real work to
        score against, so a bare task produces no skip traces either way and the
        assertion is worth nothing. This is the sandbox setup that produced seven
        skips before the fix and none after - a stockpile that wants logs and a
        felled log two tiles from the worker.
        """
        from simulation.systems.interaction import ActionIntent
        from tile_types import Tile

        world, chunk = _starving_world()
        stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log"},
                                           max_item_count=200)
        actor = _hungry_actor(world)
        chunk.tiles[6][6] = Tile(char="T", color=(34, 139, 34), passable=False,
                                 name="Tree", properties={"is_tree": True})
        world.interaction_resolver.resolve(
            ActionIntent(actor_id=actor.id, action_type="chop_tree", target_pos=(6, 6)), world)
        world.create_production_task(
            "produce_logs",
            metadata={"stockpile_id": stockpile.stockpile_id, "item_key": "raw_log",
                      "target_quantity": 1, "priority": 3, "urgency": 3},
            expiration_ticks=600)

        for _ in range(300):
            run_world_tick(world)

        skipped = [entry for entry in world.interaction_trace_log
                   if entry.get("trace_type") == "actor_skipped_survival_override"]
        self.assertEqual(
            skipped, [],
            f"scheduler skipped the actor {len(skipped)} time(s) for an override "
            "that had nothing to aim at",
        )

    def test_hunger_is_not_quietly_cured_by_standing_down(self):
        """Standing down is about work, not about no longer being hungry."""
        world, _ = _starving_world()
        actor = _hungry_actor(world, hunger=0.85)

        for _ in range(150):
            run_world_tick(world)

        self.assertGreater(float(actor.hunger), 0.85,
                           "hunger went down without anything being eaten")


class TestAnOverrideThatCanBePursuedStillTakesTheActorOffWork(unittest.TestCase):
    """The property the stand-down must not have cost us.

    A selected override is supposed to make its actor unavailable to the
    scheduler - that is what the -9999 is for, and it is right while they are on
    their way to food or a fire. The fix only stands down when there is nothing
    to walk to, so this must still hold when there is.

    Worth pinning here rather than leaving it to the sandbox, because the sandbox
    scenario that asserted it was getting its evidence from the bug. In
    survival_override_arbitration_runtime_soak the only sustained override was a
    hunger one that could never be answered, so its actor was skipped constantly
    for being stuck rather than for being busy - and the assertion passed on that.
    The scenario has since been repaired (it opened with an assignment to
    `world.ambient_temperature`, which is recomputed every tick, so it was never
    actually cold) and now passes on real evidence: 23 skips, no stand-downs, cold
    selected on 1989 of 2000 ticks.

    Keeping the property here anyway. It is the sort of thing that should not
    depend on one dev scenario's setup surviving unchanged.
    """

    def test_a_cold_actor_with_a_reachable_shelter_is_skipped_for_work(self):
        world, _ = _starving_world()
        # Winter via game_time, not by assigning ambient_temperature: that field
        # is recomputed from the season every tick and an assignment to it is
        # gone before the first tick ends. This test had that inert line in it.
        _make_it_winter(world)
        world.create_shelter_zone([(40, 40), (40, 41)],
                                  exposure_reduction_modifier=0.5, recovery_modifier=1.0)
        actor = NPC(5, 5, name="Cold Worker")
        actor.economic.profession = "Laborer"
        actor.cold_exposure = 0.95
        world.village_npcs.append(actor)
        stockpile = world.create_stockpile(4, 4, accepted_item_types={"raw_log"},
                                           max_item_count=200)
        world.create_production_task(
            "produce_logs",
            metadata={"stockpile_id": stockpile.stockpile_id, "item_key": "raw_log",
                      "target_quantity": 1, "priority": 10, "urgency": 10},
            expiration_ticks=600)

        for _ in range(200):
            run_world_tick(world)

        traces = [entry.get("trace_type") for entry in world.interaction_trace_log]
        self.assertEqual(getattr(actor, "survival_override_reason", None), "seeking_warmth")
        self.assertNotIn("survival_override_stood_down", traces,
                         "stood down even though there was a shelter to walk to")
        self.assertIn("actor_skipped_survival_override", traces,
                      "an actor on their way to shelter should not also be taking work")


class TestSeekingStillHappens(unittest.TestCase):
    """The other half: with food on the map, hunger must still take priority."""

    def test_an_actor_with_food_available_still_takes_the_override(self):
        world, _ = _starving_world()
        actor = _hungry_actor(world, x=10, y=10)
        # drop_item_on_map, not a raw dict: the eat interaction calls
        # pop_item_reference on whatever it finds, which a plain dict does not
        # have. And cooked_meat rather than simple_food - is_entity_edible
        # rejects simple_food even though _find_nearest_edible_food_target
        # lists it among the keys it searches for.
        world.drop_item_on_map("cooked_meat", 3, 11, 10)

        seeking = False
        for _ in range(60):
            run_world_tick(world)
            if getattr(actor, "survival_override_reason", None) == "seeking_food":
                seeking = True
                break

        self.assertTrue(seeking,
                        "never went after food that was one tile away")


if __name__ == "__main__":
    unittest.main()
