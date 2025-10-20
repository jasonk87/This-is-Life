
import unittest
from unittest.mock import patch
from engine import World
import json

class TestGame(unittest.TestCase):
    @patch('engine.World._call_ollama')
    def test_world_initialization(self, mock_call_ollama):
        # Canned response for NPC generation
        mock_npc_data = {
            "name": "Test NPC",
            "personality": "test",
            "family_ties": "none",
            "attitude_to_player": "neutral",
            "dialogue": ["Hello."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists"
        }
        mock_call_ollama.return_value = json.dumps(mock_npc_data)

        try:
            world = World()
            self.assertIsNotNone(world)
            self.assertIsNotNone(world.player)
        except Exception as e:
            self.fail(f"World initialization failed with an exception: {e}")

    @patch('engine.World._call_ollama')
    def test_crafting_menu(self, mock_call_ollama):
        # Canned response for NPC generation
        mock_npc_data = {
            "name": "Test NPC",
            "personality": "test",
            "family_ties": "none",
            "attitude_to_player": "neutral",
            "dialogue": ["Hello."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists"
        }
        mock_call_ollama.return_value = json.dumps(mock_npc_data)

        world = World()
        world.player.add_item("raw_log", 10)
        world.player.add_item("stone_chunk", 10)

        world.populate_craftable_recipes()

        self.assertGreater(len(world.crafting_menu_context["craftable_recipes"]), 0)

        world.craft_item("crude_spear")

        self.assertTrue(world.player.has_item("crude_spear"))

    @patch('engine.World._call_ollama')
    def test_trade_menu(self, mock_call_ollama):
        # Canned response for NPC generation
        mock_npc_data = {
            "name": "Test Merchant",
            "personality": "test",
            "family_ties": "none",
            "attitude_to_player": "neutral",
            "dialogue": ["Hello."],
            "wealth_level": "average",
            "combat_behavior": "defensive",
            "base_attack_name": "fists"
        }
        mock_call_ollama.return_value = json.dumps(mock_npc_data)

        world = World()
        # Manually create and add an NPC, since world init doesn't guarantee one
        from entities.base import NPC
        merchant = NPC(x=world.player.x + 1, y=world.player.y, name="Test Merchant", dialogue=["Buy something!"])
        merchant.profession = "Merchant"
        merchant.money = 200 # Give merchant money to buy things
        world.village_npcs.append(merchant) # Add to a list the game will check

        world.player.add_item("raw_log", 10)

        world.initialize_trade_session(merchant)

        self.assertGreater(len(world.trade_ui_context["player_inventory_snapshot"]), 0)

        world.trade_ui_context["active_panel"] = "PLAYER"
        world.handle_trade_action()

        # Player starts with 100, sells a log (value 2, but dynamic price might vary)
        # For a simple test, we'll just check that money is greater than initial
        self.assertGreater(world.player.money, 100)
        self.assertTrue(world.player.has_item("raw_log", 9))

if __name__ == '__main__':
    unittest.main()
