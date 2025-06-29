# data/items.py
import tcod

# --- Item Definitions ---
ITEM_DEFINITIONS = {
    # --- Resources ---
    "log": {
        "name": "Log",
        "description": "A sturdy log, good for building or fuel.",
        "char": "l",
        "color": tcod.constants.SADDLEBROWN,
        "value": 2, # Increased value slightly
        "weight": 5,
        "stackable": True,
        "type": ["resource"],
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
        "type": ["component"],
        "crafting_recipe": {
            "log": 1
        },
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
        "type": ["tool", "weapon_melee_axe"],
        "properties": {
            "tool_type": "axe",
            "chop_power": 1
        },
        "crafting_recipe": {
            "stone_chunk": 2,
            "log": 1
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
        "type": ["tool", "light_source_potential"],
        "crafting_recipe": {"log": 1, "herb_generic": 1}, # Example recipe, herb for tinder/oil
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
        "type": ["trash"]
    }
}
