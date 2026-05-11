"""
Ecology simulation module.

Tracks regional resources and persistent wildlife populations. Regional
populations are the source of truth; nearby animal entities are local,
physical manifestations of that population.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Any


WILDLIFE_SPECIES: dict[str, dict[str, Any]] = {
    "deer": {
        "base_population": {"plains": 34, "forest": 48, "mountain": 10},
        "preferred_biomes": {"plains", "forest"},
        "preferred_tiles": {"Plains", "Tall Grass", "Flower", "Forest", "Sapling"},
        "recovery_rate": 2,
        "migration_pressure": 0.08,
        "density_divisor": 14,
        "max_visible_per_region": 8,
        "max_visible_per_chunk": 4,
        "group_size": (1, 3),
    },
    "rabbit": {
        "base_population": {"plains": 60, "forest": 30},
        "preferred_biomes": {"plains", "forest"},
        "preferred_tiles": {"Plains", "Tall Grass", "Flower", "Sapling"},
        "recovery_rate": 4,
        "migration_pressure": 0.12,
        "density_divisor": 18,
        "max_visible_per_region": 10,
        "max_visible_per_chunk": 5,
        "group_size": (1, 2),
    },
    "turkey": {
        "base_population": {"plains": 22, "forest": 30},
        "preferred_biomes": {"plains", "forest"},
        "preferred_tiles": {"Plains", "Tall Grass", "Flower", "Forest"},
        "recovery_rate": 2,
        "migration_pressure": 0.06,
        "density_divisor": 16,
        "max_visible_per_region": 6,
        "max_visible_per_chunk": 3,
        "group_size": (1, 3),
    },
    "wolf": {
        "base_population": {"plains": 8, "forest": 16, "mountain": 18},
        "preferred_biomes": {"plains", "forest", "mountain"},
        "preferred_tiles": {"Plains", "Tall Grass", "Forest", "Mountain", "Sapling"},
        "recovery_rate": 1,
        "migration_pressure": 0.04,
        "density_divisor": 10,
        "max_visible_per_region": 4,
        "max_visible_per_chunk": 2,
        "group_size": (1, 2),
    },
}


@dataclass
class RegionalWildlifePopulation:
    region_id: str
    species_key: str
    population_count: int
    carrying_capacity: int
    preferred_biomes: set[str] = field(default_factory=set)
    preferred_terrain_tags: set[str] = field(default_factory=set)
    spawn_pressure: float = 0.0
    migration_pressure: float = 0.0
    reproduction_rate: int = 1
    local_activity_density: float = 0.0
    visible_entity_ids: set[int] = field(default_factory=set)
    last_recovery_tick: int = 0

    def refresh_pressure(self, visible_count: int = 0) -> None:
        if self.carrying_capacity <= 0:
            self.spawn_pressure = 0.0
            self.local_activity_density = 0.0
            return
        self.spawn_pressure = max(0.0, min(1.0, self.population_count / self.carrying_capacity))
        self.local_activity_density = max(0.0, min(1.0, visible_count / max(1, self.population_count)))


class EcologySystem:
    def __init__(self):
        # Maps region_id -> resource_dict
        self.regional_resources: dict[str, dict[str, int]] = {}
        # Maps region_id -> species_key -> RegionalWildlifePopulation
        self.regional_wildlife: dict[str, dict[str, RegionalWildlifePopulation]] = {}

    def _initialize_region(self, region):
        """Set up initial resources based on the region's biome."""
        resources = {"wood": 0, "forage": 0, "game": 0}

        biome = getattr(region, "primary_biome", "plains")
        if biome == "forest":
            resources["wood"] = 1000
            resources["forage"] = 500
            resources["game"] = 200
        elif biome == "plains":
            resources["wood"] = 100
            resources["forage"] = 800
            resources["game"] = 100
        elif biome in {"mountain", "mountains"}:
            resources["wood"] = 200
            resources["forage"] = 100
            resources["game"] = 50

        self.regional_resources[region.id] = resources
        self.ensure_region_wildlife(region)

    def ensure_region_wildlife(self, region) -> dict[str, RegionalWildlifePopulation]:
        """Create persistent wildlife populations for a region if missing."""
        if region is None:
            return {}
        region_populations = self.regional_wildlife.setdefault(region.id, {})
        biome = getattr(region, "primary_biome", "plains")
        for species_key, species_def in WILDLIFE_SPECIES.items():
            if species_key in region_populations:
                continue
            base_by_biome = species_def.get("base_population", {})
            base_count = int(base_by_biome.get(biome, 0))
            if base_count <= 0:
                continue
            carrying_capacity = max(base_count, int(base_count * 1.5))
            population = RegionalWildlifePopulation(
                region_id=region.id,
                species_key=species_key,
                population_count=base_count,
                carrying_capacity=carrying_capacity,
                preferred_biomes=set(species_def.get("preferred_biomes", set())),
                preferred_terrain_tags=set(species_def.get("preferred_tiles", set())),
                migration_pressure=float(species_def.get("migration_pressure", 0.0)),
                reproduction_rate=int(species_def.get("recovery_rate", 1)),
            )
            population.refresh_pressure()
            region_populations[species_key] = population
        return region_populations

    def get_region_populations(self, world, region_id: str | None) -> dict[str, RegionalWildlifePopulation]:
        if not region_id:
            return {}
        region = getattr(getattr(world, "atlas", None), "regions_by_id", {}).get(region_id)
        if region is not None:
            return self.ensure_region_wildlife(region)
        return self.regional_wildlife.setdefault(region_id, {})

    def get_population(self, world, region_id: str | None, species_key: str) -> RegionalWildlifePopulation | None:
        return self.get_region_populations(world, region_id).get(species_key)

    def count_visible_wildlife(self, world, region_id: str | None = None, species_key: str | None = None, *, chunk_coords: tuple[int, int] | None = None) -> int:
        from entities.animal import Animal

        count = 0
        for animal in getattr(world, "npcs", []):
            if not isinstance(animal, Animal) or getattr(getattr(animal, "physical", None), "is_dead", False):
                continue
            if region_id is not None and getattr(animal, "wildlife_region_id", None) != region_id:
                continue
            if species_key is not None and getattr(animal, "animal_type", None) != species_key:
                continue
            if chunk_coords is not None and world.get_chunk_coords(getattr(animal, "x", 0), getattr(animal, "y", 0)) != chunk_coords:
                continue
            count += 1
        return count

    def target_visible_count(self, population: RegionalWildlifePopulation) -> int:
        species_def = WILDLIFE_SPECIES.get(population.species_key, {})
        divisor = max(1, int(species_def.get("density_divisor", 16)))
        max_visible = int(species_def.get("max_visible_per_region", 6))
        target = max(0, population.population_count // divisor)
        if population.population_count > 0 and target == 0:
            target = 1
        return min(max_visible, target)

    def note_animal_death(self, animal) -> None:
        """Reduce regional population when a manifested wild animal dies."""
        if getattr(animal, "ecology_death_recorded", False):
            return
        region_id = getattr(animal, "wildlife_region_id", None)
        species_key = getattr(animal, "animal_type", None)
        population = self.regional_wildlife.get(region_id, {}).get(species_key)
        if population is None:
            return
        population.population_count = max(0, population.population_count - 1)
        population.visible_entity_ids.discard(getattr(animal, "id", None))
        population.refresh_pressure()
        animal.ecology_death_recorded = True

    def _recover_wildlife_populations(self, world) -> None:
        # Slow abstract recovery: sparse populations recover gradually, never above carrying capacity.
        if getattr(world, "game_time", 0) % 1000 != 0:
            return
        for region_populations in self.regional_wildlife.values():
            for population in region_populations.values():
                if population.population_count >= population.carrying_capacity:
                    population.refresh_pressure()
                    continue
                recovery = max(1, population.reproduction_rate)
                if population.population_count < population.carrying_capacity // 3:
                    # Very sparse regions recover, but visibly and mechanically remain sparse for a while.
                    recovery = max(1, recovery // 2)
                population.population_count = min(population.carrying_capacity, population.population_count + recovery)
                population.last_recovery_tick = getattr(world, "game_time", 0)
                population.refresh_pressure()

    def get_resource_availability(self, world, region_id: str, resource_type: str) -> int:
        if region_id not in self.regional_resources:
            if hasattr(world, "atlas") and region_id in world.atlas.regions_by_id:
                self._initialize_region(world.atlas.regions_by_id[region_id])
            else:
                return 0
        return self.regional_resources[region_id].get(resource_type, 0)

    def consume_resource(self, world, region_id: str, resource_type: str, amount: int) -> int:
        """Attempt to consume a resource. Returns the actual amount consumed."""
        if region_id not in self.regional_resources:
            if hasattr(world, "atlas") and region_id in world.atlas.regions_by_id:
                self._initialize_region(world.atlas.regions_by_id[region_id])
            else:
                return 0

        available = self.regional_resources[region_id].get(resource_type, 0)
        consumed = min(available, amount)
        self.regional_resources[region_id][resource_type] -= consumed
        return consumed

    def process_tick(self, world) -> None:
        """Handle abstract regeneration of resources and wildlife over time."""
        for region in getattr(getattr(world, "atlas", None), "regions_by_id", {}).values():
            self.ensure_region_wildlife(region)

        if world.game_time % 1000 == 0:
            for region_id, resources in self.regional_resources.items():
                resources["wood"] += 5
                resources["forage"] += 10
                resources["game"] += 2
                resources["wood"] = min(resources["wood"], 2000)
                resources["forage"] = min(resources["forage"], 1000)
                resources["game"] = min(resources["game"], 500)
        self._recover_wildlife_populations(world)
