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
        # Predator-prey link (see _recover_wildlife_populations): wolves are
        # the only predator species currently modeled, so this is the only
        # entry with a "prey_species" key. Anything without this key is
        # treated as having no prey dependency and recovers exactly as
        # before this change.
        "prey_species": ("deer", "rabbit", "turkey"),
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

    def _prey_availability_ratio(self, region_populations: dict[str, "RegionalWildlifePopulation"], species_key: str) -> float | None:
        """
        Returns how well-fed a predator species' prey base is in this region,
        as population/carrying_capacity summed across its configured prey
        species, or None if this species has no prey dependency (i.e. it
        isn't a predator - every non-wolf species today).

        Missing prey species (e.g. no "rabbit" entry in a mountain-only
        region) are skipped rather than counted as zero-availability, so a
        predator isn't penalized just because one of its several prey types
        doesn't exist in that biome. If NONE of a predator's prey species
        have trackable data in this region at all, this conservatively
        returns 1.0 (no penalty) rather than starving the predator based on
        missing data instead of an actual scarcity signal.
        """
        species_def = WILDLIFE_SPECIES.get(species_key, {})
        prey_keys = species_def.get("prey_species")
        if not prey_keys:
            return None

        total_prey_population = 0
        total_prey_capacity = 0
        for prey_key in prey_keys:
            prey_population = region_populations.get(prey_key)
            if prey_population is None:
                continue
            total_prey_population += max(0, prey_population.population_count)
            total_prey_capacity += max(0, prey_population.carrying_capacity)

        if total_prey_capacity <= 0:
            return 1.0
        return total_prey_population / total_prey_capacity

    def _predator_pressure_ratio(self, region_populations: dict[str, "RegionalWildlifePopulation"], species_key: str) -> float | None:
        """
        Reciprocal of _prey_availability_ratio: returns how much predator
        pressure a PREY species is under in this region, as the highest
        population/carrying_capacity ("how full is the predator's own
        capacity") among predator species that list species_key in their
        prey_species, or None if no known predator preys on this species
        (every non-prey species today, and predators w.r.t. their own
        predators - nothing preys on wolves).

        Closes the gap flagged separately from the predator-side balance
        pass above: that pass only ever constrained a PREDATOR's growth
        based on prey scarcity, never the reverse. Missing predator
        population data is skipped (not treated as zero pressure), matching
        _prey_availability_ratio's same "don't penalize based on absent
        data" stance.
        """
        predator_pressures = []
        for predator_key, predator_def in WILDLIFE_SPECIES.items():
            prey_keys = predator_def.get("prey_species")
            if not prey_keys or species_key not in prey_keys:
                continue
            predator_population = region_populations.get(predator_key)
            if predator_population is None or predator_population.carrying_capacity <= 0:
                continue
            predator_pressures.append(
                max(0, predator_population.population_count) / predator_population.carrying_capacity
            )

        if not predator_pressures:
            return None
        return max(predator_pressures)

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

                # --- Predator-prey balance (new) ---
                # Conservative, deliberately narrow first pass: this only
                # constrains a PREDATOR's own growth toward ITS carrying
                # capacity when its prey is scarce. It does NOT touch prey
                # population math at all (real predation already reduces prey
                # counts through actual hunt/kill events via note_animal_death
                # - adding a second, abstract prey-decrement here would double
                # count that and was deliberately left out). It also never
                # actively reduces an existing predator population (no
                # starvation die-off) - worst case for a predator with no
                # prey is simply zero growth that cycle, not a population
                # crash. Both omissions are intentional scope limits for this
                # pass, flagged for Jason to sanity check the tuning:
                # - Below full prey availability, growth is granted
                #   probabilistically in proportion to the prey ratio
                #   (e.g. prey at 50% of capacity -> ~50% chance this cycle's
                #   recovery is applied, otherwise 0) rather than scaling the
                #   integer recovery amount down and truncating it - wolf's
                #   baseline recovery_rate is already 1, so truncating a
                #   fractional multiplier would silently zero out ALL growth
                #   any time prey wasn't at exactly full capacity, which is a
                #   much harsher constraint than "growth constrained by prey
                #   availability" was meant to imply.
                prey_availability_ratio = self._prey_availability_ratio(region_populations, population.species_key)
                if prey_availability_ratio is not None:
                    growth_chance = min(1.0, max(0.0, prey_availability_ratio))
                    if random.random() >= growth_chance:
                        recovery = 0

                # --- Predator-prey balance (prey side, reciprocal) ---
                # Mirrors the predator-side block above but inverted: when
                # predator pressure (e.g. wolves relative to THEIR OWN
                # carrying capacity) is high in this region, a PREY
                # species's recovery is throttled too, using the exact same
                # "growth is granted probabilistically, never actively
                # reduced" idiom - no prey species population is ever
                # decremented here, only its recovery chance this cycle.
                # Real predation already removes prey through actual
                # hunt/kill events (note_animal_death); this only makes
                # abstract recovery slower while predators are numerous,
                # it doesn't add a second abstract die-off on top of that.
                # If recovery was already zeroed by some other check above,
                # skip the (harmless but pointless) extra roll.
                if recovery > 0:
                    predator_pressure_ratio = self._predator_pressure_ratio(region_populations, population.species_key)
                    if predator_pressure_ratio is not None:
                        growth_chance = min(1.0, max(0.0, 1.0 - predator_pressure_ratio))
                        if random.random() >= growth_chance:
                            recovery = 0

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
