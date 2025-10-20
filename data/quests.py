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
    }
}
