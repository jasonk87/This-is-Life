"""
This file defines the recipes for player construction.
It maps a recipe key to the item/tile it creates, the resources required,
and the type of object it places (tile or decoration).
"""

CONSTRUCTION_RECIPES = {
    "wood_wall": {
        "name": "Wooden Wall",
        "tile_def_key": "wood_wall", # From TILE_DEFINITIONS
        "source": "tile",
        "materials": {"raw_log": 2},
        "description": "A sturdy wooden wall."
    },
    "wood_floor": {
        "name": "Wooden Floor",
        "tile_def_key": "wood_floor", # From TILE_DEFINITIONS
        "source": "tile",
        "materials": {"wooden_plank": 2},
        "description": "Basic wooden flooring."
    },
    "wooden_door": {
        "name": "Wooden Door",
        "tile_def_key": "wooden_door_closed", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"wooden_plank": 4},
        "description": "A door to provide privacy."
    },
    "simple_bed": {
        "name": "Simple Bed",
        "tile_def_key": "bed_simple", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"wooden_plank": 4, "cloth": 2},
        "description": "A simple bed for sleeping."
    },
    "wooden_chest": {
        "name": "Wooden Chest",
        "tile_def_key": "chest_wooden", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"wooden_plank": 6},
        "description": "Storage for your items."
    },
    "wooden_chair": {
        "name": "Wooden Chair",
        "tile_def_key": "wooden_chair", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"wooden_plank": 2},
        "description": "A chair to sit on."
    },
    "wooden_table": {
        "name": "Wooden Table",
        "tile_def_key": "wooden_table", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"wooden_plank": 4},
        "description": "A table for placing items."
    },
    "fire_pit": {
        "name": "Fire Pit",
        "tile_def_key": "fire_pit_simple", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"stone_chunk": 4},
        "description": "Provides warmth and light."
    }
}
