"""A month of reduced macro dispatch, checked for continuity and conservation.

Every one of the worst bugs found in this codebase was invisible to unit tests
and obvious after a few simulated weeks:

* daily systems gated on the clock landing exactly on midnight, so a player who
  slept skipped whole days of births, economy, trade and governance - and once
  the clock drifted off the boundary, forever;
* entities ageing a year per day, which emptied a village of 76 down to 7 inside
  sixty days;
* taxes never collected, because governance wanted one exact tick of the day;
* survival needs that stopped accruing, so sleeping through the night was free.

This is NOT a normal-play survival soak: nearby NPC movement, production and
per-tick survival/spoilage are omitted. Check real hiring, production and tax
receipts rather than assuming unemployment, stock and treasury balances must
improve monotonically. Consumption spends goods, payroll spends employer funds,
and construction/civic salaries spend taxes. Adding coins to item quantities
was neither a conservation check nor evidence that production had run.

The population/age/debt/birth alarms remain. Long-term economic balance needs
a full dispatcher soak; these checks do not certify that towns are prosperous.
"""

import unittest
from collections import Counter
from unittest.mock import patch

from config import DAY_LENGTH_TICKS
from engine import World
from tests.world_cache import fresh_world
import pytest

pytestmark = pytest.mark.slow  # long simulation run; see pytest.ini

DAYS = 30
SEED = 8675309


class TestVillageMacroContinuity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        world = fresh_world(seed=SEED)
        cls.start = cls._snapshot(world)
        cls.receipts = Counter()

        assign = world._assign_job
        produce = world._apply_abstract_production_for_worker
        collect = world._collect_daily_city_taxes

        def track_hire(npc, building, **kwargs):
            result = assign(npc, building, **kwargs)
            if result:
                assert npc.schedule.work_building_id == building.id
                cls.receipts["hires"] += 1
            return result

        def track_production(npc, building):
            before = Counter(dict(building.building_inventory))
            result = produce(npc, building)
            output = Counter(dict(building.building_inventory)) - before
            cls.receipts["produced_units"] += sum(q for k, q in output.items() if k != "money")
            return result

        def track_taxes(hall):
            holders = [*world.buildings_by_id.values(), *world.village_npcs, world.player]
            before_money = sum(world._get_trade_money_balance(h) for h in holders)
            before_treasury = world._get_trade_money_balance(hall)
            result = collect(hall)
            assert world._get_trade_money_balance(hall) - before_treasury == result
            assert sum(world._get_trade_money_balance(h) for h in holders) == before_money
            cls.receipts["taxes"] += result
            return result

        with patch.object(world, "_assign_job", side_effect=track_hire), \
             patch.object(world, "_apply_abstract_production_for_worker", side_effect=track_production), \
             patch.object(world, "_collect_daily_city_taxes", side_effect=track_taxes):
            for day in range(1, DAYS + 1):
                for _ in range(24):
                    world.game_time += DAY_LENGTH_TICKS // 24
                    world.process_abstract_simulation()
                    world.process_macro_daily_tick()
                world._update_economy()
                world._run_daily_governance()
                world._update_npc_ages()
                world._update_npc_careers()
                world._update_abstract_simulation()

        cls.world = world
        cls.end = cls._snapshot(world)

    @staticmethod
    def _snapshot(world):
        alive = [n for n in world.village_npcs if not n.physical.is_dead]
        hall = world.get_town_hall_building()
        supply = 0
        for row in world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is not None:
                    supply += sum(
                        int(q) for q in (getattr(village, "supply", {}) or {}).values()
                        if isinstance(q, int)
                    )
        return {
            "alive": len(alive),
            "unemployed": sum(1 for n in alive if n.economic.profession == "Unemployed"),
            "money": sum(int(getattr(n.economic, "money", 0) or 0) for n in alive),
            "treasury": int(hall.building_inventory.get("money", 0) or 0) if hall else 0,
            "supply": supply,
            "oldest": max((n.age for n in alive), default=0),
        }

    def test_the_village_is_still_populated(self):
        self.assertGreaterEqual(
            self.end["alive"], self.start["alive"] * 0.75,
            f"population fell from {self.start['alive']} to {self.end['alive']} "
            f"in {DAYS} days",
        )

    def test_nobody_aged_a_lifetime(self):
        """A month is not a generation. This is the shape of the ageing bug: a
        year of life per day of play."""
        self.assertLessEqual(
            self.end["oldest"] - self.start["oldest"], 1,
            f"the oldest villager went from {self.start['oldest']} to "
            f"{self.end['oldest']} in {DAYS} days",
        )

    def test_people_found_work(self):
        self.assertGreater(self.receipts["hires"], 0, "no actual job assignment succeeded in a month")

    def test_the_economy_moved(self):
        self.assertGreater(self.receipts["produced_units"], 0, "workers produced no physical goods in a month")

    def test_the_town_collected_taxes(self):
        """The shape of the governance bug: it wanted one exact tick of the day
        and a jumping clock never landed on it."""
        if self.world.get_town_hall_building() is None:
            self.skipTest("this world generated no town hall")
        self.assertGreater(self.receipts["taxes"], 0, "governance transferred no taxes in a month")

    def test_nobody_is_in_debt(self):
        debtors = [
            n for n in self.world.village_npcs
            if not n.physical.is_dead and int(getattr(n.economic, "money", 0) or 0) < 0
        ]
        self.assertEqual(
            debtors, [], f"{len(debtors)} villagers ended the month with negative money"
        )

    def test_children_were_born(self):
        """Not a rate check - just that the birth path is reachable at all. It
        was not, for as long as the daily systems were gated on an exact tick."""
        from simulation.history import BirthRecord

        births = [e for e in self.world.history.events if isinstance(e, BirthRecord)]
        youngest = min(
            (n.age for n in self.world.village_npcs if not n.physical.is_dead),
            default=99,
        )
        self.assertTrue(
            births or youngest < 5,
            f"no child was born in {DAYS} days and the youngest villager is "
            f"{youngest}",
        )


if __name__ == "__main__":
    unittest.main()
