import unittest

import engine
from engine import NPC, World


class TestGetSpouse(unittest.TestCase):
    """World._get_spouse: shared lookup used by the household financial
    support helpers below."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=301)

    def _npc(self, name="NPC"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)

    def test_unmarried_npc_has_no_spouse(self):
        npc = self._npc()
        self.assertIsNone(self.world._get_spouse(npc))

    def test_married_npc_resolves_to_partner(self):
        npc = self._npc("A")
        partner = self._npc("B")
        npc.social.family_ties["partner_id"] = partner.id
        partner.social.family_ties["partner_id"] = npc.id
        self.world.village_npcs.extend([npc, partner])

        self.assertIs(self.world._get_spouse(npc), partner)

    def test_spouse_field_falls_back_to_legacy_spouse_id_key(self):
        npc = self._npc("A")
        partner = self._npc("B")
        npc.social.family_ties["spouse_id"] = partner.id
        self.world.village_npcs.extend([npc, partner])

        self.assertIs(self.world._get_spouse(npc), partner)

    def test_dead_spouse_is_not_returned(self):
        npc = self._npc("A")
        partner = self._npc("B")
        npc.social.family_ties["partner_id"] = partner.id
        partner.physical.is_dead = True
        self.world.village_npcs.extend([npc, partner])

        self.assertIsNone(self.world._get_spouse(npc))

    def test_player_can_be_resolved_as_a_spouse(self):
        npc = self._npc("A")
        npc.social.family_ties["partner_id"] = self.world.player.id
        self.world.village_npcs.append(npc)

        self.assertIs(self.world._get_spouse(npc), self.world.player)


class TestHouseholdAvailableMoney(unittest.TestCase):
    """World._get_household_available_money: read-only viability estimate
    used by utility-AI decisions, NOT an actual transfer."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=302)

    def _npc(self, name="NPC"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)

    def test_unmarried_npc_only_counts_their_own_money(self):
        npc = self._npc()
        npc.economic.money = 12
        self.assertEqual(self.world._get_household_available_money(npc), 12)

    def test_married_npcs_combined_money_is_summed(self):
        npc = self._npc("A")
        partner = self._npc("B")
        npc.social.family_ties["partner_id"] = partner.id
        partner.social.family_ties["partner_id"] = npc.id
        npc.economic.money = 5
        partner.economic.money = 200
        self.world.village_npcs.extend([npc, partner])

        self.assertEqual(self.world._get_household_available_money(npc), 205)

    def test_available_money_check_does_not_move_any_money(self):
        npc = self._npc("A")
        partner = self._npc("B")
        npc.social.family_ties["partner_id"] = partner.id
        partner.social.family_ties["partner_id"] = npc.id
        npc.economic.money = 5
        partner.economic.money = 200
        self.world.village_npcs.extend([npc, partner])

        self.world._get_household_available_money(npc)

        self.assertEqual(npc.economic.money, 5)
        self.assertEqual(partner.economic.money, 200)


