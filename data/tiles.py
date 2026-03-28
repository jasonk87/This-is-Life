"""
This file defines the properties of all tiles in the game, including their
character representation, color, passability, and other special properties.
It also contains a dictionary of color definitions used throughout the game.
"""
# data/tiles.py

from data.dawnlike import WORLD_TILE_SPRITES

# --- Color Definitions (RGB Tuples) ---
COLORS = {
    "plains_fg": (102, 178, 102),  # Green
    "forest_fg": (34, 139, 34),   # Darker Green
    "road_fg": (139, 137, 137),  # Grey
    "wall_fg": (139, 69, 19),    # Brown
    "door_fg": (160, 82, 45),    # Lighter Brown
    "player_fg": (255, 255, 0),    # Yellow
    "water_fg": (64, 100, 164),    # Blue
    "deep_water_fg": (40, 60, 120), # Dark Blue
    "tall_grass_fg": (60, 140, 60),    # A darker, richer green
    "flower_fg": (255, 105, 180),  # Hot Pink
    "mountain_fg": (130, 130, 130), # Grey
    "snow_fg": (250, 250, 250),   # White
    "saddlebrown": (139, 69, 19),
    "grey": (128, 128, 128),
    "dark_orange": (255, 140, 0),
    "tan": (210, 180, 140),
    "burlywood": (222, 184, 135),
    "khaki": (240, 230, 140),
    "dark_slate_gray": (47, 79, 79),
    "dark_sepia": (118, 92, 72),
    "silver": (192, 192, 192),
    "light_green": (144, 238, 144),
    "dark_amber": (128, 70, 27),
    "flame": (242, 85, 44),
    "darkest_grey": (32, 32, 32),
    "light_blue": (173, 216, 230),
    "red": (255, 0, 0),
    "yellow_green": (154, 205, 50),
    "crimson": (220, 20, 60),
    "light_sepia": (208, 188, 142),
    "sienna": (160, 82, 45),
}

