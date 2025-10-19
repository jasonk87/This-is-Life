# data/quests.py

QUEST_DEFINITIONS = {
    "kill_wolves_01": {
        "id": "kill_wolves_01", # Explicit ID for easier reference
        "title": "Wolf Extermination",
        "description": "Vicious wolves have been spotted near the village. We need someone to hunt them down before they attack livestock or travelers.",
        "type": "kill", # Quest type identifier
        "target_npc_name_prefix": "Dire Wolf", # NPCs like "Dire Wolf Alpha", "Dire Wolf Beta" would match
        "target_count": 3,
        "quest_giver_id_or_role": "Sheriff", # Role of the NPC who gives this quest
        "reward_money": 75,
        "reward_items": { # item_key: quantity
            "healing_salve": 2,
            "arrow": 10
        },
        "dialogue_offer": "Those blasted wolves are at it again, bolder than ever. I need a capable sort to thin their numbers. Take down three of those Dire Wolves, and I'll pay you 75 coins, plus a few supplies. Interested?",
        "dialogue_accept_player": ["Alright, I'll take care of those wolves.", "Consider it done, Sheriff.", "I'm on it."], # Example player accept lines
        "dialogue_accept_npc_response": "Good. Watch yourself out there. Come back when it's done.",
        "dialogue_reject_player": ["Maybe later.", "Not right now.", "I'm not interested."], # Example player reject lines
        "dialogue_reject_npc_response": "Suit yourself. The offer stands if you change your mind.",
        "dialogue_incomplete_report": "Still some of those beasts out there, from what I hear. You need to deal with {remaining_count} more.",
        "dialogue_complete_report": "You've done this village a great service! Those wolves won't be troubling us for a while. Here's your reward, as promised.",
        "completion_message_log": "Completed quest: Wolf Extermination. Received 75 money and items."
    },
    # Example of another quest type for future expansion
    "fetch_herbs_01": {
        "id": "fetch_herbs_01",
        "title": "Herbal Remedy",
        "description": "The village healer needs specific herbs for a remedy.",
        "type": "fetch",
        "item_to_fetch_key": "herb_generic", # Key from ITEM_DEFINITIONS
        "item_fetch_count": 5,
        "quest_giver_id_or_role": "Healer", # A potential future NPC role
        "reward_money": 30,
        "reward_items": {"cooked_meat_scrap": 1},
        "dialogue_offer": "I'm running low on Common Herbs for my poultices. Could you gather 5 for me? I can offer 30 coins and a bit of food for your trouble.",
        "dialogue_accept_player": ["I can get those for you.", "Sure, I'll find some herbs."],
        "dialogue_accept_npc_response": "Thank you kindly. Bring them back here when you have them.",
        "dialogue_reject_player": ["Sorry, I'm busy.", "I'm not much of an herb gatherer."],
        "dialogue_reject_npc_response": "A shame. Well, if you happen upon some...",
        "dialogue_incomplete_report": "Still need {remaining_count} more Common Herbs, dear.",
        "dialogue_complete_report": "Oh, wonderful! These are perfect. Here is your payment. Thank you again!",
        "completion_message_log": "Completed quest: Herbal Remedy. Received 30 money and items."
    },
    "law_enforcement_01": {
        "id": "law_enforcement_01",
        "title": "A Matter of Justice",
        "description": "A known bandit has been harassing travelers. The Sheriff wants them brought to justice.",
        "type": "kill",
        "target_npc_name_prefix": "Bandit Outlaw",
        "target_count": 1,
        "quest_giver_id_or_role": "Sheriff",
        "reward_money": 150,
        "reward_reputation": {
            "law_and_order": 20,
            "common_folk": 5
        },
        "required_faction": "law_and_order",
        "required_reputation": 20,
        "dialogue_offer": "We've had reports of a bandit causing trouble on the roads. I need someone I can trust to handle this quietly. Your reputation precedes you. Interested in 150 coins for the job?",
        "dialogue_accept_npc_response": "Excellent. Find this 'Bandit Outlaw' and dispense justice. Report back to me when it's done.",
        "dialogue_incomplete_report": "The bandit still roams free. My offer stands.",
        "dialogue_complete_report": "You've done the right thing. This town is safer because of you. Here is your reward.",
        "completion_message_log": "Completed quest: A Matter of Justice. Received 150 money and reputation."
    },
    "merchant_guild_01": {
        "id": "merchant_guild_01",
        "title": "Supply Chain Issues",
        "description": "A crucial shipment of goods has gone missing. The Merchants' Guild needs them recovered to fulfill an order.",
        "type": "fetch",
        "item_to_fetch_key": "valuable_goods",
        "item_fetch_count": 3,
        "quest_giver_id_or_role": "Merchant",
        "reward_money": 50,
        "reward_reputation": {
            "merchants_guild": 15
        },
        "required_faction": "merchants_guild",
        "required_reputation": 15,
        "dialogue_offer": "A reliable associate like you is just who I need. A shipment of 3 crates of valuable goods was lost. Recover them, and I'll make it worth your while with 50 coins and the Guild's gratitude.",
        "dialogue_accept_npc_response": "I knew I could count on you. The sooner you find those goods, the better.",
        "dialogue_incomplete_report": "Any luck finding those crates? I still need {remaining_count} more.",
        "dialogue_complete_report": "Perfect! You've saved me a lot of trouble. Here is your payment. The Guild will hear of your good work.",
        "completion_message_log": "Completed quest: Supply Chain Issues. Received 50 money and reputation."
    },
    "common_folk_01": {
        "id": "common_folk_01",
        "title": "Community Planting",
        "description": "The community is organizing a planting effort to ensure a good harvest. They need volunteers to plant saplings.",
        "type": "action",
        "action_type": "plant_sapling",
        "action_count": 5,
        "quest_giver_id_or_role": "Farmer",
        "reward_items": {
            "bread": 5
        },
        "reward_reputation": {
            "common_folk": 10
        },
        "required_faction": "common_folk",
        "required_reputation": 10,
        "dialogue_offer": "We're trying to get some more trees growing around here for the future. You look like you have a green thumb. If you can plant 5 saplings, I'd be happy to share some of my fresh-baked bread with you.",
        "dialogue_accept_npc_response": "Wonderful! Every tree helps. Let me know when you're done.",
        "dialogue_incomplete_report": "It's a good start, but we still need {remaining_count} more saplings in the ground.",
        "dialogue_complete_report": "Thank you for your help! The whole village appreciates it. Here is that bread I promised you.",
        "completion_message_log": "Completed quest: Community Planting. Received bread and reputation."
    }
}
