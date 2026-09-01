"""Settlements the player is not standing in still do their jobs.

Roughly four in five villagers are dormant at any moment - only chunks near the
player run the full simulation - so whatever the abstract hourly pass does is
what most of the world's economy *is*. Its consume/produce block used to sit
after a `break` inside the tile-harvest branch, unreachable, which left wheat at
a farm the only thing any off-screen worker could make while every settlement
ate its stores and rotted the rest.
"""

import unittest

import engine
from engine import Building, World
from entities.base import NPC


def _worker(profession: str) -> NPC:
    npc = NPC(0, 0, f"Test {profession}")
    npc.economic.profession = profession
    return npc


def _workshop(building_type: str, stock: dict) -> Building:
    building = Building(0, 0, 5, 5, building_type=building_type, category="commercial_workplace")
    for item_key, quantity in stock.items():
        building.building_inventory[item_key] = quantity
    return building


class TestAbstractProduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = object.__new__(World)

    def _run(self, profession, building_type, stock):
        building = _workshop(building_type, stock)
        World._apply_abstract_production_for_worker(self.world, _worker(profession), building)
        return building

    def test_a_smith_turns_ore_and_coal_into_an_ingot(self):
        building = self._run("Blacksmith", "blacksmith_shop", {"iron_ore": 4, "coal": 2})
        self.assertEqual(building.building_inventory.get("iron_ingot", 0), 1)
        self.assertEqual(building.building_inventory.get("iron_ore", 0), 2, "ore was not consumed")
        self.assertEqual(building.building_inventory.get("coal", 0), 1, "coal was not consumed")

    def test_a_baker_turns_flour_into_bread(self):
        building = self._run("Baker", "bakery", {"flour": 3})
        self.assertEqual(building.building_inventory.get("bread", 0), 1)
        self.assertEqual(building.building_inventory.get("flour", 0), 2)

    def test_nothing_is_made_without_the_inputs(self):
        building = self._run("Blacksmith", "blacksmith_shop", {"iron_ore": 1})
        self.assertEqual(building.building_inventory.get("iron_ingot", 0), 0)
        self.assertEqual(building.building_inventory.get("iron_ore", 0), 1, "ore was spent for nothing")

    def test_a_farmer_sows_seed_and_still_harvests_in_the_same_hour(self):
        """plant_seeds only draws stock; it is the front of the chain, not the end."""
        building = self._run("Farmer", "farm", {"wheat_seeds": 5})
        self.assertEqual(building.building_inventory.get("wheat_seeds", 0), 4, "seed was not sown")
        self.assertEqual(building.building_inventory.get("wheat", 0), 1, "no crop was harvested")

    def test_a_farm_without_seed_still_harvests(self):
        building = self._run("Farmer", "farm", {})
        self.assertEqual(building.building_inventory.get("wheat", 0), 1)

    def test_tile_harvesting_does_not_conjure_wheat_in_a_workshop(self):
        building = self._run("Farmer", "blacksmith_shop", {})
        self.assertEqual(building.building_inventory.get("wheat", 0), 0)


class TestOffscreenSettlementsProduce(unittest.TestCase):
    """The same thing, measured on a real world rather than a fixture."""

    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Auditor")
        cls.world._pre_simulate_world()

    def _village_stock(self):
        total = {}
        for row in self.world.chunks:
            for chunk in row:
                village = getattr(chunk, "village", None)
                if village is None:
                    continue
                for building in village.buildings:
                    for item_key, quantity in dict(building.building_inventory).items():
                        if item_key != "item_references" and isinstance(quantity, int):
                            total[item_key] = total.get(item_key, 0) + quantity
        return total

    def test_dormant_workers_exist_to_simulate(self):
        dormant_with_jobs = [
            npc
            for npc in self.world.village_npcs
            if getattr(npc, "is_sleeping", False) and npc.schedule.work_building_id
        ]
        self.assertGreater(len(dormant_with_jobs), 0, "no off-screen workers to check")

    def test_something_somewhere_is_produced_off_screen(self):
        before = self._village_stock()
        for _ in range(engine.DAY_LENGTH_TICKS // 8):
            self.world.update()
        after = self._village_stock()

        gained = {
            item_key: quantity - before.get(item_key, 0)
            for item_key, quantity in after.items()
            if quantity > before.get(item_key, 0)
        }
        # Rotten food is decay, not labour - it grows whether or not anyone works.
        gained.pop("rotten_food", None)
        self.assertTrue(
            gained,
            "no settlement produced anything over three simulated hours",
        )


if __name__ == "__main__":
    unittest.main()
