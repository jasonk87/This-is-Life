# data/environment.py
from data.tiles import COLORS

WEATHER_TYPES = {
    "clear": {
        "char": " ",
        "color": (255, 255, 255),
        "chance": 0.0,
        "effects": {}
    },
    "rain": {
        "char": ".",
        "color": (170, 170, 220),
        "chance": 0.2,
        "effects": {
            "applies_wetness": True,
            "extinguishes_fires": True,
            "waters_crops": True,
            "temperature_modifier": -2.0  # Colder
        }
    },
    "snow": {
        "char": "*",
        "color": (220, 220, 220),
        "chance": 0.1,
        "effects": {
            "slows_movement": 1.5,  # 50% slower
            "extinguishes_fires": True,
            "temperature_modifier": -5.0  # Much colder
        }
    }
}
