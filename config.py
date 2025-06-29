# game/config.py

# --- World Settings ---
WORLD_WIDTH = 200  # in tiles
WORLD_HEIGHT = 200 # in tiles
CHUNK_SIZE = 20    # in tiles

# --- POI Settings ---
POI_DENSITY = 0.05 # Likelihood of a POI in a suitable chunk

# --- Display Settings ---
SCREEN_WIDTH_TILES = 80
SCREEN_HEIGHT_TILES = 50

# --- World Generation Settings ---
NOISE_SCALE = 0.05       # Smaller values -> larger features
NOISE_OCTAVES = 4        # Adds more detail to the noise
NOISE_PERSISTENCE = 0.5  # Controls how much detail is added each octave
NOISE_LACUNARITY = 2.0   # Controls how much finer the detail is each octave
ELEVATION_DEEP_WATER = 0.2
ELEVATION_WATER = 0.35
ELEVATION_MOUNTAIN = 0.8
ELEVATION_SNOW = 0.9

# --- NPC Scheduling Settings ---
USE_LLM_FOR_SCHEDULES = True  # Set to False to use simple rule-based scheduler
DAY_LENGTH_TICKS = 1500       # How many game ticks constitute a full day-night cycle
NPC_SCHEDULE_UPDATE_INTERVAL = 50 # How often an NPC re-evaluates its schedule (in ticks)
# Example time definitions within a day (as fraction of DAY_LENGTH_TICKS)
WORK_START_TIME_RATIO = 0.25 # e.g., 25% into the day
WORK_END_TIME_RATIO = 0.70   # e.g., 70% into the day

# --- Reputation Settings ---
# Initial values for player reputation
INITIAL_CRIMINAL_POINTS = 0
INITIAL_HERO_POINTS = 0

# Define keys for reputation types for consistency
REP_CRIMINAL = "criminal_points"
REP_HERO = "hero_points"

# Optional: Define ranges or thresholds, though enforcement is in game logic
# REP_MIN_VALUE = -100
# REP_MAX_VALUE = 100

# --- Field of View & Light Levels ---
FOV_RADIUS_DAY = 20
FOV_RADIUS_DUSK_DAWN = 12
FOV_RADIUS_NIGHT = 7
FOV_RADIUS_PITCH_BLACK = 4 # For very dark conditions, like unlit caves or deep night

# Define periods of the day based on DAY_LENGTH_TICKS ratio
# These are start ratios for each period. Order matters for lookup.
# The values are the FOV radius config key string to be used for this period.
# A function in engine.py will determine current period based on these.
# Example: DAY_LENGTH_TICKS = 1500
#   0.0 - 0.20 (0-299): NIGHT (uses FOV_RADIUS_NIGHT)
#   0.20 - 0.25 (300-374): DAWN (uses FOV_RADIUS_DUSK_DAWN)
#   0.25 - 0.75 (375-1124): DAY (uses FOV_RADIUS_DAY)
#   0.75 - 0.85 (1125-1274): DUSK (uses FOV_RADIUS_DUSK_DAWN)
#   0.85 - 1.0 (1275-1499): NIGHT (uses FOV_RADIUS_NIGHT)

LIGHT_LEVEL_PERIODS = [ # Must be sorted by start_ratio
    {"start_ratio": 0.0,  "name": "DEEP_NIGHT", "fov_config_key": "FOV_RADIUS_NIGHT"}, # Until dawn's first light
    {"start_ratio": 0.22, "name": "DAWN",       "fov_config_key": "FOV_RADIUS_DUSK_DAWN"},
    {"start_ratio": 0.28, "name": "DAY",        "fov_config_key": "FOV_RADIUS_DAY"},
    {"start_ratio": 0.72, "name": "DUSK",       "fov_config_key": "FOV_RADIUS_DUSK_DAWN"},
    {"start_ratio": 0.78, "name": "NIGHT",      "fov_config_key": "FOV_RADIUS_NIGHT"} # Evening fading to night
    # The period from last entry (0.78) to 1.0 will use FOV_RADIUS_NIGHT
]

# Make sure DAY_LENGTH_TICKS is defined (it's in NPC Scheduling Settings, imported above)
# For example, if DAY_LENGTH_TICKS = 1000:
# DEEP_NIGHT: 0-219
# DAWN: 220-279
# DAY: 280-719
# DUSK: 720-779
# NIGHT: 780-999

# --- Auditory Perception Settings ---
DEFAULT_HEARING_RADIUS = 12 # How far the player can hear standard volume speech.
DEFAULT_SPEECH_VOLUME = 10  # How far standard NPC speech travels.
# Speech is heard if distance <= player.hearing_radius AND distance <= npc.speech_volume.
