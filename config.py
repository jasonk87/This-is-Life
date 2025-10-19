# config.py

# World Generation
WORLD_WIDTH = 200
WORLD_HEIGHT = 200
POI_DENSITY = 0.1
CHUNK_SIZE = 16

# Noise parameters for world generation
NOISE_SCALE = 0.05
NOISE_OCTAVES = 4
NOISE_PERSISTENCE = 0.5
NOISE_LACUNARITY = 2.0

# Elevation constants
ELEVATION_DEEP_WATER = -0.5
ELEVATION_WATER = -0.2
ELEVATION_MOUNTAIN = 0.6
ELEVATION_SNOW = 0.8

# AI and Scheduling
USE_LLM_FOR_SCHEDULES = False
DAY_LENGTH_TICKS = 24000
NPC_SCHEDULE_UPDATE_INTERVAL = 100
WORK_START_TIME_RATIO = 0.3
WORK_END_TIME_RATIO = 0.7

# Lighting and FOV
LIGHT_LEVEL_PERIODS = [
    {"name": "PITCH_BLACK", "start_ratio": 0.0, "fov_config_key": "FOV_RADIUS_PITCH_BLACK"},
    {"name": "DAWN", "start_ratio": 0.23, "fov_config_key": "FOV_RADIUS_DUSK_DAWN"},
    {"name": "DAY", "start_ratio": 0.28, "fov_config_key": "FOV_RADIUS_DAY"},
    {"name": "DUSK", "start_ratio": 0.75, "fov_config_key": "FOV_RADIUS_DUSK_DAWN"},
    {"name": "NIGHT", "start_ratio": 0.80, "fov_config_key": "FOV_RADIUS_NIGHT"},
    {"name": "PITCH_BLACK", "start_ratio": 0.95, "fov_config_key": "FOV_RADIUS_PITCH_BLACK"},
]
FOV_RADIUS_DAY = 12
FOV_RADIUS_DUSK_DAWN = 8
FOV_RADIUS_NIGHT = 5
FOV_RADIUS_PITCH_BLACK = 2

# Audio
DEFAULT_HEARING_RADIUS = 15
DEFAULT_SPEECH_VOLUME = 10
