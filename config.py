# config.py
import os

# Screen dimensions
SCREEN_WIDTH = 100
SCREEN_HEIGHT = 56
MAP_WIDTH = 78
MAP_HEIGHT = 50
STATUS_PANEL_WIDTH = SCREEN_WIDTH - MAP_WIDTH
MINIMAP_WIDTH = STATUS_PANEL_WIDTH
MINIMAP_HEIGHT = 13
MINIMAP_X = MAP_WIDTH
MINIMAP_Y = 1
TILE_SIZE = 16
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1040
SCREEN_WIDTH_TILES = SCREEN_WIDTH
SCREEN_HEIGHT_TILES = SCREEN_HEIGHT

# World generation
WORLD_WIDTH_CHUNKS = 10
WORLD_HEIGHT_CHUNKS = 10
CHUNK_WIDTH = 60
CHUNK_HEIGHT = 40
CHUNK_SIZE = 40
WORLD_WIDTH = WORLD_WIDTH_CHUNKS * CHUNK_WIDTH
WORLD_HEIGHT = WORLD_HEIGHT_CHUNKS * CHUNK_HEIGHT
POI_DENSITY = 0.3
# Noise settings for world generation
NOISE_SCALE = 0.1
NOISE_OCTAVES = 4
NOISE_PERSISTENCE = 0.5
NOISE_LACUNARITY = 2.0
# Elevation constants
ELEVATION_DEEP_WATER = -0.5
ELEVATION_WATER = -0.2
ELEVATION_MOUNTAIN = 0.6
ELEVATION_SNOW = 0.8


# Simulation settings
VILLAGE_SPAWN_ATTEMPTS = 50
VILLAGE_MIN_DISTANCE_CHUNKS = 3
MAX_VILLAGES = 5
NPC_SPAWN_ATTEMPTS_PER_VILLAGE = 20
MAX_NPCS_PER_VILLAGE = 15
TRAVELING_MERCHANT_SPAWN_CHANCE = 0.1
ABSTRACT_SIMULATION_DISTANCE_CHUNKS = 3
NPC_SCHEDULE_UPDATE_INTERVAL = 10 # Number of game ticks between NPC schedule updates
USE_LLM_FOR_SCHEDULES = False
DAY_LENGTH_TICKS = 14400
WORK_START_TIME_RATIO = 0.333 # 8 AM
WORK_END_TIME_RATIO = 0.708 # 5 PM

# Gameplay settings
DEFAULT_SPEECH_VOLUME = 8
DEFAULT_HEARING_RADIUS = 12
FOV_RADIUS = 15
PLAYER_BASE_SPEED = 1
ANIMAL_BASE_SPEED = 1
BASE_ATTACK_SPEED = 100 # in game ticks
BASE_PICK_LOCK_SPEED = 300 # in game ticks
BASE_BUTCHER_SPEED = 200 # in game ticks
BASE_FISHING_SPEED = 400 # in game ticks
BASE_TAMING_CHANCE = 0.2
HOURS_PER_DAY = 24
MINUTES_PER_HOUR = 60
SECONDS_PER_MINUTE = 60
GAME_TICKS_PER_SECOND = 10
SECONDS_PER_GAME_TICK = 1 / GAME_TICKS_PER_SECOND
TIME_PER_TICK = (HOURS_PER_DAY * MINUTES_PER_HOUR * SECONDS_PER_MINUTE) / (GAME_TICKS_PER_SECOND * 60 * 24) # Placeholder for more complex time system
INITIAL_TIME_OF_DAY = 8 * 60 # 8:00 AM

# FOV and Light Level
FOV_RADIUS_DAY = 15
FOV_RADIUS_DUSK_DAWN = 12
FOV_RADIUS_NIGHT = 8
FOV_RADIUS_PITCH_BLACK = 5

