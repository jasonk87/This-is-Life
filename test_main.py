
import unittest
from unittest.mock import patch, MagicMock
from engine import World, Chunk, Village, NPC, Building
from data.quests import QUEST_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.tiles import TILE_DEFINITIONS
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
        merchant_npc = NPC(x=0, y=0, name="Test Merchant", dialogue=[], personality="greedy", family_ties="", attitude_to_player="neutral", village=village)
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
        village = Village()

        # Manually create a Woodcutter NPC
        woodcutter_npc = NPC(x=1, y=1, name="Test Woodcutter", dialogue=[], personality="friendly", family_ties="", attitude_to_player="neutral", village=village)
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


    @patch('engine.World._call_ollama')
    def test_cooking_system(self, mock_call_ollama):
        # Setup
        mock_call_ollama.return_value = json.dumps({"name": "test", "personality": "test"})
        world = World()
        player = world.player

        # Add a fire pit (cooking station)
        station_x, station_y = player.x + 1, player.y
        world._change_map_tile((station_x, station_y), DECORATION_ITEM_DEFINITIONS["fire_pit_simple"])

        # 1. Test successful cooking
        player.add_item("raw_meat", 1)
        world.cook_item("cooked_meat")

        self.assertTrue(player.has_item("cooked_meat"))
        self.assertFalse(player.has_item("raw_meat"))

        # 2. Test cooking failure (no station)
        player.add_item("raw_meat", 1)
        # Move player away from fire
        player.x += 5
        world.cook_item("cooked_meat")
        # Assert nothing changed
        self.assertTrue(player.has_item("raw_meat", 1))


    @patch('engine.World._call_ollama')
    def test_crafting_system(self, mock_call_ollama):
        # Setup
        mock_call_ollama.return_value = json.dumps({"name": "test", "personality": "test"})
        world = World()
        player = world.player

        # Add an anvil (crafting station)
        station_x, station_y = player.x + 1, player.y
        world._change_map_tile((station_x, station_y), DECORATION_ITEM_DEFINITIONS["anvil"])

        # 1. Test successful crafting
        player.add_item("iron_ingot", 2)
        player.add_item("raw_log", 1)
        world.craft_item("iron_sword")

        self.assertTrue(player.has_item("iron_sword"))
        self.assertFalse(player.has_item("iron_ingot"))
        self.assertFalse(player.has_item("raw_log"))

        # 2. Test crafting failure (no station)
        player.add_item("iron_ingot", 2)
        player.add_item("raw_log", 1)
        player.x += 5 # Move away
        world.craft_item("iron_sword")
        self.assertFalse(player.has_item("iron_sword", 2))
        self.assertTrue(player.has_item("iron_ingot", 2))


    @patch('random.choices')
    @patch('engine.World._call_ollama')
    def test_weather_system(self, mock_call_ollama, mock_random_choices):
        # Setup
        mock_call_ollama.return_value = json.dumps({"name": "test", "personality": "test"})
        # Force the weather to transition to "rain"
        mock_random_choices.return_value = ["rain"]

        world = World()
        self.assertEqual(world.current_weather, "clear")

        # Force a weather update
        world.weather_timer = world.weather_duration
        world._update_weather()

        self.assertEqual(world.current_weather, "rain")
        self.assertIn("The weather changes to Rain.", world.chat_log[-1])

    @patch('engine.World._call_ollama')
    def test_building_system(self, mock_call_ollama):
        # Setup
        mock_call_ollama.return_value = json.dumps({"name": "test", "personality": "test"})
        world = World()
        player = world.player

        # 1. Player crafts building kits
        player.add_item("stone_chunk", 5)
        player.add_item("wooden_plank", 4)
        world.craft_item("stone_foundation_kit")
        world.craft_item("wood_wall_kit")
        self.assertTrue(player.has_item("stone_foundation_kit"))
        self.assertTrue(player.has_item("wood_wall_kit"))

        # 2. Player enters build mode and places foundation
        world.toggle_build_mode()
        self.assertTrue(world.build_mode_active)

        # Clear the area for building to avoid procedural generation interference
        build_x, build_y = player.x + 1, player.y
        world._change_map_tile((build_x, build_y), TILE_DEFINITIONS["plains"])

        world.player_attempt_place_buildable(build_x, build_y)
        self.assertEqual(world.get_tile_at(build_x, build_y).name, "Stone Foundation")

        # 3. Player places wall on foundation
        world.cycle_build_mode_item() # Select wood wall kit
        world.player_attempt_place_buildable(player.x + 1, player.y)
        self.assertEqual(world.get_tile_at(player.x + 1, player.y).name, "Wood Wall")
        world.toggle_build_mode()

        # Reset world state for a clean NPC test
        world.chunks = [[Chunk("plains", poi_type=None) for _ in range(world.chunk_width)] for _ in range(world.chunk_height)]
        world.village_npcs = []
        world.construction_sites = []
        world.buildings_by_id = {}


        # 4. NPC Builder is assigned to a construction site
        village = Village()
        world.chunks[0][0].village = village # Create a village for the test

        # Create a dummy building for the builder to live in, to associate them with the village
        builder_house = Building(1,1,1,1)
        village.add_building(builder_house)
        world.buildings_by_id[builder_house.id] = builder_house

        homeless_npc = NPC(x=1, y=1, name="Homeless", dialogue=[], personality="sad", family_ties="", attitude_to_player="neutral", village=village)
        builder_npc = NPC(x=2, y=2, name="Builder Bob", dialogue=[], personality="diligent", family_ties="", attitude_to_player="neutral", village=village)
        builder_npc.profession = "Builder"
        builder_npc.home_building_id = builder_house.id # Associate builder with village
        world.village_npcs.extend([homeless_npc, builder_npc])

        world.game_time = 500
        world._update_village_construction()
        self.assertEqual(len(world.construction_sites), 1)
        site = world.construction_sites[0]
        self.assertEqual(site.assigned_builder_id, builder_npc.id)

        # 5. Builder gathers resources (simplified)
        world._handle_npc_work_sub_tasks(builder_npc) # This should trigger fetching stone
        builder_npc.x, builder_npc.y = site.x, site.y # Teleport to site for testing
        builder_npc.add_item("stone_chunk", 1)
        world._handle_npc_work_sub_tasks(builder_npc) # This should trigger laying foundation

        # 6. A homeless NPC moves into the newly constructed house
        # Manually complete the building for the test
        for i in range(site.width * site.height):
             world._change_map_tile((site.x + i % site.width, site.y + i // site.width), TILE_DEFINITIONS["stone_foundation"])

        # Manually build the perimeter walls
        for y_offset in range(site.height):
            for x_offset in range(site.width):
                if x_offset == 0 or x_offset == site.width - 1 or y_offset == 0 or y_offset == site.height - 1:
                    world._change_map_tile((site.x + x_offset, site.y + y_offset), TILE_DEFINITIONS["wood_wall"])

        # Manually place a door
        door_x, door_y = site.x + site.width // 2, site.y + site.height - 1
        world._change_map_tile((door_x, door_y), DECORATION_ITEM_DEFINITIONS["wooden_door_closed"])

        world.game_time += 500
        world._check_for_completed_construction()
        self.assertEqual(len(world.construction_sites), 0)
        self.assertIsNotNone(homeless_npc.home_building_id)


if __name__ == '__main__':
    unittest.main()
