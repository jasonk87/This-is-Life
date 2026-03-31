"""
This file defines the properties of all items in the game that can be
found in inventories, used, or crafted.
"""
from data.dawnlike import ITEM_SPRITES
from data.tiles import COLORS

# --- Item Definitions ---
ITEM_DEFINITIONS = {
    # --- Resources ---
    "raw_log": {
        "name": "Raw Log",
        "description": "A rough, unprocessed log directly from a felled tree.",
        "char": ITEM_SPRITES["raw_log"],
        "color": COLORS["saddlebrown"],
        "value": 2,
        "weight": 5,
        "stackable": True,
        "item_type_tags": ["resource"],
    },
    "stone_chunk": {
        "name": "Stone Chunk",
        "description": "A rough piece of stone, useful for basic construction.",
        "char": ITEM_SPRITES["stone_chunk"],
        "color": COLORS["grey"],
        "value": 1,
        "weight": 8,
        "stackable": True,
        "item_type_tags": ["resource"],
    },
    "medicinal_herb": {
        "name": "Medicinal Herb",
        "description": "A rare herb with potent healing properties.",
        "char": ITEM_SPRITES["medicinal_herb"],
        "color": COLORS["light_green"],
        "value": 5,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["resource", "reagent"],
    },
    "herb_generic": {
        "name": "Common Herb",
        "description": "A common herb, often used in simple remedies.",
        "char": ITEM_SPRITES["herb_generic"],
        "color": COLORS["forest_fg"],
        "value": 3,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["resource", "reagent"],
    },
    "wheat": {
        "name": "Wheat",
        "description": "Grains of wheat, can be milled into flour or used as animal feed.",
        "char": ITEM_SPRITES["wheat"],
        "color": COLORS["khaki"],
        "value": 2,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient"],
    },
    "flour": {
        "name": "Flour",
        "description": "Fine powder ground from grain, used for baking.",
        "char": ITEM_SPRITES["flour"],
        "color": (255, 255, 255),
        "value": 4,
        "weight": 0.4,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient"],
    },
    "bread": {
        "name": "Bread",
        "description": "A loaf of bread.",
        "char": ITEM_SPRITES["bread"],
        "color": COLORS["yellow_green"],
        "value": 8,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "properties": {
            "spoilage_chance": 0.02,
            "rots_into": "rotten_food"
        },
        "on_use": {
            "reduces_hunger": 50
        }
    },
    "iron_ore": {
        "name": "Iron Ore",
        "description": "A chunk of rock containing iron.",
        "char": ITEM_SPRITES["iron_ore"],
        "color": COLORS["dark_orange"],
        "value": 4,
        "weight": 10,
        "stackable": True,
        "item_type_tags": ["resource"],
    },
    "iron_ingot": {
        "name": "Iron Ingot",
        "description": "A bar of refined iron, ready for smithing.",
        "char": ITEM_SPRITES["iron_ingot"],
        "color": COLORS["silver"],
        "value": 15,
        "weight": 8,
        "stackable": True,
        "item_type_tags": ["component", "metal"],
        "crafting_recipe": {
            "iron_ore": 2,
            "coal": 1
        },
        "required_workstation": "forge"
    },
    "coal": {
        "name": "Coal",
        "description": "A combustible black rock, used as fuel.",
        "char": ITEM_SPRITES["coal"],
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
        "char": ITEM_SPRITES["wooden_plank"],
        "color": COLORS["tan"],
        "value": 5,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["component"],
        "crafting_recipe": {
            "raw_log": 1
        },
        "required_workstation": "workbench"
    },
    "workbench": {
        "name": "Workbench",
        "description": "A sturdy bench for crafting items.",
        "char": ITEM_SPRITES["workbench"],
        "color": COLORS["dark_orange"],
        "value": 50,
        "weight": 20,
        "stackable": False,
        "item_type_tags": ["furniture", "workstation"],
        "crafting_recipe": {
            "raw_log": 5
        }
    },
    "forge": {
        "name": "Forge",
        "description": "A hearth for heating metal.",
        "char": ITEM_SPRITES["forge"],
        "color": COLORS["dark_orange"],
        "value": 100,
        "weight": 100,
        "stackable": False,
        "item_type_tags": ["furniture", "workstation"],
        "crafting_recipe": {
            "stone_chunk": 10
        },
        "required_workstation": "workbench"
    },
    "anvil": {
        "name": "Anvil",
        "description": "A heavy iron block for shaping metal.",
        "char": ITEM_SPRITES["anvil"],
        "color": COLORS["dark_slate_gray"],
        "value": 150,
        "weight": 150,
        "stackable": False,
        "item_type_tags": ["furniture", "workstation"],
        "crafting_recipe": {
            "iron_ingot": 5
        },
        "required_workstation": "workbench"
    },
    "wooden_chair": {
        "name": "Wooden Chair",
        "description": "A simple wooden chair.",
        "char": ITEM_SPRITES["wooden_chair"],
        "color": COLORS["saddlebrown"],
        "value": 10,
        "weight": 5,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 4
        },
        "required_workstation": "workbench"
    },
    "wooden_table": {
        "name": "Wooden Table",
        "description": "A sturdy wooden table.",
        "char": ITEM_SPRITES["wooden_table"],
        "color": COLORS["saddlebrown"],
        "value": 20,
        "weight": 10,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 6
        },
        "required_workstation": "workbench"
    },
    "desk": {
        "name": "Desk",
        "description": "A wooden desk for reading or writing.",
        "char": ITEM_SPRITES["desk"],
        "color": COLORS["saddlebrown"],
        "value": 25,
        "weight": 12,
        "stackable": False,
        "item_type_tags": ["furniture", "workstation"],
        "crafting_recipe": {
            "wooden_plank": 8
        },
        "required_workstation": "workbench"
    },
    "counter": {
        "name": "Counter",
        "description": "A service counter.",
        "char": ITEM_SPRITES["counter"],
        "color": COLORS["saddlebrown"],
        "value": 30,
        "weight": 15,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 10
        },
        "required_workstation": "workbench"
    },
    "storage": {
        "name": "Storage Crate",
        "description": "A wooden crate for storing items.",
        "char": ITEM_SPRITES["storage"],
        "color": COLORS["saddlebrown"],
        "value": 15,
        "weight": 5,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 4
        },
        "required_workstation": "workbench"
    },
    "chest_wooden": {
        "name": "Wooden Chest",
        "description": "A sturdy wooden chest.",
        "char": ITEM_SPRITES["chest_wooden"],
        "color": COLORS["saddlebrown"],
        "value": 25,
        "weight": 10,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 6
        },
        "required_workstation": "workbench"
    },
    "shelf": {
        "name": "Shelf",
        "description": "A simple wooden shelf.",
        "char": ITEM_SPRITES["shelf"],
        "color": COLORS["saddlebrown"],
        "value": 10,
        "weight": 3,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 3
        },
        "required_workstation": "workbench"
    },
    "dresser": {
        "name": "Dresser",
        "description": "A wooden dresser for clothes.",
        "char": ITEM_SPRITES["dresser"],
        "color": COLORS["saddlebrown"],
        "value": 25,
        "weight": 12,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 8
        },
        "required_workstation": "workbench"
    },
    "fireplace": {
        "name": "Fireplace",
        "description": "A stone fireplace for warmth and cooking.",
        "char": ITEM_SPRITES["fireplace"],
        "color": COLORS["grey"],
        "value": 50,
        "weight": 100,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "stone_chunk": 20
        }
    },
    "bed_simple": {
        "name": "Simple Bed",
        "description": "A simple bed with a straw mattress.",
        "char": ITEM_SPRITES["bed_simple"],
        "color": COLORS["tan"],
        "value": 30,
        "weight": 15,
        "stackable": False,
        "item_type_tags": ["furniture"],
        "crafting_recipe": {
            "wooden_plank": 8,
            "raw_log": 4
        },
        "required_workstation": "workbench"
    },
    "lumber_processed": {
        "name": "Processed Lumber",
        "description": "Smooth, processed lumber, ready for fine construction.",
        "char": ITEM_SPRITES["lumber_processed"],
        "color": COLORS["burlywood"],
        "value": 8,
        "weight": 3,
        "stackable": True,
        "item_type_tags": ["resource", "component"],
    },
    "wheat_seeds": {
        "name": "Wheat Seeds",
        "description": "Seeds for growing wheat.",
        "char": ITEM_SPRITES["wheat_seeds"],
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
        "char": ITEM_SPRITES["axe_stone"],
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
        "required_workstation": "workbench"
    },
    "broken_tool_handle": {
        "name": "Broken Tool Handle",
        "description": "The snapped wooden handle of a tool. Might be reusable.",
        "char": ITEM_SPRITES["broken_tool_handle"],
        "color": COLORS["dark_sepia"],
        "value": 1,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "component"]
    },
    "lockpick": {
        "name": "Lockpick",
        "description": "A thin piece of metal used for picking locks. Fragile.",
        "char": ITEM_SPRITES["lockpick"],
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
        "char": ITEM_SPRITES["healing_salve"],
        "color": COLORS["light_green"],
        "value": 15,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["consumable", "healing"],
        "crafting_recipe": {
            "medicinal_herb": 2
        },
        "on_use": {
            "heal_amount": 10
        }
    },
    "unlit_torch": {
        "name": "Unlit Torch",
        "description": "A stick with oil-soaked rags, needs to be lit.",
        "char": ITEM_SPRITES["unlit_torch"],
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
        "char": ITEM_SPRITES["torch_lit"],
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
            "max_durability": 600
        },
        "on_use_effect": "extinguish_torch"
    },
    "burnt_out_torch": {
        "name": "Burnt Out Torch",
        "description": "The charred remains of a torch. Useless.",
        "char": ITEM_SPRITES["burnt_out_torch"],
        "color": COLORS["darkest_grey"],
        "value": 0,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["trash"]
    },
    "rotten_food": {
        "name": "Rotten Food",
        "description": "A foul-smelling mass of decayed food. Do not eat.",
        "char": ITEM_SPRITES["rotten_food"],
        "color": (101, 67, 33), # Dark brown
        "value": 0,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["trash", "consumable"],
        "on_use": {
            "reduces_hunger": 5,
            "inflicts_status": "Sick",
            "damage": 5
        }
    },
    "water_flask": {
        "name": "Water Flask",
        "description": "A simple flask filled with water. Refreshing.",
        "char": ITEM_SPRITES["water_flask"],
        "color": COLORS["light_blue"],
        "value": 5,
        "weight": 1,
        "stackable": False,
        "item_type_tags": ["consumable", "drink"],
        "properties": {
             "max_durability": 3
        },
        "on_use": {
            "reduces_thirst": 40
        }
    },
    "apple": {
        "name": "Apple",
        "description": "A crisp, juicy apple.",
        "char": ITEM_SPRITES["apple"],
        "color": COLORS["red"],
        "value": 3,
        "weight": 0.3,
        "stackable": True,
        "item_type_tags": ["consumable", "food", "fruit"],
        "properties": {
            "spoilage_chance": 0.05,
            "rots_into": "rotten_food"
        },
        "on_use": {
            "reduces_hunger": 10,
            "reduces_thirst": 5
        }
    },
    "pear": {
        "name": "Pear",
        "description": "A sweet and soft pear.",
        "char": ITEM_SPRITES["pear"],
        "color": COLORS["yellow_green"],
        "value": 3,
        "weight": 0.3,
        "stackable": True,
        "item_type_tags": ["consumable", "food", "fruit"],
        "properties": {
            "spoilage_chance": 0.05,
            "rots_into": "rotten_food"
        },
        "on_use": {
            "reduces_hunger": 10,
            "reduces_thirst": 7
        }
    },
    "acorn": {
        "name": "Acorn",
        "description": "The nut of an oak tree. Edible in a pinch.",
        "char": ITEM_SPRITES["acorn"],
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
        "char": ITEM_SPRITES["sapling"],
        "color": COLORS["yellow_green"],
        "value": 5,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "reforestation"],
    },
    "raw_venison": {
        "name": "Raw Venison",
        "description": "A cut of raw deer meat.",
        "char": ITEM_SPRITES["raw_venison"],
        "color": COLORS["crimson"],
        "value": 8,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"],
        "properties": {
            "spoilage_chance": 0.2,
            "rots_into": "rotten_food"
        },
    },
    "raw_meat": {
        "name": "Raw Meat",
        "description": "A chunk of raw meat from an animal.",
        "char": ITEM_SPRITES["raw_meat"],
        "color": COLORS["crimson"],
        "value": 5,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"],
        "properties": {
            "spoilage_chance": 0.2,
            "rots_into": "rotten_food"
        },
    },
    "cooked_meat": {
        "name": "Cooked Meat",
        "description": "Meat cooked over a fire. Savory and filling.",
        "char": ITEM_SPRITES["cooked_meat"],
        "color": COLORS["saddlebrown"],
        "value": 10,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "properties": {
            "spoilage_chance": 0.05,
            "rots_into": "rotten_food"
        },
        "on_use": {
            "reduces_hunger": 45
        },
        "crafting_recipe": {
            "raw_meat": 1
        },
        "required_workstation": "fire"
    },
    "smoked_meat": {
        "name": "Smoked Meat",
        "description": "Meat preserved by smoking. Lasts a long time.",
        "char": ITEM_SPRITES["smoked_meat"],
        "color": (139, 69, 19), # Darker brown
        "value": 15,
        "weight": 0.8,
        "stackable": True,
        "item_type_tags": ["consumable", "food", "preserved"],
        "properties": {
            "spoilage_chance": 0.005, # Very low chance
            "rots_into": "rotten_food"
        },
        "on_use": {
            "reduces_hunger": 40
        }
    },
    "animal_pelt": {
        "name": "Animal Pelt",
        "description": "The uncured hide of an animal, with fur intact.",
        "char": ITEM_SPRITES["animal_pelt"],
        "color": COLORS["saddlebrown"],
        "value": 10,
        "weight": 3,
        "stackable": True,
        "item_type_tags": ["resource", "leather"],
    },
    "tanned_leather": {
        "name": "Tanned Leather",
        "description": "Cured and treated animal hide, suitable for crafting.",
        "char": ITEM_SPRITES["tanned_leather"],
        "color": COLORS["dark_amber"],
        "value": 25,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["component", "leather"],
        "crafting_recipe": {
            "animal_pelt": 2
        },
    },
    "raw_mutton": {
        "name": "Raw Mutton",
        "description": "A cut of raw sheep meat.",
        "char": ITEM_SPRITES["raw_mutton"],
        "color": COLORS["crimson"],
        "value": 6,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"],
        "properties": {
            "spoilage_chance": 0.2,
            "rots_into": "rotten_food"
        },
    },
    "raw_wool": {
        "name": "Raw Wool",
        "description": "A fluffy bundle of raw, unprocessed wool.",
        "char": ITEM_SPRITES["raw_wool"],
        "color": (255, 255, 240),
        "value": 10,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["resource", "fiber"],
    },
    "rusty_sword": {
        "name": "Rusty Sword",
        "description": "A worn, but still somewhat sharp sword.",
        "char": ITEM_SPRITES["rusty_sword"],
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
        "char": ITEM_SPRITES["crude_spear"],
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
        "char": ITEM_SPRITES["short_bow"],
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
        "char": ITEM_SPRITES["arrow"],
        "color": COLORS["light_sepia"],
        "value": 1,
        "weight": 0.1,
        "stackable": True,
        "item_type_tags": ["ammunition", "arrow"]
    },
    "wooden_shield": {
        "name": "Wooden Shield",
        "description": "A simple shield made of wooden planks.",
        "char": ITEM_SPRITES["wooden_shield"],
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
        "char": ITEM_SPRITES["leather_jerkin"],
        "color": COLORS["dark_amber"],
        "value": 40,
        "weight": 5,
        "stackable": False,
        "item_type_tags": ["armor", "body"],
        "equip_slot": "body",
        "properties": {
            "defense_bonus": 1,
            "max_durability": 60
        }
    },
    "iron_helmet": {
        "name": "Iron Helmet",
        "description": "A sturdy iron helmet.",
        "char": ITEM_SPRITES["iron_helmet"],
        "color": COLORS["dark_slate_gray"],
        "value": 35,
        "weight": 3,
        "stackable": False,
        "item_type_tags": ["armor", "head"],
        "equip_slot": "head",
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
        "char": ITEM_SPRITES["stone_pickaxe"],
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
    "stone_hoe": {
        "name": "Stone Hoe",
        "description": "A crude hoe for tilling soil.",
        "char": ITEM_SPRITES["stone_hoe"],
        "color": COLORS["dark_slate_gray"],
        "value": 20,
        "weight": 6,
        "stackable": False,
        "item_type_tags": ["tool"],
        "equip_slot": "main_hand",
        "properties": {
            "tool_type": "hoe",
            "max_durability": 20
        },
        "crafting_recipe": {
            "stone_chunk": 2,
            "raw_log": 2
        },
    },
    "iron_sword": {
        "name": "Iron Sword",
        "description": "A simple but effective iron sword.",
        "char": ITEM_SPRITES["iron_sword"],
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
        "required_workstation": "anvil"
    },
    "iron_breastplate": {
        "name": "Iron Breastplate",
        "description": "A sturdy breastplate made of iron.",
        "char": ITEM_SPRITES["iron_breastplate"],
        "color": COLORS["silver"],
        "value": 80,
        "weight": 15,
        "stackable": False,
        "item_type_tags": ["armor", "body"],
        "equip_slot": "body",
        "properties": {
            "defense_bonus": 2,
            "max_durability": 100
        },
        "crafting_recipe": {
            "iron_ingot": 5
        },
        "required_workstation": "anvil"
    },
    "fur_cloak": {
        "name": "Fur Cloak",
        "description": "A thick cloak made of animal fur, providing excellent warmth.",
        "char": ITEM_SPRITES["fur_cloak"],
        "color": COLORS["dark_sepia"],
        "value": 60,
        "weight": 8,
        "stackable": False,
        "item_type_tags": ["armor", "body"],
        "equip_slot": "body",
        "properties": {
            "defense_bonus": 0,
            "insulation": 10.0,
            "max_durability": 80
        },
        "crafting_recipe": {
            "tanned_leather": 5,
        },
    },
    "hooded_cowl": {
        "name": "Hooded Cowl",
        "description": "A deep hood and wrapped cowl that hides the wearer's face in shadow.",
        "char": ITEM_SPRITES["hooded_cowl"],
        "color": COLORS["dark_sepia"],
        "value": 35,
        "weight": 1,
        "stackable": False,
        "item_type_tags": ["armor", "head", "disguise"],
        "equip_slot": "head",
        "properties": {
            "defense_bonus": 0,
            "insulation": 2.0,
            "max_durability": 30,
            "conceals_identity": True,
        },
        "crafting_recipe": {
            "cloth": 2,
        },
        "required_workstation": "loom",
    },
    "fish": {
        "name": "Fish",
        "description": "A freshly caught fish.",
        "char": ITEM_SPRITES["fish"],
        "color": COLORS["silver"],
        "value": 5,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "on_use": {
            "reduces_hunger": 20
        }
    },
    "knife_stone": {
        "name": "Stone Knife",
        "description": "A sharp piece of stone, useful for skinning and butchering.",
        "char": ITEM_SPRITES["knife_stone"],
        "color": COLORS["dark_slate_gray"],
        "value": 15,
        "weight": 1,
        "stackable": False,
        "item_type_tags": ["tool", "weapon", "melee", "knife"],
        "equip_slot": "main_hand",
        "properties": {
            "tool_type": "knife",
            "butcher_power": 1,
            "max_durability": 15,
            "damage_dice": "1d3",
            "damage_bonus": 0,
            "attack_range": 1
        },
        "crafting_recipe": {
            "stone_chunk": 1,
            "raw_log": 1
        },
    },
    "shears": {
        "name": "Shears",
        "description": "A tool for shearing wool from sheep.",
        "char": ITEM_SPRITES["shears"],
        "color": COLORS["silver"],
        "value": 40,
        "weight": 2,
        "stackable": False,
        "item_type_tags": ["tool"],
        "properties": {
            "tool_type": "shears",
            "max_durability": 25
        },
        "crafting_recipe": {
            "iron_ingot": 2
        },
        "required_workstation": "anvil"
    },
    "loom": {
        "name": "Loom",
        "description": "A device for weaving thread into cloth.",
        "char": ITEM_SPRITES["loom"],
        "color": COLORS["saddlebrown"],
        "value": 75,
        "weight": 30,
        "stackable": False,
        "item_type_tags": ["furniture", "workstation"],
        "crafting_recipe": {
            "wooden_plank": 10
        },
        "required_workstation": "workbench"
    },
    "cloth": {
        "name": "Cloth",
        "description": "A piece of woven cloth.",
        "char": ITEM_SPRITES["cloth"],
        "color": (220, 220, 220),
        "value": 25,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["component", "fabric"],
        "crafting_recipe": {
            "raw_wool": 2
        },
        "required_workstation": "loom"
    },
    "cloth_tunic": {
        "name": "Cloth Tunic",
        "description": "A simple tunic made of woven cloth.",
        "char": ITEM_SPRITES["cloth_tunic"],
        "color": (220, 220, 220),
        "value": 50,
        "weight": 2,
        "stackable": False,
        "item_type_tags": ["armor", "body"],
        "equip_slot": "body",
        "properties": {
            "defense_bonus": 0,
            "insulation": 5.0,
            "max_durability": 40
        },
        "crafting_recipe": {
            "cloth": 4
        },
        "required_workstation": "loom"
    },
    "fishing_rod": {
        "name": "Fishing Rod",
        "description": "A simple fishing rod for catching fish.",
        "char": ITEM_SPRITES["fishing_rod"],
        "color": COLORS["dark_sepia"],
        "value": 20,
        "weight": 3,
        "stackable": False,
        "item_type_tags": ["tool"],
        "properties": {
            "tool_type": "fishing_rod",
            "max_durability": 25
        },
        "crafting_recipe": {
            "raw_log": 3,
            "cloth": 1
        }
    },
    "raw_fish": {
        "name": "Raw Fish",
        "description": "A raw fish, freshly caught. Should be cooked.",
        "char": ITEM_SPRITES["raw_fish"],
        "color": COLORS["silver"],
        "value": 4,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"],
        "properties": {
            "spoilage_chance": 0.25,
            "rots_into": "rotten_food"
        },
        "on_use": {
            "reduces_hunger": 15
        }
    },
    "cooked_fish": {
        "name": "Cooked Fish",
        "description": "A fish, cooked over a fire. A satisfying meal.",
        "char": ITEM_SPRITES["cooked_fish"],
        "color": COLORS["dark_orange"],
        "value": 8,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "properties": {
            "spoilage_chance": 0.05,
            "rots_into": "rotten_food"
        },
        "crafting_recipe": {
            "raw_fish": 1
        },
        "required_workstation": "fire",
        "on_use": {
            "reduces_hunger": 40
        }
    },
    "smoked_fish": {
        "name": "Smoked Fish",
        "description": "Fish preserved by smoking.",
        "char": ITEM_SPRITES["smoked_fish"],
        "color": (139, 69, 19),
        "value": 12,
        "weight": 0.8,
        "stackable": True,
        "item_type_tags": ["consumable", "food", "preserved"],
        "properties": {
            "spoilage_chance": 0.005,
            "rots_into": "rotten_food"
        },
        "on_use": {
            "reduces_hunger": 35
        }
    },
    "cooked_venison": {
        "name": "Cooked Venison",
        "description": "Delicious roasted deer meat.",
        "char": ITEM_SPRITES["cooked_venison"],
        "color": COLORS["saddlebrown"],
        "value": 15,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "properties": {
            "spoilage_chance": 0.05,
            "rots_into": "rotten_food"
        },
        "crafting_recipe": {
            "raw_venison": 1
        },
        "required_workstation": "fire",
        "on_use": {
            "reduces_hunger": 60
        }
    },
    "cooked_mutton": {
        "name": "Cooked Mutton",
        "description": "Hearty roasted sheep meat.",
        "char": ITEM_SPRITES["cooked_mutton"],
        "color": COLORS["saddlebrown"],
        "value": 12,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "properties": {
            "spoilage_chance": 0.05,
            "rots_into": "rotten_food"
        },
        "crafting_recipe": {
            "raw_mutton": 1
        },
        "required_workstation": "fire",
        "on_use": {
            "reduces_hunger": 50
        }
    },
    "book_census": {
        "name": "Census",
        "description": "A record of births and deaths in the village.",
        "char": ITEM_SPRITES["book_census"],
        "color": COLORS["dark_amber"],
        "value": 100,
        "weight": 2,
        "stackable": False,
        "item_type_tags": ["book", "readable"],
        "properties": {
            "interaction_hint": "read"
        }
    },
    "book_chronicle": {
        "name": "Chronicle",
        "description": "A record of significant events in the village.",
        "char": ITEM_SPRITES["book_chronicle"],
        "color": COLORS["dark_amber"],
        "value": 100,
        "weight": 2,
        "stackable": False,
        "item_type_tags": ["book", "readable"],
        "properties": {
            "interaction_hint": "read"
        }
    }
}
