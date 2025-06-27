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
        "name": "Window"
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
        "name": "Sheriff Office Wall"
    },
}
