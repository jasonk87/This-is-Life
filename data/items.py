# data/items.py
from data.tiles import COLORS

# --- Item Definitions ---
ITEM_DEFINITIONS = {
    # --- Resources ---
    "raw_log": {
        "name": "Raw Log",
        "description": "A rough, unprocessed log directly from a felled tree.",
        "char": "l",
        "color": COLORS["saddlebrown"],
        "value": 2,
        "weight": 5,
        "stackable": True,
        "item_type_tags": ["resource"],
    },
    "stone_chunk": {
        "name": "Stone Chunk",
        "description": "A rough piece of stone, useful for basic construction.",
        "char": "s",
        "color": COLORS["grey"],
        "value": 1,
        "weight": 8,
        "stackable": True,
        "item_type_tags": ["resource"],
    },
    "herb_generic": {
        "name": "Common Herb",
        "description": "A common herb, often used in simple remedies.",
        "char": "*",
        "color": COLORS["forest_fg"],
        "value": 3,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["resource", "reagent"],
    },
    "wheat": {
        "name": "Wheat",
        "description": "Grains of wheat, can be milled into flour or used as animal feed.",
        "char": "w",
        "color": COLORS["khaki"],
        "value": 2,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient"],
    },
    "flour": {
        "name": "Flour",
        "description": "Fine powder ground from grain, used for baking.",
        "char": "f",
        "color": (255, 255, 255),
        "value": 4,
        "weight": 0.4,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient"],
    },
    "bread": {
        "name": "Bread",
        "description": "A loaf of bread.",
        "char": "b",
        "color": COLORS["yellow_green"],
        "value": 8,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "on_use": {
            "reduces_hunger": 50
        }
    },
    "iron_ore": {
        "name": "Iron Ore",
        "description": "A chunk of rock containing iron.",
        "char": "o",
        "color": COLORS["dark_orange"],
        "value": 4,
        "weight": 10,
        "stackable": True,
        "item_type_tags": ["resource"],
    },
    "iron_ingot": {
        "name": "Iron Ingot",
        "description": "A bar of refined iron, ready for smithing.",
        "char": "=",
        "color": COLORS["silver"],
        "value": 15,
        "weight": 8,
        "stackable": True,
        "item_type_tags": ["component", "metal"],
    },
    "coal": {
        "name": "Coal",
        "description": "A combustible black rock, used as fuel.",
        "char": "c",
        "color": COLORS["darkest_grey"],
        "value": 3,
        "weight": 4,
        "stackable": True,
        "item_type_tags": ["resource", "fuel"],
    },

    # --- Crafted Components ---
    "wooden_plank": {
        "name": "Wooden Plank",
        "description": "A processed wooden plank, ready for construction.",
        "char": "p",
        "color": COLORS["tan"],
        "value": 5,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["component"],
        "crafting_recipe": {
            "raw_log": 1
        },
    },
    "lumber_processed": {
        "name": "Processed Lumber",
        "description": "Smooth, processed lumber, ready for fine construction.",
        "char": "=",
        "color": COLORS["burlywood"],
        "value": 8,
        "weight": 3,
        "stackable": True,
        "item_type_tags": ["resource", "component"],
    },
    "wheat_seeds": {
        "name": "Wheat Seeds",
        "description": "Seeds for growing wheat.",
        "char": "\"",
        "color": COLORS["khaki"],
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
        "color": COLORS["dark_slate_gray"],
        "value": 25,
        "weight": 7,
        "stackable": False,
        "item_type_tags": ["tool", "weapon", "melee", "axe"],
        "equip_slot": "main_hand",
        "properties": {
            "tool_type": "axe",
            "chop_power": 1,
            "max_durability": 25,
            "damage_dice": "1d4",
            "damage_bonus": 0,
            "attack_range": 1
        },
        "crafting_recipe": {
            "stone_chunk": 2,
            "raw_log": 1
        },
    },
    "broken_tool_handle": {
        "name": "Broken Tool Handle",
        "description": "The snapped wooden handle of a tool. Might be reusable.",
        "char": "_",
        "color": COLORS["dark_sepia"],
        "value": 1,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "component"]
    },
    "lockpick": {
        "name": "Lockpick",
        "description": "A thin piece of metal used for picking locks. Fragile.",
        "char": "~",
        "color": COLORS["silver"],
        "value": 5,
        "weight": 0.1,
        "stackable": False,
        "item_type_tags": ["tool"],
        "properties": {
            "tool_type": "lockpick",
            "max_durability": 5
        }
    },

    # --- Consumables ---
    "healing_salve": {
        "name": "Healing Salve",
        "description": "A simple paste that heals minor wounds.",
        "char": "!",
        "color": COLORS["light_green"],
        "value": 15,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["consumable", "healing"],
        "crafting_recipe": {
            "herb_generic": 3
        },
        "on_use": {
            "heal_amount": 10
        }
    },
    "unlit_torch": {
        "name": "Unlit Torch",
        "description": "A stick with oil-soaked rags, needs to be lit.",
        "char": "\\",
        "color": COLORS["dark_amber"],
        "value": 3,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["tool", "light_source_potential"],
        "crafting_recipe": {"raw_log": 1, "herb_generic": 1},
        "on_use_effect": "light_torch"
    },
    "torch_lit": {
        "name": "Lit Torch",
        "description": "A burning torch, casting a flickering light.",
        "char": "\\",
        "color": COLORS["flame"],
        "value": 3,
        "weight": 1,
        "stackable": False,
        "item_type_tags": ["tool", "light_source_active"],
        "properties": {
            "emits_light": True,
            "light_radius": 10,
            "duration_ticks": 600,
            "on_extinguish_becomes": "unlit_torch",
            "on_burnout_becomes": "burnt_out_torch",
            "max_durability": 600 # Duration can be its durability
        },
        "on_use_effect": "extinguish_torch"
    },
    "burnt_out_torch": {
        "name": "Burnt Out Torch",
        "description": "The charred remains of a torch. Useless.",
        "char": "~",
        "color": COLORS["darkest_grey"],
        "value": 0,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["trash"]
    },
    "cooked_meat_scrap": {
        "name": "Cooked Meat Scrap",
        "description": "A cooked piece of meat. Edible.",
        "char": "m",
        "color": COLORS["dark_orange"],
        "value": 4,
        "weight": 0.4,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "crafting_recipe": {
            "raw_meat_scrap": 1
        },
        "on_use": {
            "reduces_hunger": 35
        }
    },
    "water_flask": {
        "name": "Water Flask",
        "description": "A simple flask filled with water. Refreshing.",
        "char": "~",
        "color": COLORS["light_blue"],
        "value": 5,
        "weight": 1,
        "stackable": False,
        "item_type_tags": ["consumable", "drink"],
        "properties": {
             "max_durability": 3 # Represents 3 sips/uses
        },
        "on_use": { # Effect per sip
            "reduces_thirst": 40
        }
    },
    "apple": {
        "name": "Apple",
        "description": "A crisp, juicy apple.",
        "char": "a",
        "color": COLORS["red"],
        "value": 3,
        "weight": 0.3,
        "stackable": True,
        "item_type_tags": ["consumable", "food", "fruit"],
        "on_use": {
            "reduces_hunger": 10,
            "reduces_thirst": 5
        }
    },
    "pear": {
        "name": "Pear",
        "description": "A sweet and soft pear.",
        "char": "p",
        "color": COLORS["yellow_green"],
        "value": 3,
        "weight": 0.3,
        "stackable": True,
        "item_type_tags": ["consumable", "food", "fruit"],
        "on_use": {
            "reduces_hunger": 10,
            "reduces_thirst": 7
        }
    },
    "acorn": {
        "name": "Acorn",
        "description": "The nut of an oak tree. Edible in a pinch.",
        "char": ".",
        "color": COLORS["dark_orange"],
        "value": 1,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["consumable", "food", "nut"],
        "on_use": {
            "reduces_hunger": 3
        }
    },
    "sapling": {
        "name": "Sapling",
        "description": "A young tree, ready for planting.",
        "char": "y",
        "color": COLORS["yellow_green"],
        "value": 5,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "reforestation"],
    },
     "raw_meat_scrap": { # Already defined, ensure it's here for completeness of food section
        "name": "Raw Meat Scrap",
        "description": "A piece of raw meat. Needs cooking.",
        "char": "m",
        "color": COLORS["crimson"],
        "value": 1,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"]
    },


    # --- Weapons ---
    "rusty_sword": {
        "name": "Rusty Sword",
        "description": "A worn, but still somewhat sharp sword.",
        "char": "|",
        "color": COLORS["silver"],
        "value": 30,
        "weight": 4,
        "stackable": False,
        "item_type_tags": ["weapon", "melee", "sword"],
        "equip_slot": "main_hand",
        "properties": {
            "damage_dice": "1d6",
            "damage_bonus": 0,
            "attack_range": 1,
            "max_durability": 40
        }
    },
    "crude_spear": {
        "name": "Crude Spear",
        "description": "A sharpened log, barely a spear. Better than fists.",
        "char": "/",
        "color": COLORS["dark_sepia"],
        "value": 15,
        "weight": 4,
        "stackable": False,
        "item_type_tags": ["weapon", "melee", "spear"],
        "equip_slot": "main_hand",
        "properties": {
            "damage_dice": "1d6",
            "damage_bonus": 0,
            "attack_range": 2,
            "max_durability": 20
        },
        "crafting_recipe": {
            "raw_log": 2,
            "stone_chunk": 1
        }
    },
    "short_bow": {
        "name": "Short Bow",
        "description": "A simple wooden short bow.",
        "char": ")",
        "color": COLORS["dark_sepia"],
        "value": 25,
        "weight": 2,
        "stackable": False,
        "item_type_tags": ["weapon", "ranged", "bow"],
        "equip_slot": "main_hand",
        "properties": {
            "damage_dice": "1d6",
            "damage_bonus": 0,
            "attack_range": 12,
            "requires_ammo": "arrow",
            "max_durability": 30
        }
    },
    "arrow": {
        "name": "Arrow",
        "description": "A standard arrow for a bow.",
        "char": "-",
        "color": COLORS["light_sepia"],
        "value": 1,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["ammunition", "arrow"]
    },

    # --- Armor ---
    "wooden_shield": {
        "name": "Wooden Shield",
        "description": "A simple shield made of wooden planks.",
        "char": "[",
        "color": COLORS["burlywood"],
        "value": 30,
        "weight": 6,
        "stackable": False,
        "item_type_tags": ["armor", "shield"],
        "equip_slot": "off_hand",
        "properties": {
            "defense_bonus": 1,
            "max_durability": 50
        },
        "crafting_recipe": {
            "wooden_plank": 4
        }
    },
    "leather_jerkin": {
        "name": "Leather Jerkin",
        "description": "A tough leather vest offering basic protection.",
        "char": "[",
        "color": COLORS["dark_amber"],
        "value": 40,
        "weight": 5,
        "stackable": False,
        "item_type_tags": ["armor", "body"],
        "equip_slot": "body_armor",
        "properties": {
            "defense_bonus": 1,
            "max_durability": 60
        }
    },
    "iron_helmet": {
        "name": "Iron Helmet",
        "description": "A sturdy iron helmet.",
        "char": "^",
        "color": COLORS["dark_slate_gray"],
        "value": 35,
        "weight": 3,
        "stackable": False,
        "item_type_tags": ["armor", "head"],
        "equip_slot": "head_armor",
        "properties": {
            "defense_bonus": 1,
            "max_durability": 70
        },
        "crafting_recipe": {
            "iron_ingot": 3
        }
    },
    "stone_pickaxe": {
        "name": "Stone Pickaxe",
        "description": "A crude pickaxe for mining.",
        "char": "p",
        "color": COLORS["dark_slate_gray"],
        "value": 30,
        "weight": 8,
        "stackable": False,
        "item_type_tags": ["tool", "weapon", "melee", "pickaxe"],
        "equip_slot": "main_hand",
        "properties": {
            "tool_type": "pickaxe",
            "mine_power": 1,
            "max_durability": 25,
            "damage_dice": "1d4",
        },
        "crafting_recipe": {
            "stone_chunk": 3,
            "raw_log": 2
        },
    },
    "iron_sword": {
        "name": "Iron Sword",
        "description": "A simple but effective iron sword.",
        "char": "|",
        "color": COLORS["silver"],
        "value": 50,
        "weight": 5,
        "stackable": False,
        "item_type_tags": ["weapon", "melee", "sword"],
        "equip_slot": "main_hand",
        "properties": {
            "damage_dice": "1d8",
            "max_durability": 60
        },
        "crafting_recipe": {
            "iron_ingot": 2,
            "raw_log": 1
        },
    },
    "iron_breastplate": {
        "name": "Iron Breastplate",
        "description": "A sturdy breastplate made of iron.",
        "char": "[",
        "color": COLORS["silver"],
        "value": 80,
        "weight": 15,
        "stackable": False,
        "item_type_tags": ["armor", "body"],
        "equip_slot": "body_armor",
        "properties": {
            "defense_bonus": 2,
            "max_durability": 100
        },
        "crafting_recipe": {
            "iron_ingot": 5,
        },
    },
    "fish": {
        "name": "Fish",
        "description": "A freshly caught fish.",
        "char": "f",
        "color": COLORS["silver"],
        "value": 5,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "on_use": {
            "reduces_hunger": 20
        }
    }
}

