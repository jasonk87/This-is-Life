"""
This file defines the properties of all items in the game that can be
found in inventories, used, or crafted.
"""
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
        "crafting_recipe": {
            "iron_ore": 2,
            "coal": 1
        },
        "required_workstation": "forge"
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
        "required_workstation": "workbench"
    },
    "workbench": {
        "name": "Workbench",
        "description": "A sturdy bench for crafting items.",
        "char": "W",
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
        "char": "F",
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
        "char": "A",
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
        "char": "h",
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
        "char": "T",
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
    "bed_simple": {
        "name": "Simple Bed",
        "description": "A simple bed with a straw mattress.",
        "char": "B",
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
        "required_workstation": "workbench"
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
            "max_durability": 600
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
             "max_durability": 3
        },
        "on_use": {
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
    "raw_venison": {
        "name": "Raw Venison",
        "description": "A cut of raw deer meat.",
        "char": "m",
        "color": COLORS["crimson"],
        "value": 8,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"],
    },
    "animal_pelt": {
        "name": "Animal Pelt",
        "description": "The uncured hide of an animal, with fur intact.",
        "char": "p",
        "color": COLORS["saddlebrown"],
        "value": 10,
        "weight": 3,
        "stackable": True,
        "item_type_tags": ["resource", "leather"],
    },
    "tanned_leather": {
        "name": "Tanned Leather",
        "description": "Cured and treated animal hide, suitable for crafting.",
        "char": "L",
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
        "char": "m",
        "color": COLORS["crimson"],
        "value": 6,
        "weight": 2,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"],
    },
    "raw_wool": {
        "name": "Raw Wool",
        "description": "A fluffy bundle of raw, unprocessed wool.",
        "char": "u",
        "color": (255, 255, 240),
        "value": 10,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["resource", "fiber"],
    },
     "raw_meat_scrap": {
        "name": "Raw Meat Scrap",
        "description": "A piece of raw meat. Needs cooking.",
        "char": "m",
        "color": COLORS["crimson"],
        "value": 1,
        "weight": 0.5,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"]
    },
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
        "equip_slot": "body",
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
    "stone_hoe": {
        "name": "Stone Hoe",
        "description": "A crude hoe for tilling soil.",
        "char": "h",
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
        "required_workstation": "anvil"
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
        "char": "C",
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
    },
    "knife_stone": {
        "name": "Stone Knife",
        "description": "A sharp piece of stone, useful for skinning and butchering.",
        "char": "k",
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
        "char": "s",
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
        "char": "L",
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
        "char": "c",
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
        "char": "t",
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
        "char": "/",
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
        "char": "f",
        "color": COLORS["silver"],
        "value": 4,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["resource", "food_ingredient_raw"],
        "on_use": {
            "reduces_hunger": 15
        }
    },
    "cooked_fish": {
        "name": "Cooked Fish",
        "description": "A fish, cooked over a fire. A satisfying meal.",
        "char": "f",
        "color": COLORS["dark_orange"],
        "value": 8,
        "weight": 1,
        "stackable": True,
        "item_type_tags": ["consumable", "food"],
        "crafting_recipe": {
            "raw_fish": 1
        },
        "required_workstation": "fire",
        "on_use": {
            "reduces_hunger": 40
        }
    },
    "book_census": {
        "name": "Census",
        "description": "A record of births and deaths in the village.",
        "char": "B",
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
        "char": "B",
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
