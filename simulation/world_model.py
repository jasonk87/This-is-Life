from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import uuid


class Building:
    def __init__(self, x, y, width, height, building_type="house", category="residential", global_chunk_x_start=0, global_chunk_y_start=0):
        self.id = str(uuid.uuid4())
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.building_type = building_type
        self.category = category
        self.interior_decorated = False
        self.occupants = []
        self.residents = []
        self.building_inventory = {}
        self.interaction_points = {}
        self.work_zone_tiles: dict[str, list[tuple[int, int]]] = {}
        self.global_origin_x = global_chunk_x_start + x
        self.global_origin_y = global_chunk_y_start + y
        self.global_center_x = self.global_origin_x + width // 2
        self.global_center_y = self.global_origin_y + height // 2
        self.player_owned: bool = False
        self.max_workers: int = 2
        self.region_id: str | None = None
        self.settlement_id: str | None = None

    @property
    def max_workers(self):
        return getattr(self, "_max_workers", 2)

    @max_workers.setter
    def max_workers(self, value):
        self._max_workers = value

    def contains_global_coords(self, world_x: int, world_y: int) -> bool:
        return (
            self.global_origin_x <= world_x < self.global_origin_x + self.width
            and self.global_origin_y <= world_y < self.global_origin_y + self.height
        )


class Village:
    def __init__(self, primary_biome: str | None = None, chunk_coords: tuple[int, int] | None = None, region_id: str | None = None):
        self.id = str(uuid.uuid4())
        self.buildings = []
        self.lore = "No lore generated yet."
        self.interaction_points = {}
        self.supply = {}
        self.demand = {}
        self.local_events = []
        self.known_events = {}
        self.construction_projects = []
        self.village_relationships = {}
        self.at_war_with = set()
        self.population_cache = 0
        self.primary_biome = primary_biome
        self.chunk_coords = chunk_coords
        self.region_id = region_id
        self.history_record_ids: list[str] = []

    def add_building(self, building: Building):
        building.settlement_id = self.id
        building.region_id = self.region_id
        self.buildings.append(building)


class Ruin:
    def __init__(self, primary_biome: str | None = None, chunk_coords: tuple[int, int] | None = None, region_id: str | None = None):
        self.id = str(uuid.uuid4())
        self.lore = "The origins of this place are lost to time."
        self.primary_biome = primary_biome
        self.chunk_coords = chunk_coords
        self.region_id = region_id
        self.history_record_ids: list[str] = []


@dataclass
class Region:
    name: str
    primary_biome: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chunk_coords: set[tuple[int, int]] = field(default_factory=set)
    village_ids: set[str] = field(default_factory=set)
    ruin_ids: set[str] = field(default_factory=set)
    climate_profile: dict[str, Any] = field(default_factory=dict)
    resource_tags: set[str] = field(default_factory=set)
    lore_notes: list[str] = field(default_factory=list)

    def add_chunk(self, chunk_coords: tuple[int, int]):
        self.chunk_coords.add(chunk_coords)

    def add_village(self, village: Village):
        village.region_id = self.id
        self.village_ids.add(village.id)

    def add_ruin(self, ruin: Ruin):
        ruin.region_id = self.id
        self.ruin_ids.add(ruin.id)


class Chunk:
    def __init__(self, biome, poi_type=None, region_id: str | None = None):
        self.biome = biome
        self.poi_type = poi_type
        self.tiles = None
        self.is_generated = False
        self.is_terrain_generated = False
        self.village = None
        self.ruin = None
        self.region_id = region_id


class WorldAtlas:
    """Owns world geography, settlements, and building indexes."""

    def __init__(self):
        self.villages: list[Village] = []
        self.buildings_by_id: dict[str, Building] = {}
        self.regions_by_id: dict[str, Region] = {}
        self.region_by_chunk: dict[tuple[int, int], str] = {}
        self.ruins_by_id: dict[str, Ruin] = {}

    def create_region(self, name: str, primary_biome: str) -> Region:
        region = Region(name=name, primary_biome=primary_biome)
        self.regions_by_id[region.id] = region
        return region

    def get_region(self, region_id: str | None) -> Region | None:
        if not region_id:
            return None
        return self.regions_by_id.get(region_id)

    def get_region_for_chunk(self, chunk_x: int, chunk_y: int) -> Region | None:
        region_id = self.region_by_chunk.get((chunk_x, chunk_y))
        return self.get_region(region_id)

    def get_region_for_world_coords(self, world_x: int, world_y: int, chunk_size: int) -> Region | None:
        return self.get_region_for_chunk(world_x // chunk_size, world_y // chunk_size)

    def get_or_create_region_for_chunk(self, chunk_x: int, chunk_y: int, biome: str) -> Region:
        existing = self.get_region_for_chunk(chunk_x, chunk_y)
        if existing is not None:
            return existing
        region = self.create_region(name=f"{biome.title()} Region {chunk_x},{chunk_y}", primary_biome=biome)
        self.assign_chunk_to_region(chunk_x, chunk_y, region)
        return region

    def assign_chunk_to_region(self, chunk_x: int, chunk_y: int, region: Region):
        coords = (chunk_x, chunk_y)
        self.region_by_chunk[coords] = region.id
        region.add_chunk(coords)

    def add_village(self, village: Village, chunk_coords: tuple[int, int] | None = None, region: Region | None = None):
        if region is not None:
            region.add_village(village)
        if chunk_coords is not None:
            village.chunk_coords = chunk_coords
        self.villages.append(village)
        for building in village.buildings:
            self.register_building(building)
        return village

    def add_ruin(self, ruin: Ruin, chunk_coords: tuple[int, int] | None = None, region: Region | None = None):
        if region is not None:
            region.add_ruin(ruin)
        if chunk_coords is not None:
            ruin.chunk_coords = chunk_coords
        self.ruins_by_id[ruin.id] = ruin
        return ruin

    def register_building(self, building: Building):
        self.buildings_by_id[building.id] = building
        return building

    def get_building(self, building_id: str | None) -> Building | None:
        if not building_id:
            return None
        return self.buildings_by_id.get(building_id)