# Standardize 'type' to 'item_type_tags' and ensure all items have item_type_tags
for item_key, item_data in ITEM_DEFINITIONS.items():
    if "type" in item_data and "item_type_tags" not in item_data:
        if isinstance(item_data["type"], list):
            item_data["item_type_tags"] = list(item_data["type"]) # Ensure it's a list copy
        else:
            item_data["item_type_tags"] = [str(item_data["type"])]
        # del item_data["type"] # Optionally remove old 'type' key
    elif "item_type_tags" not in item_data:
        item_data["item_type_tags"] = []

    # Ensure stackable is defined, default to False for non-consumables/resources if not set
    if "stackable" not in item_data:
        if any(tag in item_data.get("item_type_tags", []) for tag in ["resource", "consumable", "reagent", "ammunition", "food_ingredient", "seed", "trash"]):
            item_data["stackable"] = True
        else:
            item_data["stackable"] = False

    # For non-stackable items that should have durability, ensure properties and max_durability exist
    if not item_data["stackable"] and any(tag in item_data.get("item_type_tags", []) for tag in ["tool", "weapon", "armor", "shield"]):
        if "properties" not in item_data:
            item_data["properties"] = {}
        if "max_durability" not in item_data["properties"]:
            # Add a default max_durability if missing for durable types
            if "tool" in item_data["item_type_tags"]:
                item_data["properties"]["max_durability"] = 20
            elif "weapon" in item_data["item_type_tags"]:
                item_data["properties"]["max_durability"] = 50
            elif "armor" in item_data["item_type_tags"] or "shield" in item_data["item_type_tags"]:
                item_data["properties"]["max_durability"] = 80
            else:
                item_data["properties"]["max_durability"] = 10 # Generic fallback for other non-stackable

