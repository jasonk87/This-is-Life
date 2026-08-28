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
        self.random = random.Random(seed)
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
        self.village_coords = self._select_village_coords()

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

    # Biomes settlements may be founded on, best first. Plains is the
    # intended home for a village; the rest are fallbacks used only when a
    # map doesn't offer enough plains. Water is never habitable.
    HABITABLE_BIOMES = ("plains", "mountain", "snow")

    def _candidate_village_coords(self, biomes) -> list[tuple[int, int]]:
        """Inland chunks whose biome is in `biomes`.

        Border chunks are excluded so a village always has room to generate
        its surroundings.
        """
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.get_biome_at(x, y) in biomes
            and 1 <= x < self.width - 1
            and 1 <= y < self.height - 1
        ]

    def _select_village_coords(self) -> set[tuple[int, int]]:
        # Widen the search to less hospitable land rather than returning no
        # villages at all. Restricting candidates to plains meant a map that
        # generated mostly ocean produced a world with zero settlements -
        # no NPCs, no quests, no economy, nothing to do - and that happened
        # for roughly one seed in thirteen. Plains are still strongly
        # preferred: the fallback only contributes when plains alone can't
        # supply the target count.
        candidates = self._candidate_village_coords(("plains",))
        self.random.shuffle(candidates)
        if len(candidates) < 3:
            fallback = self._candidate_village_coords(self.HABITABLE_BIOMES)
            self.random.shuffle(fallback)
            seen = set(candidates)
            candidates.extend(coord for coord in fallback if coord not in seen)

        if not candidates:
            return set()
        target_count = min(4, max(3, len(candidates)))
        selected: list[tuple[int, int]] = []
        min_spacing = max(3, min(self.width, self.height) // 3)

        def is_far_enough(candidate: tuple[int, int], spacing: int) -> bool:
            return all(abs(candidate[0] - other[0]) + abs(candidate[1] - other[1]) >= spacing for other in selected)

        spacing = min_spacing
        while spacing >= 1 and len(selected) < target_count:
            selected.clear()
            for candidate in candidates:
                if is_far_enough(candidate, spacing):
                    selected.append(candidate)
                if len(selected) >= target_count:
                    break
            spacing -= 1
        return set(selected[:target_count])

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
        if (x, y) in self.village_coords:
            return "village"
        if biome == "plains":
            coord_rng = random.Random(str((self.seed, x, y)))
            if coord_rng.random() < POI_DENSITY / 8:
                return "ruin"
        elif biome == "mountain":
            coord_rng = random.Random(str((self.seed, x, y, "mountain")))
            if coord_rng.random() < POI_DENSITY / 3:
                return "ruin"
        return None
