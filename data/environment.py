# data/environment.py

# A day is DAY_LENGTH_TICKS ticks long. Let's define season length in days.
SEASON_LENGTH_IN_DAYS = 20  # A shorter season for gameplay purposes

SEASONS = {
    "spring": {
        "name": "Spring",
        "duration_days": SEASON_LENGTH_IN_DAYS,
        "weather_probabilities": {
            "clear": 0.6,
            "rain": 0.3,
            "snow": 0.1,  # Lingering snow/cold snaps
        },
        "effects": {
            "tree_growth_modifier": 1.5,  # Faster growth
            "sapling_growth_modifier": 1.5,
        }
    },
    "summer": {
        "name": "Summer",
        "duration_days": SEASON_LENGTH_IN_DAYS,
        "weather_probabilities": {
            "clear": 0.8,
            "rain": 0.2,
            "snow": 0.0,
        },
        "effects": {
            "tree_growth_modifier": 1.0,
            "sapling_growth_modifier": 1.0,
        }
    },
    "autumn": {
        "name": "Autumn",
        "duration_days": SEASON_LENGTH_IN_DAYS,
        "weather_probabilities": {
            "clear": 0.5,
            "rain": 0.4,
            "snow": 0.1,  # Early snowfalls
        },
        "effects": {
            "tree_growth_modifier": 0.75, # Slower growth
            "sapling_growth_modifier": 0.75,
        }
    },
    "winter": {
        "name": "Winter",
        "duration_days": SEASON_LENGTH_IN_DAYS,
        "weather_probabilities": {
            "clear": 0.4,
            "rain": 0.1,
            "snow": 0.5,
        },
        "effects": {
            "tree_growth_modifier": 0.25, # Very slow growth
            "sapling_growth_modifier": 0.25,
        }
    }
}

# The order of seasons for cycling
SEASON_ORDER = ["spring", "summer", "autumn", "winter"]

WEATHER_TYPES = {
    "clear": {
        "name": "Clear",
        "overlay_char": " ",  # No visual effect for clear weather
        "overlay_color": (255, 255, 255) # Not used, but good to have
    },
    "rain": {
        "name": "Rain",
        "overlay_char": ".",
        "overlay_color": (100, 150, 255) # A blue color for rain
    },
    "snow": {
        "name": "Snow",
        "overlay_char": "*",
        "overlay_color": (200, 200, 200) # A light grey/white for snow
    }
}