# Ensure axe_stone specific properties are correctly merged (already done by direct edit)
axe_stone_def = ITEM_DEFINITIONS.get("axe_stone")
if axe_stone_def:
    axe_stone_def["stackable"] = False # Explicit
    if "properties" not in axe_stone_def: axe_stone_def["properties"] = {}
    axe_stone_def["properties"]["tool_type"] = "axe"
    axe_stone_def["properties"]["chop_power"] = axe_stone_def["properties"].get("chop_power",1)
    axe_stone_def["properties"]["max_durability"] = axe_stone_def["properties"].get("max_durability", 25)
    axe_stone_def["properties"]["damage_dice"] = axe_stone_def["properties"].get("damage_dice", "1d4")
    axe_stone_def["properties"]["damage_bonus"] = axe_stone_def["properties"].get("damage_bonus", 0)
    axe_stone_def["properties"]["attack_range"] = axe_stone_def["properties"].get("attack_range", 1)
    axe_stone_def["equip_slot"] = "main_hand"
    # Remove old chance based key if it exists
    if "durability_chance_to_degrade" in axe_stone_def["properties"]:
        del axe_stone_def["properties"]["durability_chance_to_degrade"]

lockpick_def = ITEM_DEFINITIONS.get("lockpick")
if lockpick_def:
    lockpick_def["stackable"] = False # Explicitly non-stackable
    if "properties" not in lockpick_def: lockpick_def["properties"] = {}
    lockpick_def["properties"]["tool_type"] = "lockpick"
    lockpick_def["properties"]["max_durability"] = lockpick_def["properties"].get("max_durability", 5)
    if "breaks_on_fail_chance" in lockpick_def["properties"]:
        del lockpick_def["properties"]["breaks_on_fail_chance"]

