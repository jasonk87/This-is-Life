"""Traveling merchants exist, and they travel.

Two faults, one behind the other:

* _spawn_traveling_merchants wrapped the whole merchant in a `try` whose first
  line is `json.loads(llm_response)` - and _call_llm_for_worldgen returns ""
  by design, because world generation is meant to stay local. So the parse threw
  before the NPC was built and every world had zero traveling merchants. The
  villager spawner handles the same empty response with a fallback and carries
  on; this one did not.

* Once they existed they never moved. A merchant's job is the road between
  villages, which is almost always away from the player, so they are dormant
  nearly all the time - and run_npc_traveling_merchant_policy only runs for NPCs
  in active chunks, while the daily travel pass reads self.village_npcs and
  merchants live in self.npcs. Two merchants stood in their spawn village for
  ever, taking inter-village trade and the rumours they carry with them.
"""

import unittest

from config import DAY_LENGTH_TICKS
from engine import World


def _merchants(world):
    return [
        npc for npc in world.npcs
        if getattr(npc, "economic", None)
        and npc.economic.profession == "Traveling Merchant"
        and not npc.physical.is_dead
    ]


class TestMerchantsExist(unittest.TestCase):
    def test_a_generated_world_has_traveling_merchants(self):
        world = World(player_first_name="Tester")
        self.assertGreater(
            len(_merchants(world)), 0,
            "no traveling merchant was created - the spawner's fallback is missing again",
        )

    def test_they_are_given_a_name_and_stock(self):
        world = World(player_first_name="Tester")
        for merchant in _merchants(world):
            self.assertTrue(str(merchant.name).strip())
            self.assertGreater(merchant.economic.money, 0)
            carried = sum(
                quantity for key, quantity in dict(merchant.economic.npc_inventory).items()
                if key != "item_references" and isinstance(quantity, int)
            )
            self.assertGreater(carried, 0, "a merchant set out with nothing to sell")


class TestMerchantsTravelOffScreen(unittest.TestCase):
    """A world per test, deliberately.

    Sharing one across the class made these order-dependent and they failed in
    the full suite while passing alone: the on-screen test leaves a merchant
    awake and the arrival test advances forty days, so whichever ran first
    decided the answer for the rest.
    """

    def setUp(self):
        self.world = World(player_first_name="Tester")
        self.world._pre_simulate_world()
        self.merchants = _merchants(self.world)
        # These cover off-screen travel, so put the merchants off-screen. Whether
        # they spawn dormant otherwise depends on where they land relative to the
        # player, which made this flaky about one run in five.
        for merchant in self.merchants:
            merchant.is_sleeping = True

    def test_there_are_merchants_to_move(self):
        self.assertGreater(len(self.merchants), 0)

    def test_they_reach_other_settlements_over_time(self):
        world = self.world
        start = {m.id: (m.x, m.y) for m in self.merchants}
        visited = {m.id: set() for m in self.merchants}

        arrivals = 0
        for day in range(1, 41):
            world.game_time = day * DAY_LENGTH_TICKS
            arrivals += world._advance_abstract_merchant_travel()
            for merchant in self.merchants:
                village = world._get_npc_settlement(merchant)
                if village is not None:
                    visited[merchant.id].add(village.id)

        moved = [m for m in self.merchants if (m.x, m.y) != start[m.id]]
        self.assertGreater(arrivals, 0, "no merchant completed a journey in 40 days")
        self.assertTrue(moved, "no merchant left the village they spawned in")
        self.assertTrue(
            any(len(seen) > 1 for seen in visited.values()),
            "no merchant ever saw a second settlement",
        )

    def test_an_arrived_merchant_is_ready_to_trade(self):
        """Arrival hands them back to the task the on-screen policy expects."""
        world = self.world
        for day in range(1, 41):
            world.game_time = day * DAY_LENGTH_TICKS
            world._advance_abstract_merchant_travel()
        tasks = {m.schedule.current_task for m in self.merchants}
        self.assertTrue(
            tasks & {"lingering_in_village", "traveling_to_village"},
            f"merchants ended up in an unexpected state: {tasks}",
        )

    def test_an_active_merchant_is_left_to_walk(self):
        """On-screen merchants are the policy's job, not the abstract pass's."""
        world = self.world
        merchant = self.merchants[0]
        merchant.is_sleeping = False   # this one is the on-screen case
        merchant.travel.is_traveling = False
        before = (merchant.x, merchant.y)

        world.game_time += DAY_LENGTH_TICKS
        world._advance_abstract_merchant_travel()

        self.assertEqual((merchant.x, merchant.y), before)
        self.assertFalse(merchant.travel.is_traveling)


if __name__ == "__main__":
    unittest.main()
