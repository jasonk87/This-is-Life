# data/items.py
import tcod

# --- Item Definitions ---
ITEM_DEFINITIONS = {
    # --- Resources ---
    "log": {
        "name": "Log",
        "description": "A sturdy log, good for building or fuel.",
        "char": "l",
        "color": tcod.constants.SADDLEBROWN, # (139, 69, 19)
        "value": 1,
        "weight": 5,
        "stackable": True,
        "type": ["resource"],
    },
    "stone_chunk": {
        "name": "Stone Chunk",
        "description": "A rough piece of stone, useful for basic construction.",
        "char": "s",
        "color": tcod.constants.GREY, # (128, 128, 128)
        "value": 1,
        "weight": 8,
        "stackable": True,
        "type": ["resource"],
    },
    "herb_generic": {
        "name": "Common Herb",
        "description": "A common herb, often used in simple remedies.",
        "char": "*",
        "color": tcod.constants.FOREST, # (34, 139, 34)
        "value": 2,
        "weight": 0.1,
        "stackable": True,
        "type": ["resource", "reagent"],
    },

    # --- Crafted Components ---
    "wooden_plank": {
        "name": "Wooden Plank",
        "description": "A processed wooden plank, ready for construction.",
        "char": "p",
        "color": tcod.constants.TAN, # (210, 180, 140)
        "value": 3,
        "weight": 2,
        "stackable": True,
        "type": ["component"],
        "crafting_recipe": {
            "log": 1 # 1 log makes 1 plank (can adjust to 1 log -> 2 planks later in crafting logic)
        },
    },

    # --- Tools ---
    "axe_stone": {
        "name": "Stone Axe",
        "description": "A crudely made axe with a stone head. Good for chopping wood.",
        "char": "/", # Forward slash
        "color": tcod.constants.DARKSLATEGRAY, # (47, 79, 79) - dimgray is (105,105,105)
        "value": 10,
        "weight": 7,
        "stackable": False,
        "type": ["tool", "weapon_melee_axe"],
        "properties": {
            "tool_type": "axe",
            "chop_power": 1
        },
        "crafting_recipe": {
            "stone_chunk": 2,
            "log": 1 # Log for handle
        },
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
}