# --- Tile Definitions (Back to ASCII!) ---
TILE_DEFINITIONS = {
    "plains": {
        "char": WORLD_TILE_SPRITES["plains"],
        "color": COLORS["plains_fg"],
        "passable": True,
        "name": "Plains"
    },
    "forest": {
        "char": WORLD_TILE_SPRITES["forest"],
        "color": COLORS["forest_fg"],
        "passable": True,
        "name": "Forest"
    },
    "road": {
        "char": WORLD_TILE_SPRITES["road"],
        "color": COLORS["road_fg"],
        "passable": True,
        "name": "Road"
    },
    "wood_wall": {
        "char": WORLD_TILE_SPRITES["wood_wall"],
        "color": COLORS["wall_fg"],
        "passable": False,
        "name": "Wood Wall",
        "properties": {"provides_shelter": True}
    },
    "stone_wall": {
        "char": WORLD_TILE_SPRITES["stone_wall"],
        "color": COLORS["grey"],
        "passable": False,
        "name": "Stone Wall",
        "properties": {"provides_shelter": True}
    },
    "brick_wall": {
        "char": WORLD_TILE_SPRITES["brick_wall"],
        "color": COLORS["wall_fg"],
        "passable": False,
        "name": "Brick Wall",
        "properties": {"provides_shelter": True}
    },
    "plaster_wall": {
        "char": WORLD_TILE_SPRITES["plaster_wall"],
        "color": COLORS["khaki"],
        "passable": False,
        "name": "Plaster Wall",
        "properties": {"provides_shelter": True}
    },
    "log_wall": {
        "char": WORLD_TILE_SPRITES["log_wall"],
        "color": COLORS["saddlebrown"],
        "passable": False,
        "name": "Log Wall",
        "properties": {"provides_shelter": True}
    },
    "door": {
        "char": WORLD_TILE_SPRITES["door"],
        "color": COLORS["door_fg"],
        "passable": True,
        "name": "Door"
    },
    "wood_floor": {
        "char": WORLD_TILE_SPRITES["wood_floor"],
        "color": (160, 82, 45), # Sienna
        "passable": True,
        "name": "Wood Floor"
    },
    "stone_floor": {
        "char": WORLD_TILE_SPRITES["stone_floor"],
        "color": COLORS["grey"],
        "passable": True,
        "name": "Stone Floor"
    },
    "brick_floor": {
        "char": WORLD_TILE_SPRITES["brick_floor"],
        "color": COLORS["wall_fg"],
        "passable": True,
        "name": "Brick Floor"
    },
    "dirt_floor": {
        "char": WORLD_TILE_SPRITES["dirt_floor"],
        "color": COLORS["saddlebrown"],
        "passable": True,
        "name": "Dirt Floor"
    },
    "window": {
        "char": WORLD_TILE_SPRITES["window"],
        "color": (173, 216, 230), # Light Blue
        "passable": False,
        "name": "Window",
        "properties": {"blocks_fov": False} # Windows don't block FOV
    },
    "water": {
        "char": WORLD_TILE_SPRITES["water"],
        "color": COLORS["water_fg"],
        "passable": False,
        "name": "Water"
    },
    "deep_water": {
        "char": WORLD_TILE_SPRITES["deep_water"],
        "color": COLORS["deep_water_fg"],
        "passable": False,
        "name": "Deep Water"
    },
    "mountain": {
        "char": WORLD_TILE_SPRITES["mountain"],
        "color": COLORS["mountain_fg"],
        "passable": False,
        "name": "Mountain"
    },
    "snow": {
        "char": WORLD_TILE_SPRITES["snow"],
        "color": COLORS["snow_fg"],
        "passable": True,
        "name": "Snow",
        "properties": {"movement_cost": 2}
    },
    "tall_grass": {
        "char": WORLD_TILE_SPRITES["tall_grass"],
        "color": COLORS["tall_grass_fg"],
        "passable": True,
        "name": "Tall Grass"
    },
    "flower": {
        "char": WORLD_TILE_SPRITES["flower"],
        "color": COLORS["flower_fg"],
        "passable": True,
        "name": "Flower"
    },
    "well": {
        "char": WORLD_TILE_SPRITES["well"],
        "color": (100, 100, 150), # Stone color
        "passable": False,
        "name": "Well"
    },
    "capital_hall_wall": {
        "char": WORLD_TILE_SPRITES["capital_hall_wall"],
        "color": (150, 150, 150), # Grey stone
        "passable": False,
        "name": "Capital Hall Wall",
        "properties": {"provides_shelter": True}
    },
    "jail_bars": {
        "char": WORLD_TILE_SPRITES["jail_bars"],
        "color": (70, 70, 70), # Dark grey
        "passable": False,
        "name": "Jail Bars"
    },
    "sheriff_office_wall": {
        "char": WORLD_TILE_SPRITES["sheriff_office_wall"],
        "color": (120, 100, 80), # Brownish grey
        "passable": False,
        "name": "Sheriff Office Wall",
        "properties": {"provides_cover_value": 0.7, "provides_shelter": True}
    },
    "tree_generic": { # Example if we had a distinct tree tile
        "char": WORLD_TILE_SPRITES["tree_generic"],
        "color": COLORS["forest_fg"],
        "passable": False, # Trunk itself
        "name": "Tree",
        "properties": {"provides_cover_value": 0.5}
    },
    "boulder": {
        "char": WORLD_TILE_SPRITES["boulder"],
        "color": (100,100,100), # Grey
        "passable": False,
        "name": "Boulder",
        "properties": {"provides_cover_value": 0.6}
    },
    "fire_trap_hidden": { # Hidden version
        "char": WORLD_TILE_SPRITES["fire_trap_hidden"],
        "color": COLORS["plains_fg"], # Blends in
        "passable": True,
        "name": "Suspicious Floor Tile",
        "properties": {
            "is_hazard": False, # Becomes True when triggered
            "reveals_on_trigger": "fire_trap_active"
        }
    },
    "fire_trap_active": {
        "char": WORLD_TILE_SPRITES["fire_trap_active"],
        "color": (255,0,0), # Red
        "passable": True, # Can walk through fire, but take damage
        "name": "Fire Trap (Active)",
        "properties": {
            "is_hazard": True,
            "hazard_type": "fire",
            "hazard_damage": 5,
            "provides_cover_value": 0.0
        }
    }
}

# Update existing definitions with new properties
TILE_DEFINITIONS["forest"]["properties"] = TILE_DEFINITIONS["forest"].get("properties", {})
TILE_DEFINITIONS["forest"]["properties"]["provides_cover_value"] = 0.3

