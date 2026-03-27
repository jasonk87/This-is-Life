"""
This file defines the properties of different weather types in the game.
"""
from data.dawnlike import WEATHER_SPRITES
from data.tiles import COLORS

WEATHER_DEFINITIONS = {
    "clear": {
        "name": "Clear",
        "char": WEATHER_SPRITES["clear"],
        "color": (255, 255, 255),
        "applies_wetness": False,
        "extinguishes_fires": False,
        "slows_movement": False,
        "seasons": ["Spring", "Summer", "Autumn", "Winter"],
    },
    "rain": {
        "name": "Rain",
        "char": WEATHER_SPRITES["rain"],
        "color": COLORS["water_fg"],
        "applies_wetness": True,
        "extinguishes_fires": True,
        "slows_movement": False,
        "seasons": ["Spring", "Autumn"],
    },
    "snow": {
        "name": "Snow",
        "char": WEATHER_SPRITES["snow"],
        "color": (255, 255, 255),
        "applies_wetness": True,
        "extinguishes_fires": True,
        "slows_movement": True,
        "seasons": ["Winter"],
    },
}