LIGHT_LEVEL_PERIODS = [
    {"name": "PITCH BLACK", "start_ratio": 0.0, "fov_config_key": "FOV_RADIUS_PITCH_BLACK"},
    {"name": "DAWN", "start_ratio": 0.25, "fov_config_key": "FOV_RADIUS_DUSK_DAWN"},
    {"name": "DAY", "start_ratio": 0.3, "fov_config_key": "FOV_RADIUS_DAY"},
    {"name": "DUSK", "start_ratio": 0.7, "fov_config_key": "FOV_RADIUS_DUSK_DAWN"},
    {"name": "NIGHT", "start_ratio": 0.8, "fov_config_key": "FOV_RADIUS_NIGHT"},
    {"name": "PITCH BLACK", "start_ratio": 0.95, "fov_config_key": "FOV_RADIUS_PITCH_BLACK"}
]

# Controls
KEY_UP = 'w'
KEY_DOWN = 's'
KEY_LEFT = 'a'
KEY_RIGHT = 'd'
KEY_INTERACT = 'e'
KEY_WAIT = 'space'
KEY_INFO_MENU = 'i'
KEY_KNOWLEDGE_MENU = 'k'
KEY_CRAFTING_MENU = 'c'
KEY_EXAMINE = 'x'
KEY_ESCAPE = 'escape'

# Display
TILESET_PATH = "assets/tileset.png"
# TILE_SIZE and DOUBLE_TILE_SIZE are removed as they are duplicates

# Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_RED = (255, 0, 0)
COLOR_GREEN = (0, 255, 0)
COLOR_BLUE = (0, 0, 255)
COLOR_YELLOW = (255, 255, 0)
COLOR_ORANGE = (255, 165, 0)
COLOR_PURPLE = (128, 0, 128)
COLOR_CYAN = (0, 255, 255)
COLOR_GREY = (128, 128, 128)
COLOR_LIGHT_GREY = (192, 192, 192)
COLOR_DARK_GREY = (64, 64, 64)
COLOR_PLAYER_STATUS_WET = (0, 100, 255)
COLOR_PLAYER_STATUS_FREEZING = (100, 100, 255)
COLOR_CURSOR_INFO_TEXT = (200, 200, 200)

# Factions
FACTION_COMMON_FOLK = "common_folk"
FACTION_MERCHANTS_GUILD = "merchants_guild"
FACTION_LAW_AND_ORDER = "law_and_order"

# Reputation
INITIAL_CRIMINAL_POINTS = 0
INITIAL_HERO_POINTS = 0
REP_CRIMINAL = "criminal"
REP_HERO = "hero"

# Seasons and Temperature
DAYS_PER_SEASON = 28
SEASON_TEMPERATURE_MODIFIERS = {
    "Spring": 15, "Summer": 25, "Autumn": 10, "Winter": -5
}
BIOME_TEMPERATURE_MODIFIERS = {
    "plains": 0, "forest": -2, "mountain": -8, "snow": -15, "desert": 10
}
TIME_OF_DAY_TEMPERATURE_MODIFIERS = {
    "PITCH BLACK": -10, "DAWN": -5, "DAY": 0, "DUSK": -5, "NIGHT": -8, "DEEP_NIGHT": -10
}

# LLM settings
import json
ENABLE_LLM_CONNECTION = True # Master switch to enable/disable LLM connection
ENABLE_OLLAMA_CONNECTION = ENABLE_LLM_CONNECTION # Legacy support
LLM_BACKEND = "gemini" # Options: "ollama", "gemini"

GOOGLE_API_KEY = ""

# Try loading from python config file first (preferred)
try:
    from llm_config import GOOGLE_API_KEY as FILE_KEY
    if FILE_KEY and "PASTE_YOUR" not in FILE_KEY:
        GOOGLE_API_KEY = FILE_KEY
except ImportError:
    pass

# Fallback to keys.json (legacy)
if not GOOGLE_API_KEY:
    try:
        with open("keys.json", "r") as f:
            keys = json.load(f)
            GOOGLE_API_KEY = keys.get("GOOGLE_API_KEY", "")
    except FileNotFoundError:
        pass

# Fallback to environment variable
if not GOOGLE_API_KEY:
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