class TestDrawHouseholdSupport(unittest.TestCase):
    """World._draw_household_support: the actual (real) transfer used at
    purchase time - informal support, not full pooling."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=303)

    def _npc(self, name="NPC"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)

    def _marry(self, a, b):
        a.social.family_ties["partner_id"] = b.id
        b.social.family_ties["partner_id"] = a.id
        self.world.village_npcs.extend([a, b])

    def test_unmarried_npc_gets_no_support(self):
        npc = self._npc()
        npc.economic.money = 0
        self.assertFalse(self.world._draw_household_support(npc, 10))
        self.assertEqual(npc.economic.money, 0)

    def test_spouse_with_enough_money_covers_the_shortfall_exactly(self):
        npc = self._npc("A")
        partner = self._npc("B")
        self._marry(npc, partner)
        npc.economic.money = 0
        partner.economic.money = 50

        self.assertTrue(self.world._draw_household_support(npc, 20))

        self.assertEqual(npc.economic.money, 20)
        self.assertEqual(partner.economic.money, 30)

    def test_spouse_who_cannot_cover_the_full_amount_gives_no_partial_support(self):
        npc = self._npc("A")
        partner = self._npc("B")
        self._marry(npc, partner)
        npc.economic.money = 0
        partner.economic.money = 5  # less than the requested shortfall

        self.assertFalse(self.world._draw_household_support(npc, 20))

        # Nothing moved - no partial payment left dangling.
        self.assertEqual(npc.economic.money, 0)
        self.assertEqual(partner.economic.money, 5)

    def test_zero_or_negative_shortfall_is_a_trivial_success_with_no_transfer(self):
        npc = self._npc("A")
        partner = self._npc("B")
        self._marry(npc, partner)
        partner.economic.money = 50

        self.assertTrue(self.world._draw_household_support(npc, 0))
        self.assertEqual(partner.economic.money, 50)


class TestBuyFoodUsesHouseholdSupport(unittest.TestCase):
    """Integration: World._npc_buy_or_collect_food (the real hunger-purchase
    path) should draw on a spouse's money rather than failing outright when
    the NPC's own wallet can't cover the price."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World()

    def test_broke_npc_can_still_buy_food_via_a_wealthy_spouse(self):
        from unittest.mock import patch

        tavern = engine.Building(0, 0, 4, 4, building_type="tavern", category="commercial_workplace")
        tavern.building_inventory.add_item("apple", 1, quality="Fine", crafter_name="Orchard")
        item_reference = tavern.building_inventory.get_item_reference("apple")

        buyer = engine.NPC(0, 0, name="Buyer", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        spouse = engine.NPC(0, 0, name="Spouse", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        buyer.social.family_ties["partner_id"] = spouse.id
        spouse.social.family_ties["partner_id"] = buyer.id
        self.world.village_npcs.extend([buyer, spouse])

        buyer.economic.money = 0
        spouse.economic.money = item_reference.value * 5

        with patch.object(self.world, "_get_village_for_npc", return_value=None):
            bought = self.world._npc_buy_or_collect_food(buyer, tavern)

        self.assertTrue(bought)
        bought_item = buyer.economic.npc_inventory.get_item_reference("apple")
        self.assertIsNotNone(bought_item)
        # Spouse's balance actually decreased by the price paid.
        self.assertLess(spouse.economic.money, item_reference.value * 5)

    def test_broke_and_unmarried_npc_still_fails_to_buy_food(self):
        from unittest.mock import patch

        tavern = engine.Building(0, 0, 4, 4, building_type="tavern", category="commercial_workplace")
        tavern.building_inventory.add_item("apple", 1, quality="Fine", crafter_name="Orchard")

        buyer = engine.NPC(0, 0, name="Buyer", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        buyer.economic.money = 0

        with patch.object(self.world, "_get_village_for_npc", return_value=None):
            bought = self.world._npc_buy_or_collect_food(buyer, tavern)

        self.assertFalse(bought)


class TestExecuteBuyFoodUsesHouseholdSupport(unittest.TestCase):
    """The utility-AI routine hunger path (evaluate_needs_utility ->
    _set_buy_food_goal -> _execute_buy_food) is a SEPARATE code path from
    World._npc_buy_or_collect_food's survival-override path above, with its
    own direct building_inventory/money handling. Needed its own
    household-support wiring at the actual purchase point, or an NPC could
    "decide" to buy food based on combined household money and then fail
    to execute the purchase anyway."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=304)

    def test_broke_npc_buys_food_via_spousal_support(self):
        from unittest.mock import patch, MagicMock
        from simulation.systems.utility_ai import _execute_buy_food
        from engine import Building

        buyer = NPC(5, 5, name="Buyer", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        spouse = NPC(5, 5, name="Spouse", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        buyer.social.family_ties["partner_id"] = spouse.id
        spouse.social.family_ties["partner_id"] = buyer.id
        self.world.village_npcs.extend([buyer, spouse])

        buyer.economic.money = 0
        spouse.economic.money = 100
        buyer.physical.hunger = 80

        building = Building(0, 0, 5, 5, building_type="general_store", category="commercial")
        building.building_inventory["bread"] = 3
        self.world._get_building_global_center_coords = MagicMock(return_value=(5, 5))

        with patch.object(self.world, "_get_village_for_npc") as mock_village, \
             patch.object(self.world, "get_dynamic_price", return_value=10):
            fake_village = MagicMock()
            fake_village.buildings = [building]
            mock_village.return_value = fake_village

            _execute_buy_food(self.world, buyer)

        # Price (10) drawn from spouse then immediately spent - buyer ends
        # back at their starting 0, spouse is down exactly the price paid.
        self.assertEqual(buyer.economic.money, 0)
        self.assertEqual(spouse.economic.money, 90)
        self.assertEqual(buyer.physical.hunger, 30)

    def test_broke_and_unmarried_npc_fails_to_buy_and_stays_hungry(self):
        from unittest.mock import patch, MagicMock
        from simulation.systems.utility_ai import _execute_buy_food
        from engine import Building

        buyer = NPC(5, 5, name="Buyer", dialogue=["Hi"], personality="villager", player_id=self.world.player.id)
        buyer.economic.money = 0
        buyer.physical.hunger = 80

        building = Building(0, 0, 5, 5, building_type="general_store", category="commercial")
        building.building_inventory["bread"] = 3
        self.world._get_building_global_center_coords = MagicMock(return_value=(5, 5))

        with patch.object(self.world, "_get_village_for_npc") as mock_village, \
             patch.object(self.world, "get_dynamic_price", return_value=10):
            fake_village = MagicMock()
            fake_village.buildings = [building]
            mock_village.return_value = fake_village

            _execute_buy_food(self.world, buyer)

        self.assertEqual(buyer.economic.money, 0)
        self.assertEqual(buyer.physical.hunger, 80)  # unchanged - purchase failed


class TestUtilityAIHouseholdViability(unittest.TestCase):
    """evaluate_needs_utility / _evaluate_wealth_utility decision-making
    should treat combined household money as available spending power, not
    just the NPC's own wallet."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=305)

    def _npc(self, name="NPC"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)

    def _marry(self, a, b):
        a.social.family_ties["partner_id"] = b.id
        b.social.family_ties["partner_id"] = a.id
        self.world.village_npcs.extend([a, b])

    def test_hungry_broke_npc_with_wealthy_spouse_chooses_buy_food_over_theft(self):
        from unittest.mock import patch
        import simulation.systems.utility_ai as utility_ai

        npc = self._npc("A")
        spouse = self._npc("B")
        self._marry(npc, spouse)
        npc.economic.money = 0
        spouse.economic.money = 500
        npc.physical.hunger = npc.physical.max_hunger

        with patch.object(utility_ai, "_set_buy_food_goal") as mock_buy, \
             patch.object(utility_ai, "_set_forage_goal") as mock_forage, \
             patch.object(utility_ai, "_set_steal_goal") as mock_steal:
            utility_ai.evaluate_needs_utility(self.world, npc)

        mock_buy.assert_called_once()
        mock_steal.assert_not_called()

    def test_hungry_broke_and_unmarried_npc_does_not_get_a_buy_food_option(self):
        from unittest.mock import patch
        import simulation.systems.utility_ai as utility_ai

        npc = self._npc("A")
        npc.economic.money = 0
        npc.physical.hunger = npc.physical.max_hunger

        with patch.object(utility_ai, "_set_buy_food_goal") as mock_buy:
            utility_ai.evaluate_needs_utility(self.world, npc)

        mock_buy.assert_not_called()

    def test_unemployed_npc_with_wealthy_spouse_does_not_trigger_poverty_branch(self):
        from simulation.systems.utility_ai import _evaluate_wealth_utility

        npc = self._npc("A")
        spouse = self._npc("B")
        self._marry(npc, spouse)
        npc.economic.money = 0
        npc.economic.profession = "Unemployed"
        spouse.economic.money = 500

        triggered = _evaluate_wealth_utility(self.world, npc)

        self.assertFalse(triggered)

    def test_unemployed_npc_without_a_spouse_still_triggers_poverty_branch(self):
        from unittest.mock import patch
        import simulation.systems.utility_ai as utility_ai

        npc = self._npc("A")
        npc.economic.money = 0
        npc.economic.profession = "Unemployed"

        with patch.object(utility_ai, "_set_steal_goal"):
            triggered = utility_ai._evaluate_wealth_utility(self.world, npc)

        self.assertTrue(triggered)


class TestHouseholdTheftDeterrent(unittest.TestCase):
    """_household_theft_deterrent: the new scoring nudge that makes a
    spouse's ongoing (not just shortfall-covering) money lower the appeal of
    stealing, closing the gap where an already crime-prone NPC's
    steal_food/beg_or_steal score never factored in household wealth at all
    once inside the personality-modifier scoring."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=306)

    def _npc(self, name="NPC"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality="villager", player_id=self.world.player.id)

    def _marry(self, a, b):
        a.social.family_ties["partner_id"] = b.id
        b.social.family_ties["partner_id"] = a.id
        self.world.village_npcs.extend([a, b])

    def test_no_spouse_means_no_deterrent(self):
        from simulation.systems.utility_ai import _household_theft_deterrent

        npc = self._npc()
        self.assertEqual(_household_theft_deterrent(self.world, npc), 0)

    def test_broke_spouse_means_no_deterrent(self):
        from simulation.systems.utility_ai import _household_theft_deterrent

        npc = self._npc("A")
        spouse = self._npc("B")
        self._marry(npc, spouse)
        spouse.economic.money = 0

        self.assertEqual(_household_theft_deterrent(self.world, npc), 0)

    def test_deterrent_scales_with_spouse_money(self):
        from simulation.systems.utility_ai import _household_theft_deterrent

        npc = self._npc("A")
        spouse = self._npc("B")
        self._marry(npc, spouse)

        spouse.economic.money = 100
        self.assertEqual(_household_theft_deterrent(self.world, npc), 5)  # 100 // 20

        spouse.economic.money = 300
        self.assertEqual(_household_theft_deterrent(self.world, npc), 15)  # 300 // 20

    def test_deterrent_is_capped_so_a_very_wealthy_spouse_does_not_zero_out_crime(self):
        from simulation.systems.utility_ai import _household_theft_deterrent, HOUSEHOLD_THEFT_DETERRENT_CAP

        npc = self._npc("A")
        spouse = self._npc("B")
        self._marry(npc, spouse)
        spouse.economic.money = 100_000

        self.assertEqual(_household_theft_deterrent(self.world, npc), HOUSEHOLD_THEFT_DETERRENT_CAP)


class TestHouseholdWealthDeterrentFlipsHungerDecision(unittest.TestCase):
    """Integration: evaluate_needs_utility's steal_food option previously had
    no household-wealth term at all, only personality modifiers - a
    greedy+chaotic NPC married to a wealthy spouse could still "choose" to
    steal even though buy_food was a perfectly viable, available option,
    because steal_food's inflated personality bonus (+40 greedy +50 chaotic)
    could outscore buy_food's base score. The deterrent should now pull that
    back down enough for buy_food to win in a realistic wealthy-household
    case, without changing anything for an NPC with no such spouse."""

    def setUp(self):
        engine.ENABLE_OLLAMA_CONNECTION = False
        engine.ENABLE_LLM_CONNECTION = False
        self.world = World(seed=307)

    def _npc(self, name="NPC", personality="villager"):
        return NPC(0, 0, name=name, dialogue=["Hi"], personality=personality, player_id=self.world.player.id)

    def _marry(self, a, b):
        a.social.family_ties["partner_id"] = b.id
        b.social.family_ties["partner_id"] = a.id
        self.world.village_npcs.extend([a, b])

    def test_chaotic_npc_with_moderately_wealthy_spouse_now_chooses_buy_food(self):
        """At household money=220 the numbers land right at the tipping
        point: steal_food's fixed +50 chaotic bonus (80 total) would have
        beaten buy_food's money-scaled score (72) before this fix. The new
        deterrent (min(25, 220 // 20) = 11) pulls steal down to 69, letting
        buy_food win - a real decision flip caused by household wealth, not
        just a smaller score gap that never changed the outcome."""
        from unittest.mock import patch
        import simulation.systems.utility_ai as utility_ai

        npc = self._npc("A", personality="chaotic drifter")
        spouse = self._npc("B")
        self._marry(npc, spouse)
        npc.economic.money = 0
        spouse.economic.money = 220
        npc.physical.hunger = npc.physical.max_hunger

        with patch.object(utility_ai, "_set_buy_food_goal") as mock_buy, \
             patch.object(utility_ai, "_set_steal_goal") as mock_steal:
            utility_ai.evaluate_needs_utility(self.world, npc)

        mock_buy.assert_called_once()
        mock_steal.assert_not_called()

    def test_same_chaotic_npc_without_a_spouse_still_steals(self):
        """Control: confirms the flip above is really due to the spousal
        deterrent, not some other change - an identical NPC with no
        household money at all still chooses to steal (steal_food's 80
        beats buy_food, which isn't even offered as an option with 0
        money)."""
        from unittest.mock import patch
        import simulation.systems.utility_ai as utility_ai

        npc = self._npc("A", personality="chaotic drifter")
        npc.economic.money = 0
        npc.physical.hunger = npc.physical.max_hunger

        with patch.object(utility_ai, "_set_buy_food_goal") as mock_buy, \
             patch.object(utility_ai, "_set_steal_goal") as mock_steal:
            utility_ai.evaluate_needs_utility(self.world, npc)

        mock_buy.assert_not_called()
        mock_steal.assert_called_once()

    def test_maximally_crime_prone_npc_still_steals_despite_a_modest_deterrent(self):
        """The deterrent is capped (see HOUSEHOLD_THEFT_DETERRENT_CAP,
        confirmed directly in TestHouseholdTheftDeterrent) so it nudges
        rather than neuters: a greedy+chaotic NPC's combined +90 trait bonus
        (and buy_food's own -20 greedy penalty) should still comfortably win
        out over legitimate options against a modestly-supportive spouse -
        marriage alone shouldn't make a genuinely crime-prone personality
        stop stealing. (A spouse wealthy enough to make buy_food's own
        money-scaled score dominate on its own isn't a useful case here -
        that's buy_food's existing household-money term doing its job, not
        the deterrent; see the capped-value unit test above for that.)"""
        from unittest.mock import patch
        import simulation.systems.utility_ai as utility_ai

        npc = self._npc("A", personality="greedy and chaotic drifter")
        spouse = self._npc("B")
        self._marry(npc, spouse)
        npc.economic.money = 0
        spouse.economic.money = 50
        npc.physical.hunger = npc.physical.max_hunger

        with patch.object(utility_ai, "_set_steal_goal") as mock_steal:
            utility_ai.evaluate_needs_utility(self.world, npc)

        mock_steal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