TILE_DEFINITIONS["water"]["properties"] = TILE_DEFINITIONS["water"].get("properties", {})
TILE_DEFINITIONS["water"]["properties"]["is_hazard"] = True
TILE_DEFINITIONS["water"]["properties"]["hazard_type"] = "water_shallows"

TILE_DEFINITIONS["deep_water"]["properties"] = TILE_DEFINITIONS["deep_water"].get("properties", {})
TILE_DEFINITIONS["deep_water"]["properties"]["is_hazard"] = True
TILE_DEFINITIONS["deep_water"]["properties"]["hazard_type"] = "water_deep"
TILE_DEFINITIONS["deep_water"]["properties"]["hazard_damage"] = 1

wall_keys = ["wood_wall", "capital_hall_wall", "jail_bars", "sheriff_office_wall"]
for key in wall_keys:
    if key in TILE_DEFINITIONS:
        TILE_DEFINITIONS[key]["properties"] = TILE_DEFINITIONS[key].get("properties", {})
        if key != "jail_bars":
            TILE_DEFINITIONS[key]["properties"]["provides_cover_value"] = 0.7
        else:
            TILE_DEFINITIONS[key]["properties"]["provides_cover_value"] = 0.1

TILE_DEFINITIONS["tall_grass"]["properties"] = TILE_DEFINITIONS["tall_grass"].get("properties", {})
TILE_DEFINITIONS["tall_grass"]["properties"]["provides_cover_value"] = 0.2
TILE_DEFINITIONS["tall_grass"]["properties"]["yields_on_pass_through"] = {
    "item_key": "wheat_seeds",
    "quantity": [1, 2],
    "chance": 0.1
}

TILE_DEFINITIONS["stump_generic"] = {
    "char": WORLD_TILE_SPRITES["stump_generic"],
    "color": (101, 67, 33),  # Brownish, like a cut log
    "passable": True,
    "name": "Tree Stump",
    "properties": {
        "is_choppable": False, # Can't chop a stump further by default
        "provides_cover_value": 0.1 # Very minor cover
    }
}

TILE_DEFINITIONS["sapling"] = {
    "char": WORLD_TILE_SPRITES["sapling"],
    "color": (154, 205, 50), # YellowGreen
    "passable": True,
    "name": "Sapling",
    "properties": {
        "growth_timer": 200, # Ticks to grow into a tree
        "evolves_to": "oak_tree" # Default evolution
    }
}

TILE_DEFINITIONS["tilled_soil"] = {
    "char": WORLD_TILE_SPRITES["tilled_soil"],
    "color": (160, 110, 70),  # Darker, richer brown than wood_floor
    "passable": True,
    "name": "Tilled Soil",
    "properties": {}
}
TILE_DEFINITIONS["wheat_plant_growing"] = {
    "char": WORLD_TILE_SPRITES["wheat_plant_growing"],
    "color": (144, 238, 144), # Light green
    "passable": True,
    "name": "Growing Wheat",
    "properties": {
        "growth_progress": 0,
        "growth_needed": 100, # Example value
        "evolves_to": "wheat_plant"
    }
}
TILE_DEFINITIONS["wheat_plant"] = {
    "char": WORLD_TILE_SPRITES["wheat_plant"],
    "color": (255, 223, 0),  # Golden yellow
    "passable": True,
    "name": "Wheat",
    "properties": {
        "is_harvestable": True,
        "harvest_yield_item_key": "wheat",
        "harvest_yield_quantity": 2,
        "becomes_on_harvest_key": "tilled_soil"
    }
}

TILE_DEFINITIONS["cracked_stone_wall"] = {
    "char": WORLD_TILE_SPRITES["cracked_stone_wall"],
    "color": (105, 105, 105), # DimGray
    "passable": False,
    "name": "Cracked Stone Wall",
    "properties": {"provides_shelter": True, "provides_cover_value": 0.6}
}

TILE_DEFINITIONS["mossy_cobblestone"] = {
    "char": WORLD_TILE_SPRITES["mossy_cobblestone"],
    "color": (85, 107, 47), # DarkOliveGreen
    "passable": True,
    "name": "Mossy Cobblestone"
}
