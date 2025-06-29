# data/tiles.py

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
}

# --- Tile Definitions (Back to ASCII!) ---
TILE_DEFINITIONS = {
    "plains": {
        "char": ".",
        "color": COLORS["plains_fg"],
        "passable": True,
        "name": "Plains"
    },
    "forest": {
        "char": '"',
        "color": COLORS["forest_fg"],
        "passable": True,
        "name": "Forest"
    },
    "road": {
        "char": "#",
        "color": COLORS["road_fg"],
        "passable": True,
        "name": "Road"
    },
    "wood_wall": {
        "char": "#",
        "color": COLORS["wall_fg"],
        "passable": False,
        "name": "Wood Wall"
    },
    "door": {
        "char": "+",
        "color": COLORS["door_fg"],
        "passable": True,
        "name": "Door"
    },
    "wood_floor": {
        "char": ".",
        "color": (160, 82, 45), # Sienna
        "passable": True,
        "name": "Wood Floor"
    },
    "window": {
        "char": "o",
        "color": (173, 216, 230), # Light Blue
        "passable": False,
        "name": "Window",
        "properties": {"blocks_fov": False} # Windows don't block FOV
    },
    "water": {
        "char": "~",
        "color": COLORS["water_fg"],
        "passable": False,
        "name": "Water"
    },
    "deep_water": {
        "char": "~",
        "color": COLORS["deep_water_fg"],
        "passable": False,
        "name": "Deep Water"
    },
    "mountain": {
        "char": "^",
        "color": COLORS["mountain_fg"],
        "passable": False,
        "name": "Mountain"
    },
    "snow": {
        "char": "*",
        "color": COLORS["snow_fg"],
        "passable": True,
        "name": "Snow"
    },
    "tall_grass": {
        "char": "}",
        "color": COLORS["tall_grass_fg"],
        "passable": True,
        "name": "Tall Grass"
    },
    "flower": {
        "char": "*",
        "color": COLORS["flower_fg"],
        "passable": True,
        "name": "Flower"
    },
    "well": {
        "char": "W",
        "color": (100, 100, 150), # Stone color
        "passable": False,
        "name": "Well"
    },
    "capital_hall_wall": {
        "char": "#",
        "color": (150, 150, 150), # Grey stone
        "passable": False,
        "name": "Capital Hall Wall"
    },
    "jail_bars": {
        "char": "=",
        "color": (70, 70, 70), # Dark grey
        "passable": False,
        "name": "Jail Bars"
    },
    "sheriff_office_wall": {
        "char": "#",
        "color": (120, 100, 80), # Brownish grey
        "passable": False,
        "name": "Sheriff Office Wall",
        "properties": {"provides_cover_value": 0.7} # Walls provide good cover
    },
    "tree_generic": { # Example if we had a distinct tree tile
        "char": "T",
        "color": COLORS["forest_fg"],
        "passable": False, # Trunk itself
        "name": "Tree",
        "properties": {"provides_cover_value": 0.5}
    },
    "boulder": {
        "char": "O",
        "color": (100,100,100), # Grey
        "passable": False,
        "name": "Boulder",
        "properties": {"provides_cover_value": 0.6}
    },
    "fire_trap_hidden": { # Hidden version
        "char": ".", # Looks like a normal floor tile
        "color": COLORS["plains_fg"], # Blends in
        "passable": True,
        "name": "Suspicious Floor Tile",
        "properties": {
            "is_hazard": False, # Becomes True when triggered
            "reveals_on_trigger": "fire_trap_active"
        }
    },
    "fire_trap_active": {
        "char": "*",
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
TILE_DEFINITIONS["forest"]["properties"]["provides_cover_value"] = 0.3 # General forest area provides some light cover

TILE_DEFINITIONS["water"]["properties"] = TILE_DEFINITIONS["water"].get("properties", {})
TILE_DEFINITIONS["water"]["properties"]["is_hazard"] = True
TILE_DEFINITIONS["water"]["properties"]["hazard_type"] = "water_shallows"
# No damage for shallows, but could imply slow movement later in pathfinding cost

TILE_DEFINITIONS["deep_water"]["properties"] = TILE_DEFINITIONS["deep_water"].get("properties", {})
TILE_DEFINITIONS["deep_water"]["properties"]["is_hazard"] = True
TILE_DEFINITIONS["deep_water"]["properties"]["hazard_type"] = "water_deep"
TILE_DEFINITIONS["deep_water"]["properties"]["hazard_damage"] = 1 # Minor damage for deep water, or could be drowning later

# Walls already updated above for provides_cover_value if they are added to this dict directly like sheriff_office_wall
# For other existing walls, if they are just keys in TILE_DEFINITIONS:
wall_keys = ["wood_wall", "capital_hall_wall", "jail_bars", "sheriff_office_wall"] # jail_bars might not be cover
for key in wall_keys:
    if key in TILE_DEFINITIONS:
        TILE_DEFINITIONS[key]["properties"] = TILE_DEFINITIONS[key].get("properties", {})
        if key != "jail_bars": # Jail bars likely don't provide much cover
             TILE_DEFINITIONS[key]["properties"]["provides_cover_value"] = 0.7 # Solid walls
        else:
             TILE_DEFINITIONS[key]["properties"]["provides_cover_value"] = 0.1 # Bars minimal cover

TILE_DEFINITIONS["tall_grass"]["properties"] = TILE_DEFINITIONS["tall_grass"].get("properties", {})
TILE_DEFINITIONS["tall_grass"]["properties"]["provides_cover_value"] = 0.2 # Light cover
