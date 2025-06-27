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
