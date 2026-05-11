"""
This file defines the recipes for player construction.
It maps a recipe key to the item/tile it creates, the resources required,
and the type of object it places (tile or decoration).
"""

CONSTRUCTION_RECIPES = {
    "clinic": {
        "name": "Clinic",
        "tile_def_key": "wood_wall", # Placeholder or use a specific tile if needed, but it's a building
        "source": "building", # Assuming 'building' is valid or use 'decoration' with a placeholder
        "materials": {"raw_log": 40, "stone_chunk": 10},
        "width": 7,
        "height": 6,
        "category": "civic_workplace",
        "description": "A place for healing and treatment."
    },
    "house": {
        "name": "House",
        "tile_def_key": "wood_wall",
        "source": "building",
        "materials": {"raw_log": 50},
        "required_work": 100,
        "width": 7,
        "height": 7,
        "category": "residential",
        "description": "A new home for villagers."
    },
    "farm": {
        "name": "Farm",
        "tile_def_key": "wood_wall",
        "source": "building",
        "materials": {"raw_log": 30, "stone_chunk": 10},
        "required_work": 120,
        "width": 8,
        "height": 6,
        "category": "agricultural_workplace",
        "description": "A farm to produce food."
    },
    "warehouse": {
        "name": "Warehouse",
        "tile_def_key": "wood_wall",
        "source": "building",
        "materials": {"raw_log": 35, "stone_chunk": 8},
        "required_work": 110,
        "width": 8,
        "height": 6,
        "category": "storage_workplace",
        "description": "Shared storage for growing towns and businesses."
    },
    "workshop": {
        "name": "Workshop",
        "tile_def_key": "wood_wall",
        "source": "building",
        "materials": {"raw_log": 25, "stone_chunk": 6, "wooden_plank": 8},
        "required_work": 100,
        "width": 6,
        "height": 5,
        "category": "commercial_workplace",
        "description": "A small flexible workplace for business expansion."
    },
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
    "wooden_bed": {
        "name": "Wooden Bed",
        "tile_def_key": "wooden_bed",
        "source": "decoration",
        "materials": {"wooden_plank": 15, "cloth": 4},
        "description": "A robust bed with a mattress."
    },
    "stone_anvil": {
        "name": "Stone Anvil",
        "tile_def_key": "stone_anvil",
        "source": "decoration",
        "materials": {"stone_chunk": 12},
        "description": "A heavy stone block used as an anvil."
    },
    "bookshelf": {
        "name": "Bookshelf",
        "tile_def_key": "bookshelf",
        "source": "decoration",
        "materials": {"wooden_plank": 12},
        "description": "A tall wooden shelf for holding books."
    },
    "fire_pit": {
        "name": "Fire Pit",
        "tile_def_key": "fire_pit_simple", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"stone_chunk": 4},
        "description": "Provides warmth and light."
    },
    "smoking_rack": {
        "name": "Smoking Rack",
        "tile_def_key": "smoking_rack", # From DECORATION_ITEM_DEFINITIONS
        "source": "decoration",
        "materials": {"raw_log": 2, "wooden_plank": 2},
        "description": "Preserve meat by smoking it."
    }
}
