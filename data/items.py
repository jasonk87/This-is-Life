# data/items.py
import tcod

# --- Item Definitions ---
ITEM_DEFINITIONS = {
    # --- Resources ---
    "raw_log": {
        "name": "Raw Log",
        "description": "A rough, unprocessed log directly from a felled tree.",
        "char": "l",
        "color": tcod.constants.SADDLEBROWN,
        "value": 2,
        "weight": 5,
        "stackable": True,
        "item_type_tags": ["resource"], # Standardized key
    },
    "stone_chunk": {
        "name": "Stone Chunk",
        "description": "A rough piece of stone, useful for basic construction.",
        "char": "s",
        "color": tcod.constants.GREY,
        "value": 1,
        "weight": 8,
        "stackable": True,
        "type": ["resource"],
    },
    "herb_generic": {
        "name": "Common Herb",
        "description": "A common herb, often used in simple remedies.",
        "char": "*",
        "color": tcod.constants.FOREST,
        "value": 3, # Increased value
        "weight": 0.1,
        "stackable": True,
        "type": ["resource", "reagent"],
    },
    "wheat": {
        "name": "Wheat",
        "description": "Grains of wheat, can be milled into flour or used as animal feed.",
        "char": "w",
        "color": tcod.constants.GOLD,
        "value": 2,
        "weight": 0.5,
        "stackable": True,
        "type": ["resource", "food_ingredient"],
    },
    "iron_ore": {
        "name": "Iron Ore",
        "description": "A chunk of rock containing iron.",
        "char": "o", # 'o' for ore
        "color": tcod.constants.DARK_ORANGE, # A rusty color
        "value": 4,
        "weight": 10,
        "stackable": True,
        "type": ["resource"],
    },

    # --- Crafted Components ---
    "wooden_plank": {
        "name": "Wooden Plank",
        "description": "A processed wooden plank, ready for construction.",
        "char": "p",
        "color": tcod.constants.TAN,
        "value": 5, # Value added by crafting
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["component"], # Standardized key
        "crafting_recipe": {
            "raw_log": 1 # Changed from log to raw_log
        },
    },
    "lumber_processed": {
        "name": "Processed Lumber",
        "description": "Smooth, processed lumber, ready for fine construction.",
        "char": "=",
        "color": tcod.constants.BURlywood, # Corrected typo from plan
        "value": 8,
        "weight": 3,
        "stackable": True,
        "item_type_tags": ["resource", "component"],
    },
    "wheat_seeds": {
        "name": "Wheat Seeds",
        "description": "Seeds for growing wheat.",
        "char": "\"", # Using quote for seeds, like tiny grains
        "color": tcod.constants.KHAKI,
        "value": 1,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["resource", "seed"],
    },

    # --- Tools ---
    "axe_stone": {
        "name": "Stone Axe",
        "description": "A crudely made axe with a stone head. Good for chopping wood.",
        "char": "/",
        "color": tcod.constants.DARKSLATEGRAY,
        "value": 25, # Tools are more valuable
        "weight": 7,
        "stackable": False,
        "type": ["tool", "weapon_melee_axe"], # This will be standardized later
        "properties": {
            "tool_type": "axe",
            "chop_power": 1
        },
        "crafting_recipe": {
            "stone_chunk": 2,
            "raw_log": 1 # Changed from log to raw_log
        },
    },
    "lockpick": {
        "name": "Lockpick",
        "description": "A thin piece of metal used for picking locks. Fragile.",
        "char": "~",
        "color": tcod.constants.SILVER,
        "value": 5,
        "weight": 0.1,
        "stackable": True, # Lockpicks often come in sets or are stackable
        "type": ["tool"],
        "properties": {
            "tool_type": "lockpick",
            "breaks_on_fail_chance": 0.25 # 25% chance to break on a failed lockpicking attempt
        }
    },

    # --- Existing Items ---
    "healing_salve": {
        "name": "Healing Salve",
        "description": "A simple paste that heals minor wounds.",
        "char": "!", # Example char, can be anything not used
        "color": tcod.constants.LIGHT_GREEN,
        "value": 15,
        "weight": 0.5,
        "stackable": True,
        "type": ["consumable"],
        "crafting_recipe": {
            "herb_generic": 3 # Changed from "flower" to "herb_generic"
        },
        "on_use": {
            "heal_amount": 10
        }
    },
    # "flower" item itself is removed, as it's now "herb_generic"
    # If player picks a flower tile, they get "herb_generic" item.

    # --- Light Sources ---
    "unlit_torch": {
        "name": "Unlit Torch",
        "description": "A stick with oil-soaked rags, needs to be lit.",
        "char": "\\", # Backslash for torch
        "color": tcod.constants.DARK_AMBER,
        "value": 3,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["tool", "light_source_potential"], # Standardized key
        "crafting_recipe": {"raw_log": 1, "herb_generic": 1}, # Changed log to raw_log
        "on_use_effect": "light_torch" # Custom effect string
    },
    "torch_lit": { # This item might not be directly in inventory, but represents the state
        "name": "Lit Torch",
        "description": "A burning torch, casting a flickering light.",
        "char": "\\",
        "color": tcod.constants.FLAME,
        "value": 3, # Same value as unlit
        "weight": 1,
        "stackable": False, # Only one lit torch "active" usually
        "type": ["tool", "light_source_active"],
        "properties": {
            "emits_light": True,
            "light_radius": 10,
            "duration_ticks": 600, # e.g., 600 ticks (1/2.5 of a short day, or 1/5 of a longer day)
            "on_extinguish_becomes": "unlit_torch", # Optional: if it can be re-lit or partially used
            "on_burnout_becomes": "burnt_out_torch"
        },
        "on_use_effect": "extinguish_torch" # Using it again extinguishes it
    },
    "burnt_out_torch": {
        "name": "Burnt Out Torch",
        "description": "The charred remains of a torch. Useless.",
        "char": "~", # Different char
        "color": tcod.constants.DARKEST_GREY,
        "value": 0,
        "weight": 0.5,
        "stackable": True,
        "type": ["trash"] # Changed from list to single string for consistency with others
    },

    # --- Weapons ---
    "rusty_sword": {
        "name": "Rusty Sword",
        "description": "A worn, but still somewhat sharp sword.",
        "char": "|",
        "color": tcod.constants.SILVER,
        "value": 30,
        "weight": 4,
        "stackable": False,
        "item_type_tags": ["weapon", "melee", "sword"],
        "equip_slot": "main_hand",
        "properties": {
            "damage_dice": "1d6",
            "damage_bonus": 0,
            "attack_range": 1
        }
    },
    "short_bow": {
        "name": "Short Bow",
        "description": "A simple wooden short bow.",
        "char": ")",
        "color": tcod.constants.DARK_SEPIA,
        "value": 25,
        "weight": 2,
        "stackable": False,
        "item_type_tags": ["weapon", "ranged", "bow"],
        "equip_slot": "main_hand", # Or "ranged_weapon" slot if we add more
        "properties": {
            "damage_dice": "1d6",
            "damage_bonus": 0,
            "attack_range": 12,
            "requires_ammo": "arrow" # Placeholder for future ammo system
        }
    },
    # Ammunition example (not fully used yet)
    "arrow": {
        "name": "Arrow",
        "description": "A standard arrow for a bow.",
        "char": "-",
        "color": tcod.constants.LIGHT_SEPIA,
        "value": 1,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["ammunition", "arrow"]
    },

    # --- Armor ---
    "leather_jerkin": {
        "name": "Leather Jerkin",
        "description": "A tough leather vest offering basic protection.",
        "char": "[",
        "color": tcod.constants.DARK_AMBER,
        "value": 40,
        "weight": 5,
        "stackable": False,
        "item_type_tags": ["armor", "body"],
        "equip_slot": "body_armor",
        "properties": {
            "defense_bonus": 1
        }
    },
    "iron_helmet": {
        "name": "Iron Helmet",
        "description": "A sturdy iron helmet.",
        "char": "^", # Using existing mountain char, might need unique
        "color": tcod.constants.DARK_SLATE_GREY,
        "value": 35,
        "weight": 3,
        "stackable": False,
        "item_type_tags": ["armor", "head"],
        "equip_slot": "head_armor",
        "properties": {
            "defense_bonus": 1
        }
    }
}

