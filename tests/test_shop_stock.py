"""What a shopkeeper will actually sell you.

Trade used to read the merchant's stock from an allowlist of exactly two
building types - ["general_store", "mill"] - and that list was written out twice,
once to build the trade window and once to settle the transaction. Everyone else
traded out of their own pockets while the shop they were standing in stayed full.

Measured on a generated world, counting goods on the shelves of staffed
workplaces: 549 could be bought and 1250 could not. Among the unreachable were
302 at the blacksmith, 211 at the tavern, 146 of bread at the bakery, and the
butcher's entire stock. The economy was producing goods the player had no way to
obtain.

The rule is now the building's category rather than its name: places of business
sell their stock, civic buildings do not. The sheriff is not retailing the town's
swords and the library is not selling its books.
"""

import unittest
from types import SimpleNamespace

from engine import World


class TestWhichBuildingsSellTheirStock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = World(player_first_name="Shopper")
        cls.world._pre_simulate_world()

    def _worker_at(self, building_type):
        for npc in self.world.village_npcs:
            if npc.physical.is_dead:
                continue
            building = self.world.buildings_by_id.get(npc.schedule.work_building_id)
            if building is not None and building.building_type == building_type:
                return npc, building
        return None, None

    def _assert_sells_from_shelves(self, building_type):
        npc, building = self._worker_at(building_type)
        if npc is None:
            self.skipTest(f"no staffed {building_type} in this world")
        self.assertIs(
            self.world._merchant_stock(npc), building.building_inventory,
            f"a worker in a {building_type} was selling out of their pockets "
            f"while the building's stock sat on the shelves",
        )

    def test_a_baker_sells_the_bakery_bread(self):
        self._assert_sells_from_shelves("bakery")

    def test_a_tavern_keeper_sells_the_tavern_stock(self):
        self._assert_sells_from_shelves("tavern")

    def test_a_blacksmith_sells_the_forge_stock(self):
        self._assert_sells_from_shelves("blacksmith_shop")

    def test_a_butcher_sells_the_shop_stock(self):
        self._assert_sells_from_shelves("butcher_shop")

    def test_the_general_store_still_works(self):
        """The one case that always worked - it must not have been broken on the
        way to fixing the rest."""
        self._assert_sells_from_shelves("general_store")

    def test_a_civic_worker_does_not_retail_public_property(self):
        npc, building = self._worker_at("sheriff_office")
        if npc is None:
            self.skipTest("no staffed sheriff's office in this world")
        self.assertIsNot(self.world._merchant_stock(npc), building.building_inventory)

    def test_someone_with_no_workplace_trades_from_their_own_pack(self):
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.schedule.work_building_id = None
        self.assertIs(self.world._merchant_stock(npc), npc.economic.npc_inventory)

    def test_a_missing_workplace_does_not_raise(self):
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.schedule.work_building_id = "no-such-building"
        self.assertIs(self.world._merchant_stock(npc), npc.economic.npc_inventory)


class TestTheWindowAndTheTillAgree(unittest.TestCase):
    """The duplication was the actual defect: two copies of one allowlist, one
    for the trade window and one for the transaction. They have to be the same
    source or the player is shown a shelf they cannot buy from."""

    def setUp(self):
        self.world = World(player_first_name="Shopper")
        self.world._pre_simulate_world()

    def test_the_listed_goods_come_from_the_stock_that_is_sold_from(self):
        baker = None
        for npc in self.world.village_npcs:
            if npc.physical.is_dead:
                continue
            building = self.world.buildings_by_id.get(npc.schedule.work_building_id)
            if building is not None and building.building_type == "bakery":
                baker = npc
                break
        if baker is None:
            self.skipTest("no staffed bakery in this world")

        stock = self.world._merchant_stock(baker)
        sellable = {
            key for key, qty in stock.items()
            if key != "money" and isinstance(qty, int) and qty > 0
        }
        self.assertTrue(sellable, "the bakery had nothing on its shelves to sell")

        self.world.trade_ui_npc_target = baker
        self.world.trade_ui_active = True
        self.world.initialize_trade_session()

        if not self.world.trade_ui_active:
            self.skipTest("this baker refused to trade with the player")
        listed = {key for key, _, _ in self.world.trade_ui_merchant_inventory_snapshot}
        self.assertTrue(
            listed & sellable,
            f"the trade window listed {sorted(listed)} while the till sells "
            f"{sorted(sellable)}",
        )


class TestAStandInShopStillSells(unittest.TestCase):
    """Category is the rule, building type is the floor.

    Several existing tests stand a shop in as
    SimpleNamespace(building_type="general_store", ...) with no category. The
    first version of the category rule quietly stopped those shops selling
    anything, which is the wrong answer: a general store that has always
    retailed should not stop because a stand-in lacks an attribute.
    """

    @classmethod
    def setUpClass(cls):
        cls.world = World(seed=31)

    def test_a_general_store_with_no_category_still_sells_its_stock(self):
        shop = SimpleNamespace(
            building_type="general_store", building_inventory={"raw_log": 3, "money": 25}
        )
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.schedule.work_building_id = "stand_in"
        self.world.buildings_by_id["stand_in"] = shop

        self.assertIs(self.world._merchant_stock(npc), shop.building_inventory)

    def test_an_unknown_building_with_no_category_does_not(self):
        shop = SimpleNamespace(building_type="mystery_hut", building_inventory={"raw_log": 3})
        npc = next(n for n in self.world.village_npcs if not n.physical.is_dead)
        npc.schedule.work_building_id = "stand_in_2"
        self.world.buildings_by_id["stand_in_2"] = shop

        self.assertIs(self.world._merchant_stock(npc), npc.economic.npc_inventory)


if __name__ == "__main__":
    unittest.main()
