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
