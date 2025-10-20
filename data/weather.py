# data/weather.py

WEATHER_TYPES = {
    "clear": {
        "name": "Clear",
        "color_modifier": {"plains": (0, 0, 0), "road": (0, 0, 0)}, # No change
        "transitions": {
            "clear": 0.8,
            "cloudy": 0.15,
            "rain": 0.05
        },
        "min_duration": 1000,
        "max_duration": 5000
    },
    "cloudy": {
        "name": "Cloudy",
        "color_modifier": {"plains": (-20, -20, -10), "road": (-10, -10, -10)}, # Darken slightly
        "transitions": {
            "clear": 0.6,
            "cloudy": 0.2,
            "rain": 0.2
        },
        "min_duration": 500,
        "max_duration": 2000
    },
    "rain": {
        "name": "Rain",
        "color_modifier": {"plains": (-40, -40, -20), "road": (-20, -20, -20)}, # Darken more and add blueish tint
        "transitions": {
            "cloudy": 0.7,
            "rain": 0.3
        },
        "min_duration": 800,
        "max_duration": 2500
    }
}
