"""A haul survives the scheduler resetting the villager's task.

Two pieces of state describe a villager carrying something to a stockpile:

    npc.task_context           "stockpile_hauling"   - what job they are on
    npc.schedule.current_task  "hauling_to_source"   - what they are doing now

`_handle_npc_stockpile_haul_task` acts only when `current_task` is one of the
two haul states and returns False otherwise. But `current_task` belongs to the
scheduling system, and roughly forty places in the engine set it to IDLE while
exactly two of them clear `task_context`.

The reliable one is `_update_npc_movement`: when a villager finishes walking a
path it runs an if/elif chain over `current_task` and neither haul state appears
anywhere in it, so both fall through to `else: current_task = IDLE`. The moment
a hauler arrives at the log they were sent for, they are set to idle while still
holding the haul context.

After that the haul can never advance. The handler sees a task it does not
recognise and returns False; `_advance_produce_logs_task` sees an actor already
in hauling context and skips them as busy. Nobody advances the haul and nobody
reassigns the task, so the production task reports
`no_available_source_or_actor` on every retry until it expires. Traced with a
worker standing directly on top of the raw_log they were supposed to pick up,
retry_count climbing to 18.

The handler now re-derives the haul state from what the villager is carrying
rather than trusting `current_task` to have survived.
"""

import unittest

from tests.world_cache import fresh_world


def _wedged_world(seed=13):
    """A villager mid-haul whose current_task has been reset to idle."""
    world = fresh_world(seed=seed, pre_simulate=False)
    npc = world.village_npcs[0]

    stockpile = world.create_stockpile(npc.x + 2, npc.y, accepted_item_types={"raw_log"},
                                       max_item_count=50)
    source_coords = (npc.x, npc.y)          # standing on it, as observed
    world.drop_item_on_map("raw_log", 1, *source_coords)

    npc.task_context = "stockpile_hauling"
    npc.task_context_data = {
        "item_key": "raw_log",
        "source": {"source_type": "ground", "coords": source_coords, "item_key": "raw_log"},
        "destination_stockpile_id": stockpile.stockpile_id,
        "stockpile_reservation_id": None,
    }
    npc.current_sub_task = "Stockpiling raw_log"
    # What the movement handler leaves behind on arrival.
    npc.schedule.current_task = "idle"
    npc.schedule.current_path = []
    npc.schedule.current_destination_coords = None
    return world, npc, stockpile


class TestTheHaulRecovers(unittest.TestCase):
    def test_an_idle_hauler_is_put_back_on_the_haul(self):
        world, npc, _ = _wedged_world()
        self.assertTrue(
            world._handle_npc_stockpile_haul_task(npc),
            "the handler refused to advance a haul whose task had been reset",
        )
        self.assertNotEqual(npc.schedule.current_task, "idle",
                            "the villager was left idle while still holding a haul")

    def test_standing_on_the_item_they_pick_it_up(self):
        """The exact observed stall: on the log, holding the context, doing nothing."""
        world, npc, _ = _wedged_world()
        world._handle_npc_stockpile_haul_task(npc)
        self.assertEqual(npc.schedule.current_task, "hauling_to_stockpile",
                         "the log was not picked up despite standing on it")

    def test_a_carrier_is_sent_onward_not_back(self):
        """Someone already carrying the item must not be sent to fetch it again."""
        world, npc, _ = _wedged_world()
        world.items_on_map.clear()
        npc.economic.npc_inventory.add_item("raw_log", 1)

        world._handle_npc_stockpile_haul_task(npc)
        self.assertEqual(npc.schedule.current_task, "hauling_to_stockpile",
                         "a villager holding the log was sent back to the source")

    def test_the_recovery_is_recorded(self):
        """It should be visible in the traces, not a silent repair."""
        world, npc, _ = _wedged_world()
        world._handle_npc_stockpile_haul_task(npc)
        resumed = [e for e in world.interaction_trace_log
                   if e.get("trace_type") == "haul_task_resumed"]
        self.assertTrue(resumed, "no trace was written for the resumed haul")

    def test_someone_not_hauling_is_left_alone(self):
        """The guard must not adopt villagers who are doing something else."""
        world = fresh_world(seed=13, pre_simulate=False)
        npc = world.village_npcs[0]
        npc.task_context = None
        npc.schedule.current_task = "idle"
        self.assertFalse(world._handle_npc_stockpile_haul_task(npc))
        self.assertEqual(npc.schedule.current_task, "idle")


class TestTheStateMachinesAreStillOutOfSync(unittest.TestCase):
    """Documents the underlying defect the recovery works around.

    If the two are ever unified - one owner for "what is this villager doing" -
    this test should be deleted along with the recovery block. Until then it
    records why the recovery has to exist.
    """

    def test_the_movement_handler_does_not_know_the_haul_states(self):
        import inspect

        from engine import World

        source = inspect.getsource(World._update_npc_movement)
        self.assertNotIn(
            "hauling_to_source", source,
            "movement now handles the haul states - the recovery in "
            "_handle_npc_stockpile_haul_task may no longer be needed",
        )


if __name__ == "__main__":
    unittest.main()
