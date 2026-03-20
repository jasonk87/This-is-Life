"""World generation utilities extracted from the engine module."""

from __future__ import annotations

import random

from config import (
    ELEVATION_DEEP_WATER,
    ELEVATION_MOUNTAIN,
    ELEVATION_SNOW,
    ELEVATION_WATER,
    NOISE_LACUNARITY,
    NOISE_OCTAVES,
    NOISE_PERSISTENCE,
    NOISE_SCALE,
    POI_DENSITY,
)
from runtime_compat import np
from tcod_compat import tcod


class WorldGenerator:
    """Handles the procedural generation of the world's macro-structure."""

    def __init__(self, width, height, seed=None):
        self.width = width
        self.height = height
        self.seed = seed
        self.noise = tcod.noise.Noise(
            dimensions=2,
            algorithm=tcod.noise.Algorithm.SIMPLEX,
            implementation=tcod.noise.Implementation.SIMPLE,
            hurst=NOISE_PERSISTENCE,
            lacunarity=NOISE_LACUNARITY,
            octaves=NOISE_OCTAVES,
            seed=seed,
        )
        self.elevation_map = self._generate_noise_map()

    def __getstate__(self):
        """Exclude tcod noise objects from pickled save data."""
        state = self.__dict__.copy()
        state["noise"] = None
        return state

    def __setstate__(self, state):
        """Restore tcod noise objects after loading a save."""
        self.__dict__.update(state)
        self.noise = tcod.noise.Noise(
            dimensions=2,
            algorithm=tcod.noise.Algorithm.SIMPLEX,
            implementation=tcod.noise.Implementation.SIMPLE,
            hurst=NOISE_PERSISTENCE,
            lacunarity=NOISE_LACUNARITY,
            octaves=NOISE_OCTAVES,
            seed=self.seed,
        )

    def _generate_noise_map(self):
        noise_map = np.zeros((self.height, self.width), dtype=np.float32)
        for y in range(self.height):
            for x in range(self.width):
                noise_map[y, x] = self.noise[x * NOISE_SCALE, y * NOISE_SCALE].item()
        return noise_map

    def get_biome_at(self, x, y):
        """Determines the biome for a given CHUNK coordinate based on elevation."""
        elevation = self.elevation_map[y, x]
        if elevation < ELEVATION_DEEP_WATER:
            return "deep_water"
        if elevation < ELEVATION_WATER:
            return "water"
        if elevation < ELEVATION_MOUNTAIN:
            return "plains"
        if elevation < ELEVATION_SNOW:
            return "mountain"
        return "snow"

    def get_poi_at(self, x, y, biome):
        """Determines if a POI should be placed at a chunk coordinate."""
        if biome == "plains":
            if random.random() < POI_DENSITY:
                return "village"
            if random.random() < POI_DENSITY / 4:
                return "ruin"
        elif biome == "mountain":
            if random.random() < POI_DENSITY / 3:
                return "ruin"
        return None
