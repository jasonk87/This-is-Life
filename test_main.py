
import unittest
from unittest.mock import patch, MagicMock
from engine import World, Chunk, Village, NPC
from data.quests import QUEST_DEFINITIONS
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

    @patch('engine.World._call_ollama')
    def test_faction_quest_system(self, mock_call_ollama):
        # Canned responses for various LLM calls
        mock_responses = {
            "npc_personality": json.dumps({
                "name": "Test Woodcutter", "personality": "friendly", "family_ties": "none",
                "attitude_to_player": "neutral", "dialogue": ["Hello, traveller."],
                "wealth_level": "average", "combat_behavior": "avoids_combat",
                "base_attack_name": "fists"
            }),
            "npc_conversation_greeting": "Well met, friend. What can I do for you?",
            "npc_conversation_continue": "Is that so? Interesting."
        }
        # Use a side_effect to provide different return values based on the prompt
        def ollama_side_effect(prompt):
            if "Generate a detailed personality" in prompt:
                return mock_responses["npc_personality"]
            elif "approaches Test Woodcutter" in prompt:
                return mock_responses["npc_conversation_greeting"]
            else:
                return mock_responses["npc_conversation_continue"]
        mock_call_ollama.side_effect = ollama_side_effect

        world = World()
        player = world.player

        # Manually create a Woodcutter NPC
        woodcutter_npc = NPC(x=1, y=1, name="Test Woodcutter", dialogue=[], personality="friendly", family_ties="", attitude_to_player="neutral")
        woodcutter_npc.profession = "Woodcutter"
        woodcutter_npc.factions = ["common_folk"] # Assign faction
        world.village_npcs.append(woodcutter_npc)

        # 1. Test Quest Offering - Not enough reputation
        player.reputation["common_folk"] = 0
        world.start_npc_dialogue(woodcutter_npc) # Initiate dialogue
        # In this state, the pending_quest_offer should NOT be set
        self.assertIsNone(world.pending_quest_offer)

        # 2. Test Quest Offering - Enough reputation
        player.reputation["common_folk"] = 15
        world.start_npc_dialogue(woodcutter_npc) # Re-initiate dialogue
        # Now the NPC should offer the quest
        self.assertIsNotNone(world.pending_quest_offer)

        # 3. Test Quest Acceptance
        # Dynamically get the offered quest ID
        quest_id = world.pending_quest_offer["quest_id"]
        quest_def = QUEST_DEFINITIONS[quest_id]

        # Simulate player accepting the quest
        world.player.active_quests[quest_id] = world.pending_quest_offer
        world.pending_quest_offer = None # Clear the offer

        self.assertIn(quest_id, player.active_quests)
        # Initialize progress for the test
        player.active_quests[quest_id] = quest_def.copy()
        player.active_quests[quest_id]["progress"] = 0


        # 4. Test Quest Completion
        # Add required items to player's inventory based on the quest definition
        if quest_def["type"] == "fetch":
            item_key = quest_def["item_to_fetch_key"]
            item_count = quest_def["item_fetch_count"]
            player.add_item(item_key, item_count)
        elif quest_def["type"] == "action":
            player.active_quests[quest_id]["progress"] = quest_def["action_count"]

        # Ensure the NPC has the correct role to complete the quest
        if "quest_giver_id_or_role" in quest_def:
            woodcutter_npc.profession = quest_def["quest_giver_id_or_role"]

        world.complete_quest(quest_id, woodcutter_npc)

        self.assertNotIn(quest_id, player.active_quests)
        self.assertIn(quest_id, player.completed_quests)

        # Verify rewards based on quest definition
        reward_rep = quest_def["reward_reputation"]["common_folk"]
        reward_money = quest_def.get("reward_money", 0)

        self.assertEqual(player.reputation["common_folk"], 15 + reward_rep)
        self.assertEqual(player.money, 100 + reward_money)
        if quest_def["type"] == "fetch":
            self.assertFalse(player.has_item(item_key))


if __name__ == '__main__':
    unittest.main()