# Update existing Stone Axe to conform to new weapon properties
if "axe_stone" in ITEM_DEFINITIONS:
    ITEM_DEFINITIONS["axe_stone"]["item_type_tags"] = ITEM_DEFINITIONS["axe_stone"].get("item_type_tags", [])
    if "weapon" not in ITEM_DEFINITIONS["axe_stone"]["item_type_tags"]:
        ITEM_DEFINITIONS["axe_stone"]["item_type_tags"].append("weapon")
    if "melee" not in ITEM_DEFINITIONS["axe_stone"]["item_type_tags"]:
        ITEM_DEFINITIONS["axe_stone"]["item_type_tags"].append("melee")
    if "axe" not in ITEM_DEFINITIONS["axe_stone"]["item_type_tags"]:
        ITEM_DEFINITIONS["axe_stone"]["item_type_tags"].append("axe")

    ITEM_DEFINITIONS["axe_stone"]["equip_slot"] = "main_hand"

    if "properties" not in ITEM_DEFINITIONS["axe_stone"]:
        ITEM_DEFINITIONS["axe_stone"]["properties"] = {}

    ITEM_DEFINITIONS["axe_stone"]["properties"]["damage_dice"] = ITEM_DEFINITIONS["axe_stone"]["properties"].get("damage_dice", "1d4") # Default if not set
    ITEM_DEFINITIONS["axe_stone"]["properties"]["damage_bonus"] = ITEM_DEFINITIONS["axe_stone"]["properties"].get("damage_bonus", 0)
    ITEM_DEFINITIONS["axe_stone"]["properties"]["attack_range"] = ITEM_DEFINITIONS["axe_stone"]["properties"].get("attack_range", 1)
    # Keep existing tool_type and chop_power
    ITEM_DEFINITIONS["axe_stone"]["properties"]["tool_type"] = "axe"
    ITEM_DEFINITIONS["axe_stone"]["properties"]["chop_power"] = ITEM_DEFINITIONS["axe_stone"]["properties"].get("chop_power",1)


# Standardize 'type' to 'item_type_tags' for older items for consistency, if they don't have it
for item_key, item_data in ITEM_DEFINITIONS.items():
    if "type" in item_data and "item_type_tags" not in item_data:
        if isinstance(item_data["type"], list):
            item_data["item_type_tags"] = item_data["type"]
        else: # If it's a single string
            item_data["item_type_tags"] = [item_data["type"]]
        # del item_data["type"] # Optionally remove old 'type' key after migration
    elif "item_type_tags" not in item_data: # Ensure all items have the key, even if empty
        item_data["item_type_tags"] = []
