
import unittest
from unittest.mock import patch, MagicMock
from engine import World, Chunk, Village, NPC
import json

class TestGame(unittest.TestCase):
    @patch('engine.World._call_ollama')
    def test_faction_reputation_system(self, mock_call_ollama):
        # Canned response for NPC generation to speed up world creation
        mock_npc_data = {
            "name": "Test Merchant", "personality": "greedy", "family_ties": "none",
            "attitude_to_player": "neutral", "dialogue": ["Hello."],
            "wealth_level": "average", "combat_behavior": "avoids_combat",
            "base_attack_name": "fists"
        }
        mock_call_ollama.return_value = json.dumps(mock_npc_data)

        world = World()

        # Manually create a village and a merchant NPC to ensure the test can run
        village = Village()
        merchant_npc = NPC(x=0, y=0, name="Test Merchant", dialogue=[], personality="greedy", family_ties="", attitude_to_player="neutral")
        merchant_npc.profession = "Merchant"
        world.village_npcs.append(merchant_npc)


        # 1. Test Initialization
        self.assertIn("common_folk", world.player.reputation)
        self.assertIn("merchants_guild", world.player.reputation)
        self.assertIn("law_and_order", world.player.reputation)
        self.assertEqual(world.player.reputation["common_folk"], 0)

        # 2. Test Adjusting Reputation
        world.player.adjust_reputation("common_folk", 15)
        self.assertEqual(world.player.reputation["common_folk"], 15)
        world.player.adjust_reputation("merchants_guild", -10)
        self.assertEqual(world.player.reputation["merchants_guild"], -10)

        # 3. Test Pricing Affect
        # Set a baseline price
        world.player.reputation["merchants_guild"] = 0
        base_price = world.get_dynamic_price("axe_stone", village, is_selling=False)

        # High reputation should give a discount (lower price)
        world.player.reputation["merchants_guild"] = 100
        price_high_rep_buy = world.get_dynamic_price("axe_stone", village, is_selling=False)
        self.assertLess(price_high_rep_buy, base_price)

        # Low reputation should give a surcharge (higher price)
        world.player.reputation["merchants_guild"] = -100
        price_low_rep_buy = world.get_dynamic_price("axe_stone", village, is_selling=False)
        self.assertGreater(price_low_rep_buy, base_price)

        # Test selling prices
        base_sell_price = world.get_dynamic_price("axe_stone", village, is_selling=True)
        world.player.reputation["merchants_guild"] = 100
        price_high_rep_sell = world.get_dynamic_price("axe_stone", village, is_selling=True)
        self.assertGreater(price_high_rep_sell, base_sell_price)

if __name__ == '__main__':
    unittest.main()