# Final check for item_type_tags for newly added items
new_items_to_check_tags = ["crude_spear", "wooden_shield", "raw_meat_scrap", "cooked_meat_scrap", "water_flask", "apple", "pear", "acorn"]
for key in new_items_to_check_tags:
    if key in ITEM_DEFINITIONS and "item_type_tags" not in ITEM_DEFINITIONS[key]:
        ITEM_DEFINITIONS[key]["item_type_tags"] = [] # Initialize if totally missing

    # Ensure 'stackable' is present
    if key in ITEM_DEFINITIONS and "stackable" not in ITEM_DEFINITIONS[key]:
         ITEM_DEFINITIONS[key]["stackable"] = False # Default non-stackable and then check tags
         if any(tag in ITEM_DEFINITIONS[key].get("item_type_tags", []) for tag in ["resource", "consumable", "reagent", "ammunition", "food_ingredient", "seed", "trash"]):
            ITEM_DEFINITIONS[key]["stackable"] = True

    # Ensure 'properties' and 'max_durability' for non-stackable tools/weapons/armor
    if key in ITEM_DEFINITIONS and not ITEM_DEFINITIONS[key]["stackable"]:
        if any(tag in ITEM_DEFINITIONS[key].get("item_type_tags", []) for tag in ["tool", "weapon", "armor", "shield"]):
            if "properties" not in ITEM_DEFINITIONS[key]:
                ITEM_DEFINITIONS[key]["properties"] = {}
            if "max_durability" not in ITEM_DEFINITIONS[key]["properties"]:
                 ITEM_DEFINITIONS[key]["properties"]["max_durability"] = 30 # A generic default
                 if key == "water_flask": ITEM_DEFINITIONS[key]["properties"]["max_durability"] = 3 # sips


# One final pass to remove the old "type" key if "item_type_tags" exists
for item_key, item_data in ITEM_DEFINITIONS.items():
    if "type" in item_data and "item_type_tags" in item_data:
        del item_data["type"]
