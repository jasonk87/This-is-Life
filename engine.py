# engine.py
import math
import random
import numpy as np
import tcod
from tcod import libtcodpy
import tcod.noise
import requests
import time
from entities.base import NPC, DireWolf # Added DireWolf
from entities.animal import Animal
from data.animals import ANIMAL_DEFINITIONS
from entities.tree import Tree, OakTree, AppleTree, PearTree # Tree classes seem partially defined/used.
from config import (
    WORLD_WIDTH, WORLD_HEIGHT, POI_DENSITY, CHUNK_SIZE,
    NOISE_SCALE, NOISE_OCTAVES, NOISE_PERSISTENCE, NOISE_LACUNARITY,
    ELEVATION_DEEP_WATER, ELEVATION_WATER, ELEVATION_MOUNTAIN, ELEVATION_SNOW,
    # NPC Scheduling Configs
    USE_LLM_FOR_SCHEDULES, DAY_LENGTH_TICKS, NPC_SCHEDULE_UPDATE_INTERVAL,
    WORK_START_TIME_RATIO, WORK_END_TIME_RATIO,
    # Reputation Configs
    INITIAL_CRIMINAL_POINTS, INITIAL_HERO_POINTS,
    REP_CRIMINAL, REP_HERO,
    # FOV and Light Level Configs
    DAY_LENGTH_TICKS, LIGHT_LEVEL_PERIODS,
    FOV_RADIUS_DAY, FOV_RADIUS_DUSK_DAWN, FOV_RADIUS_NIGHT, FOV_RADIUS_PITCH_BLACK,
    # Auditory Perception Configs
    DEFAULT_HEARING_RADIUS, DEFAULT_SPEECH_VOLUME,
    # Abstract Simulation Configs
    ABSTRACT_SIMULATION_DISTANCE_CHUNKS,
    # Season and Temperature Configs
    DAYS_PER_SEASON,
    SEASON_TEMPERATURE_MODIFIERS,
    BIOME_TEMPERATURE_MODIFIERS,
    TIME_OF_DAY_TEMPERATURE_MODIFIERS,
    ENABLE_OLLAMA_CONNECTION,
)
from data.tiles import TILE_DEFINITIONS, COLORS # For TILE_DEFINITIONS
from tile_types import Tile # For Tile class
from entities.tree import Tree # For isinstance check
from data.items import ITEM_DEFINITIONS # For checking yielded resources
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.prompts import LLM_PROMPTS, OLLAMA_ENDPOINT
from data.professions import PROFESSIONS, get_profession_data, get_sub_task_data
from data.decorations import DECORATION_ITEM_DEFINITIONS as ALL_DECORATION_DEFS
from tile_types import Tile as BaseTileType
from data.quests import QUEST_DEFINITIONS # Import quest definitions
from data.environment import WEATHER_DEFINITIONS
from data.construction import CONSTRUCTION_RECIPES

import json
import uuid

class Quest:
    """A class to represent an active quest."""
    def __init__(self, quest_id: str, title: str, description: str, quest_type: str, quest_giver_id: int):
        self.id = quest_id
        self.title = title
        self.description = description
        self.type = quest_type
        self.quest_giver_id = quest_giver_id
        self.progress = 0
        # For 'fetch' quests
        self.item_key: str | None = None
        self.required_count: int = 0
        # For 'kill' quests
        self.target_name_prefix: str | None = None
        self.required_kills: int = 0

class Book:
    """A class to represent a book written by a Scribe."""
    def __init__(self, title: str, author_id: int, author_name: str, year_written: int, content: str, book_type: str = "chronicle"):
        self.id = str(uuid.uuid4())
        self.title = title
        self.author_id = author_id
        self.author_name = author_name
        self.year_written = year_written
        self.content = content
        self.book_type = book_type # e.g., "chronicle", "census"

class Event:
    """A class to represent a significant event that occurs in the world."""
    def __init__(self, event_type: str, description: str, subject_id: int, game_time: int, target_id: int | None = None, location: tuple[int, int] | None = None):
        self.id = str(uuid.uuid4())
        self.type = event_type  # e.g., "combat_attack", "npc_death", "item_craft"
        self.description = description
        self.subject_id = subject_id  # The ID of the entity performing the action
        self.target_id = target_id    # The ID of the entity being acted upon (optional)
        self.location = location      # Where the event happened (optional)
        self.timestamp = game_time  # Use game ticks for consistency


class WorldGenerator:
    """Handles the procedural generation of the world's macro-structure."""
    def __init__(self, width, height, seed=None):
        self.width = width
        self.height = height
        self.noise = tcod.noise.Noise(
            dimensions=2,
            algorithm=tcod.noise.Algorithm.SIMPLEX,
            implementation=tcod.noise.Implementation.SIMPLE,
            hurst=NOISE_PERSISTENCE,
            lacunarity=NOISE_LACUNARITY,
            octaves=NOISE_OCTAVES,
            seed=seed
        )
        self.elevation_map = self._generate_noise_map()

    def _generate_noise_map(self):
        noise_map = np.zeros((self.height, self.width), dtype=np.float32)
        for y in range(self.height):
            for x in range(self.width):
                noise_map[y, x] = self.noise[x * NOISE_SCALE, y * NOISE_SCALE].item()
        return noise_map

    def get_biome_at(self, x, y):
        """Determines the biome for a given CHUNK coordinate based on elevation."""
        elevation = self.elevation_map[y, x]
        if elevation < ELEVATION_DEEP_WATER: return "deep_water"
        if elevation < ELEVATION_WATER: return "water"
        if elevation < ELEVATION_MOUNTAIN: return "plains"
        if elevation < ELEVATION_SNOW: return "mountain"
        return "snow"

    def get_poi_at(self, x, y, biome):
        """Determines if a POI should be placed at a chunk coordinate."""
        if biome == "plains":
            if random.random() < POI_DENSITY:
                return "village"
            elif random.random() < POI_DENSITY / 4: # Ruins are rarer
                return "ruin"
        elif biome == "mountain":
            if random.random() < POI_DENSITY / 3:
                return "ruin"
        return None

class Building:
    def __init__(self, x, y, width, height, building_type="house", category="residential", global_chunk_x_start=0, global_chunk_y_start=0):
        self.id = str(uuid.uuid4()) # Unique ID for the building
        self.x = x # Local x within chunk
        self.y = y # Local y within chunk
        self.width = width
        self.height = height
        self.building_type = building_type
        self.category = category
        self.interior_decorated = False
        self.occupants = [] # General list of NPCs associated (e.g. workers)
        self.residents = []
        self.building_inventory = {}
        self.interaction_points = {}
        # Work zones: keys are zone_tags (e.g., "log_pile_area"), values are lists of global (x,y) coordinates
        self.work_zone_tiles: dict[str, list[tuple[int, int]]] = {}

        # Store global origin of the building (top-left tile)
        self.global_origin_x = global_chunk_x_start + x
        self.global_origin_y = global_chunk_y_start + y

        # Global coordinates of the building's center
        self.global_center_x = self.global_origin_x + width // 2
        self.global_center_y = self.global_origin_y + height // 2
        self.player_owned: bool = False # New attribute for player housing
        self.max_workers: int = 2 # Default capacity, updated during generation

    @property
    def max_workers(self):
        return getattr(self, "_max_workers", 2)

    @max_workers.setter
    def max_workers(self, value):
        self._max_workers = value

    def contains_global_coords(self, world_x: int, world_y: int) -> bool:
        """Checks if the given global world coordinates are within this building's footprint."""
        return (self.global_origin_x <= world_x < self.global_origin_x + self.width and
                self.global_origin_y <= world_y < self.global_origin_y + self.height)

class Village:
    def __init__(self):
        self.buildings = []
        self.lore = "No lore generated yet."
        self.interaction_points = {} # E.g., {"well": [(x1,y1), (x2,y2)], "town_square_center": (x,y)}
        self.supply = {}  # item_key: count
        self.demand = {}  # item_key: count

    def add_building(self, building: Building):
        self.buildings.append(building)

class Ruin:
    def __init__(self):
        self.lore = "The origins of this place are lost to time."

from dataclasses import dataclass, field
from typing import Any

class Chunk:
    def __init__(self, biome, poi_type=None):
        self.biome = biome
        self.poi_type = poi_type
        self.tiles = None
        self.is_generated = False
        self.village = None # To store Village object if POI is a village
        self.ruin = None # To store Ruin object if POI is a ruin

@dataclass
class PlayerPhysicalState:
    hunger: int = 0
    max_hunger: int = 100
    thirst: int = 0
    max_thirst: int = 100
    hunger_level_msg: str = ""
    thirst_level_msg: str = ""
    temperature: float = 37.0
    base_temperature_resistance: float = 0.0
    clothing_insulation: float = 0.0
    status_effects: list[str] = field(default_factory=list)
    is_wet: bool = False
    wetness_timer: int = 0
    is_sheltered: bool = False
    hearing_radius: int = DEFAULT_HEARING_RADIUS

@dataclass
class PlayerCombatStats:
    max_hp: int = 30
    hp: int = 30
    defense_bonus: int = 0

@dataclass
class PlayerSocialState:
    reputation: dict[str, int] = field(default_factory=lambda: {REP_CRIMINAL: INITIAL_CRIMINAL_POINTS, REP_HERO: INITIAL_HERO_POINTS})
    social_skill: int = 5
    fame: int = 0
    infamy: int = 0
    title: str = ""

@dataclass
class PlayerEconomicState:
    inventory: list[dict] = field(default_factory=list)
    money: int = 100
    active_contracts: dict = field(default_factory=dict)
    pending_contract_offer: Any | None = None
    bounty: int = 0

@dataclass
class PlayerEquipment:
    equipped_armor: dict[str, str | None] = field(default_factory=lambda: {"head": None, "body": None, "hands": None, "feet": None})
    equipped_light_item_key: str | None = None
    light_source_active_until_tick: int = -1
    current_personal_light_radius: int = 0

@dataclass
class PlayerKnowledge:
    active_quests: dict = field(default_factory=dict)
    completed_quests: list[str] = field(default_factory=list)
    known_books: set[str] = field(default_factory=set)
    lockpicking_skill: int = 3
    known_locations: dict[str, tuple[int, int]] = field(default_factory=dict)

@dataclass
class PlayerState:
    is_sitting: bool = False
    is_sleeping: bool = False
    sitting_on_object_at: tuple[int, int] | None = None
    is_jailed: bool = False
    jail_cell_coords: tuple[int, int] | None = None
    jail_time_remaining: int = 0
    is_riding: bool = False
    riding_animal_id: int | None = None
    last_dx: int = 0
    last_dy: int = -1
    original_char: int = ord('@')


class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.char = ord('@')
        self.color = COLORS["player_fg"]
        self.id = id(self)  # Simple unique ID for player

        # Components
        self.physical = PlayerPhysicalState()
        self.combat = PlayerCombatStats()
        self.social = PlayerSocialState()
        self.economic = PlayerEconomicState()
        self.equipment = PlayerEquipment()
        self.knowledge = PlayerKnowledge()
        self.state = PlayerState()

        self.state.original_char = self.char
        self.combat.hp = self.combat.max_hp


    def take_damage(self, amount: int, world=None) -> int:
        """Applies damage to the player after accounting for armor, returns actual damage dealt."""
        effective_damage = max(0, amount - self.combat.defense_bonus)
        self.combat.hp -= effective_damage
        if self.combat.hp < 0:
            self.combat.hp = 0

        world_ref = world if world else getattr(self, 'world_ref', None)
        if self.combat.hp <= 0 and world_ref:
            world_ref.game_state = "PLAYER_DEAD"

        return effective_damage

    def equip_armor(self, item_key: str):
        item_def = ITEM_DEFINITIONS.get(item_key)
        if not item_def or "armor" not in item_def.get("item_type_tags", []):
            self.world_ref.add_message_to_chat_log("You can't equip that.")
            return

        slot = item_def.get("equip_slot")
        if not slot or slot not in self.equipment.equipped_armor:
            self.world_ref.add_message_to_chat_log("That item doesn't have a valid equip slot.")
            return

        # Unequip current item in that slot, if any
        if self.equipment.equipped_armor.get(slot):
            self.unequip_armor(slot)

        self.equipment.equipped_armor[slot] = item_key
        self.world_ref.add_message_to_chat_log(f"You equip the {item_def['name']}.")
        self.recalculate_stats()

    def unequip_armor(self, slot: str):
        if slot in self.equipment.equipped_armor and self.equipment.equipped_armor[slot]:
            item_key = self.equipment.equipped_armor[slot]
            item_def = ITEM_DEFINITIONS.get(item_key)
            self.equipment.equipped_armor[slot] = None
            self.world_ref.add_message_to_chat_log(f"You unequip the {item_def['name']}.")
            self.recalculate_stats()

    def recalculate_stats(self):
        """Recalculates player stats based on equipped items."""
        self.physical.clothing_insulation = 0.0
        self.combat.defense_bonus = 0
        for slot, item_key in self.equipment.equipped_armor.items():
            if item_key:
                item_def = ITEM_DEFINITIONS.get(item_key)
                if item_def and "properties" in item_def:
                    self.physical.clothing_insulation += item_def["properties"].get("insulation", 0.0)
                    self.combat.defense_bonus += item_def["properties"].get("defense_bonus", 0)

    def add_item(self, item_key_to_add: str, quantity: int = 1, initial_durability: int | None = None):
        item_def = ITEM_DEFINITIONS.get(item_key_to_add)
        if not item_def:
            print(f"Warning: Tried to add unknown item key '{item_key_to_add}'")
            return

        is_stackable = item_def.get("stackable", False)

        if is_stackable:
            for item_instance in self.economic.inventory:
                if item_instance["key"] == item_key_to_add:
                    item_instance["quantity"] = item_instance.get("quantity", 0) + quantity
                    return
            # Not found, add new stack
            self.economic.inventory.append({"key": item_key_to_add, "quantity": quantity})
        else: # Non-stackable (durable or unique)
            for _ in range(quantity): # Add multiple individual instances if quantity > 1
                new_instance = {"key": item_key_to_add}
                if "max_durability" in item_def.get("properties", {}):
                    new_instance["max_durability"] = item_def["properties"]["max_durability"]
                    new_instance["durability"] = initial_durability if initial_durability is not None else new_instance["max_durability"]
                self.economic.inventory.append(new_instance)

    def remove_item(self, item_key_to_remove: str, quantity: int = 1, specific_instance_index: int | None = None) -> bool:
        item_def = ITEM_DEFINITIONS.get(item_key_to_remove)
        if not item_def:
            # print(f"Warning: Tried to remove unknown item key '{item_key_to_remove}'")
            return False

        is_stackable = item_def.get("stackable", False)

        if is_stackable:
            for i, item_instance in enumerate(self.economic.inventory):
                if item_instance["key"] == item_key_to_remove:
                    if item_instance.get("quantity", 0) >= quantity:
                        item_instance["quantity"] -= quantity
                        if item_instance["quantity"] <= 0:
                            self.economic.inventory.pop(i)
                        return True
                    else: # Not enough in this stack (shouldn't happen if has_item was checked)
                        return False
            return False # Item not found
        else: # Non-stackable
            removed_count = 0
            indices_to_remove = []
            if specific_instance_index is not None and 0 <= specific_instance_index < len(self.economic.inventory):
                 if self.economic.inventory[specific_instance_index]["key"] == item_key_to_remove:
                    indices_to_remove.append(specific_instance_index)
                    removed_count = 1
            else: # Remove first N instances found
                for i in range(len(self.economic.inventory) -1, -1, -1): # Iterate backwards for safe removal
                    if self.economic.inventory[i]["key"] == item_key_to_remove:
                        indices_to_remove.append(i)
                        removed_count += 1
                        if removed_count == quantity:
                            break

            if removed_count == quantity:
                for index in sorted(indices_to_remove, reverse=True): # Sort to remove from end first
                    self.economic.inventory.pop(index)
                return True
            return False # Not enough instances found or specific instance mismatch

    def has_item(self, item_key_to_check: str, quantity: int = 1) -> bool:
        item_def = ITEM_DEFINITIONS.get(item_key_to_check)
        if not item_def: return False
        is_stackable = item_def.get("stackable", False)

        if is_stackable:
            for item_instance in self.economic.inventory:
                if item_instance["key"] == item_key_to_check:
                    return item_instance.get("quantity", 0) >= quantity
            return False
        else: # Non-stackable, check for presence of N instances
            count = 0
            for item_instance in self.economic.inventory:
                if item_instance["key"] == item_key_to_check:
                    count += 1
            return count >= quantity

    def get_item_instance_indices(self, item_key_to_find: str) -> list[int]:
        """Returns a list of indices for all instances of a given non-stackable item key."""
        indices = []
        for i, item_instance in enumerate(self.economic.inventory):
            if item_instance["key"] == item_key_to_find:
                indices.append(i)
        return indices

    def get_item_by_index(self, index: int) -> dict | None:
        if 0 <= index < len(self.economic.inventory):
            return self.economic.inventory[index]
        return None

    def adjust_reputation(self, rep_type: str, amount: int):
        """Adjusts the player's reputation of a specific type."""
        if rep_type in self.social.reputation:
            self.social.reputation[rep_type] += amount
            # Could add clamping here if REP_MIN/MAX_VALUE were used
            # self.social.reputation[rep_type] = max(REP_MIN_VALUE, min(self.social.reputation[rep_type], REP_MAX_VALUE))
            # print(f"Player reputation updated: {rep_type} changed by {amount} to {self.social.reputation[rep_type]}") # For now, print to console
            if hasattr(self, 'world_ref') and self.world_ref: # Access world_ref if it exists
                self.world_ref.add_message_to_chat_log(f"Reputation: {rep_type} {amount:+} (Total: {self.social.reputation[rep_type]})")
        else:
            # print(f"Warning: Tried to adjust unknown reputation type '{rep_type}'")
            if hasattr(self, 'world_ref') and self.world_ref:
                 self.world_ref.add_message_to_chat_log(f"Warning: Tried to adjust unknown reputation type '{rep_type}'")


class World:
    """World class now uses a generator for a more complex map."""
    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
        self.chat_log = [] # Stores chat messages
        self.chunk_width = WORLD_WIDTH // CHUNK_SIZE
        self.chunk_height = WORLD_HEIGHT // CHUNK_SIZE
        self.player = Player(WORLD_WIDTH // 2, WORLD_HEIGHT // 2)
        self.player.world_ref = self
        self.generator = WorldGenerator(self.chunk_width, self.chunk_height, seed=seed)
        self.chunks = self._initialize_chunks()
        self.npcs = []
        self.village_npcs = []
        self.buildings_by_id = {}
        self.mouse_x = 0
        self.mouse_y = 0
        self.game_state = "PLAYING"
        self.game_time = 0
        self.last_talked_to_npc = None # Store the NPC targeted by 'T'alk (may be superseded by menu target)
        self.needs_text_input = False

        # Season and Temperature
        self.seasons: list[str] = ["Spring", "Summer", "Autumn", "Winter"]
        self.current_season_index: int = 0
        self.current_day: int = 0
        self.ambient_temperature: float = 20.0 # Default starting temp
        self.weather = "clear"
        self.weather_change_timer: int = 0

        # New Interaction Context
        self.interaction_context = {
            "active": False,
            "x": 0,
            "y": 0,
            "target_entities": [],  # List of entities on the tile
            "selected_entity_index": 0,
            "available_actions": [], # Actions for the selected entity
            "selected_action_index": 0
        }

        # Build Mode State
        self.build_mode_selected_item_index: int = 0
        # Define some placeable items (keys from DECORATION_ITEM_DEFINITIONS)
        self.placeable_furniture_keys: list[str] = [
            "wooden_chair", "wooden_table", "bed_simple", "chest_wooden", "wall_shelf", "fire_pit_simple"
        ]
        self.ghost_furniture_tile: Tile | None = None # For rendering placement preview

        # Chat UI State
        self.chat_ui_active = False
        self.chat_ui_target_npc = None
        self.chat_ui_history = [] # List of tuples: (speaker_name_or_type, text_string)
        self.chat_ui_input_line = ""
        self.chat_ui_mode = "talk"
        self.chat_ui_scroll_offset = 0
        self.chat_ui_max_history = 50

        # Trade UI State
        self.trade_ui_active = False
        self.trade_ui_npc_target = None # The NPC merchant
        self.trade_ui_player_inventory_view = True # True if viewing player's items to sell, False for merchant's
        self.trade_ui_player_item_index = 0
        self.trade_ui_merchant_item_index = 0
        self.trade_ui_player_inventory_snapshot = [] # List of (item_key, quantity, price) tuples
        self.trade_ui_merchant_inventory_snapshot = [] # List of (item_key, quantity, price) tuples

        # Crafting Menu State
        self.crafting_menu_context = {
            "selected_recipe_index": 0,
            "scroll_offset": 0,
            "all_recipes": [] # This will be populated when the menu is opened
        }

        # Building Menu State
        self.building_menu_context = {
            "selected_recipe_index": 0,
            "scroll_offset": 0,
            "all_recipes": [] # This will be populated when the menu is opened
        }

        # Knowledge Menu State
        self.knowledge_menu_context = {
            "scroll_offset": 0
        }

        # Book Reading UI State
        self.book_reading_context = {
            "book_id": None,
            "scroll_offset": 0
        }

        # Items on the ground
        self.items_on_map: dict[tuple[int, int], list[dict]] = {} # Key: (x,y), Value: list of {"item_key": str, "quantity": int}

        # FOV and Light Level state
        self.current_light_level_name = "DAY" # Default
        self.current_fov_radius = FOV_RADIUS_DAY # Default

        # Initialize FOV related maps
        self.player_fov_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), fill_value=False, order="F")
        self.npc_fov_maps: dict[int, np.ndarray] = {}
        self.explored_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), fill_value=False, order="F")
        self.transparency_map = np.full((WORLD_HEIGHT, WORLD_WIDTH), fill_value=True, order="F")

        # Sound events list for the current tick
        self.sound_events: list[dict] = [] # Each dict: {"x", "y", "type", "volume", "source_id"(optional)}

        # Gossip and Event System
        self.global_events: list[Event] = []
        self.books: list[Book] = []

        # Pre-generate all chunks to avoid lazy-loading issues in tests
        for y in range(self.chunk_height):
            for x in range(self.chunk_width):
                self._generate_chunk_detail(self.chunks[y][x], x, y)

        self._spawn_traveling_merchants()
        self._find_starting_position()

        # Build transparency map - this is expensive on init as it forces all chunks to generate.
        # Consider dynamic updates or pre-generation if performance becomes an issue.
        for y_map in range(WORLD_HEIGHT):
            for x_map in range(WORLD_WIDTH):
                tile = self.get_tile_at(x_map, y_map) # Forces chunk generation
                if tile and tile.blocks_fov:
                    self.transparency_map[y_map, x_map] = False

        self._update_light_level_and_fov() # Initialize based on game time 0
        self._update_player_fov() # Initial FOV calculation for player
        self._update_player_hunger_thirst(initial_setup=True) # Initial status update

    def _update_entity_temperature(self, entity):
        """Calculates ambient temperature at entity's location and updates their body temperature."""
        is_player = isinstance(entity, Player)

        # 1. Calculate Ambient Temperature at entity's location
        season_name = self.seasons[self.current_season_index]
        base_temp = SEASON_TEMPERATURE_MODIFIERS.get(season_name, 20)

        entity_chunk = self.chunks[entity.y // CHUNK_SIZE][entity.x // CHUNK_SIZE]
        biome_temp_mod = BIOME_TEMPERATURE_MODIFIERS.get(entity_chunk.biome, 0)

        time_of_day_mod = TIME_OF_DAY_TEMPERATURE_MODIFIERS.get(self.current_light_level_name, 0)

        ambient_temp = base_temp + biome_temp_mod + time_of_day_mod

        # Check for nearby heat sources
        heat_source_bonus = 0.0
        search_radius = 5 if is_player else 3
        for y in range(entity.y - search_radius, entity.y + search_radius + 1):
            for x in range(entity.x - search_radius, entity.x + search_radius + 1):
                if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
                    tile = self.get_tile_at(x, y)
                    if tile and hasattr(tile, 'properties') and tile.properties and tile.properties.get("heat_source"):
                        radius = tile.properties.get("heat_source_radius", 0)
                        intensity = tile.properties.get("heat_intensity", 0)
                        distance = max(abs(entity.x - x), abs(entity.y - y))
                        if distance <= radius:
                            heat_bonus = intensity * (1 - (distance / radius))
                            if heat_bonus > heat_source_bonus:
                                heat_source_bonus = heat_bonus

        ambient_temp_at_entity = ambient_temp + heat_source_bonus
        if is_player:
            self.ambient_temperature = ambient_temp_at_entity

        # 2. Update entity Temperature
        entity.recalculate_stats()
        total_insulation = entity.physical.base_temperature_resistance + entity.physical.clothing_insulation

        # Apply wetness penalty for player
        if is_player and entity.physical.is_wet:
            total_insulation *= 0.5

        target_temp_equilibrium = ambient_temp_at_entity + total_insulation

        temp_diff = target_temp_equilibrium - entity.physical.temperature
        change_rate = 0.05
        entity.physical.temperature += temp_diff * change_rate

        # 3. Apply Effects
        entity.physical.status_effects.clear()
        if entity.physical.temperature < 35.0:
            entity.physical.status_effects.append("Freezing")
        elif entity.physical.temperature > 38.5:
            entity.physical.status_effects.append("Overheating")

    def _update_npc_temperature(self, npc: NPC):
        """Wrapper to call the generic entity temperature update for an NPC."""
        self._update_entity_temperature(npc)


    def _update_player_hunger_thirst(self, initial_setup=False):
        """Updates player hunger and thirst, applies effects, and sets status messages."""
        player = self.player
        ticks_for_hunger_increase = DAY_LENGTH_TICKS // 10 # Hunger increases 10 times a day
        ticks_for_thirst_increase = DAY_LENGTH_TICKS // 15 # Thirst increases 15 times a day
        ticks_for_starvation_damage = DAY_LENGTH_TICKS // 20 # Damage if critical for this long

        if not initial_setup:
            if self.game_time % ticks_for_hunger_increase == 0:
                player.physical.hunger = min(player.physical.max_hunger, player.physical.hunger + 5) # Increase by 5
            if self.game_time % ticks_for_thirst_increase == 0:
                player.physical.thirst = min(player.physical.max_thirst, player.physical.thirst + 7) # Increase by 7 (thirst grows faster)

        # Hunger status messages
        if player.physical.hunger >= player.physical.max_hunger * 0.9:
            player.physical.hunger_level_msg = "Starving"
            if not initial_setup and self.game_time % ticks_for_starvation_damage == 0 :
                self.add_message_to_chat_log("You are weak from starvation!")
                player.take_damage(1)
        elif player.physical.hunger >= player.physical.max_hunger * 0.7:
            player.physical.hunger_level_msg = "Very Hungry"
        elif player.physical.hunger >= player.physical.max_hunger * 0.5:
            player.physical.hunger_level_msg = "Hungry"
        elif player.physical.hunger >= player.physical.max_hunger * 0.25:
            player.physical.hunger_level_msg = "Peckish"
        else:
            player.physical.hunger_level_msg = ""

        # Thirst status messages
        if player.physical.thirst >= player.physical.max_thirst * 0.9:
            player.physical.thirst_level_msg = "Dehydrated"
            if not initial_setup and self.game_time % ticks_for_starvation_damage == 0: # Same tick for damage
                self.add_message_to_chat_log("You are faint from thirst!")
                player.take_damage(1)
        elif player.physical.thirst >= player.physical.max_thirst * 0.7:
            player.physical.thirst_level_msg = "Very Thirsty"
        elif player.physical.thirst >= player.physical.max_thirst * 0.5:
            player.physical.thirst_level_msg = "Thirsty"
        else:
            player.physical.thirst_level_msg = ""

    def _update_season(self):
        """Updates the current season based on the number of days passed."""
        day_of_year = self.game_time // DAY_LENGTH_TICKS
        new_season_index = (day_of_year // DAYS_PER_SEASON) % len(self.seasons)

        if new_season_index != self.current_season_index:
            self.current_season_index = new_season_index
            season_name = self.seasons[self.current_season_index]
            self.add_message_to_chat_log(f"The season has changed to {season_name}.")

    def _update_player_temperature(self):
        """Wrapper to call the generic entity temperature update for the player."""
        self._update_entity_temperature(self.player)

    def _apply_temperature_effects(self, entity):
        """Applies damage and other effects based on an entity's temperature status."""
        ticks_for_temp_damage = DAY_LENGTH_TICKS // 25

        if self.game_time % ticks_for_temp_damage != 0:
            return

        is_player = isinstance(entity, Player)

        if "Freezing" in entity.physical.status_effects:
            if is_player:
                self.add_message_to_chat_log("You are freezing cold!")
            entity.take_damage(1, world=self)
        elif "Overheating" in entity.physical.status_effects:
            if is_player:
                self.add_message_to_chat_log("You are burning up!")
            entity.take_damage(1, world=self)

    def _update_player_wetness(self):
        """Updates the player's wetness status based on weather and shelter."""
        player = self.player

        # First, update the player's shelter status
        player.physical.is_sheltered = self._check_for_shelter(player.x, player.y)

        if self.weather == "rain" and not player.physical.is_sheltered:
            if not player.physical.is_wet:
                self.add_message_to_chat_log("You are getting wet from the rain.")
            player.physical.is_wet = True
            player.physical.wetness_timer = max(player.physical.wetness_timer, DAY_LENGTH_TICKS // 10) # Become wet for a while

        if player.physical.is_wet and self.game_time % (DAY_LENGTH_TICKS // 20) == 0: # Check to dry off periodically
            if self.weather != "rain" or player.physical.is_sheltered:
                player.physical.wetness_timer -= 1
                if player.physical.wetness_timer <= 0:
                    player.physical.is_wet = False
                    self.add_message_to_chat_log("You have dried off.")

    def _check_for_shelter(self, x: int, y: int, max_dist: int = 10) -> bool:
        """
        Checks if a position is sheltered by casting rays in 8 directions.
        If all rays hit a shelter-providing tile within max_dist, it's sheltered.
        """
        directions = [
            (0, -1),  # N
            (1, -1),  # NE
            (1, 0),   # E
            (1, 1),   # SE
            (0, 1),   # S
            (-1, 1),  # SW
            (-1, 0),  # W
            (-1, -1), # NW
        ]

        for dx, dy in directions:
            found_shelter_in_direction = False
            # Calculate endpoint for the ray
            end_x, end_y = x + dx * max_dist, y + dy * max_dist

            # Get all points in the line
            line_points = tcod.los.bresenham((x, y), (end_x, end_y))

            # Start from the second point to avoid checking the entity's own tile
            for i, (px, py) in enumerate(list(line_points)[1:]):
                if not (0 <= px < WORLD_WIDTH and 0 <= py < WORLD_HEIGHT):
                    # Ray went off the map, this direction is not sheltered
                    return False # Open to the void

                tile = self.get_tile_at(px, py)
                if tile and hasattr(tile, 'properties') and tile.properties.get("provides_shelter"):
                    found_shelter_in_direction = True
                    break # This ray is blocked, check next direction

            if not found_shelter_in_direction:
                # This ray reached max_dist without hitting a shelter tile, so not enclosed.
                return False

        # If all 8 directions found a shelter tile, then we are enclosed.
        return True

    def _handle_player_light_source_burnout(self):
        """Checks and handles burnout of player's active light source."""
        if self.player.equipment.equipped_light_item_key and \
           self.player.equipment.light_source_active_until_tick != -1 and \
           self.game_time >= self.player.equipment.light_source_active_until_tick:

            burnt_item_def = ITEM_DEFINITIONS.get(self.player.equipment.equipped_light_item_key)
            item_name = burnt_item_def.get("name", "light source") if burnt_item_def else "light source"
            self.add_message_to_chat_log(f"Your {item_name} has burnt out!")

            becomes_item_key = burnt_item_def.get("properties", {}).get("on_burnout_becomes")
            if becomes_item_key:
                self.player.economic.inventory[becomes_item_key] = self.player.economic.inventory.get(becomes_item_key, 0) + 1
                # Could also remove 1 of the original item if it was stackable and not fully consumed by "lighting" it
                # For now, lighting "unlit_torch" consumes it, and burnout creates "burnt_out_torch".

            self.player.equipment.equipped_light_item_key = None
            self.player.equipment.current_personal_light_radius = 0
            self.player.equipment.light_source_active_until_tick = -1
            # No need to call self._update_player_fov() here, as _update_light_level_and_fov (which calls this)
            # is followed by _update_player_fov() in the main loop.

    def _update_player_fov(self) -> None:
        """
        Updates the player's field of view map and explored tiles.
        """
        # Player FOV
        base_ambient_fov_radius = self.current_fov_radius
        effective_player_fov_radius = base_ambient_fov_radius

        if self.player.equipment.equipped_light_item_key and self.player.equipment.current_personal_light_radius > 0:
            is_active = True
            if self.player.equipment.light_source_active_until_tick != -1 and \
               self.game_time >= self.player.equipment.light_source_active_until_tick:
                is_active = False

            if is_active:
                effective_player_fov_radius = max(base_ambient_fov_radius, self.player.equipment.current_personal_light_radius)

        self.player_fov_map = tcod.map.compute_fov(
            self.transparency_map,
            (self.player.x, self.player.y),
            radius=effective_player_fov_radius,
            algorithm=libtcodpy.FOV_SYMMETRIC_SHADOWCAST
        )
        self.explored_map |= self.player_fov_map

    def _update_npc_fov(self, npc: NPC) -> None:
        """
        Updates the field of view for a single NPC.
        """
        if npc.physical.is_dead:
            return

        npc_fov_radius = self.current_fov_radius # NPCs use global ambient light for now
        self.npc_fov_maps[npc.id] = tcod.map.compute_fov(
            self.transparency_map,
            (npc.x, npc.y),
            radius=npc_fov_radius,
            algorithm=libtcodpy.FOV_SYMMETRIC_SHADOWCAST
        )

        # NPC Item Perception within their FOV
        npc.knowledge.perceived_item_tiles.clear()
        fov_map_for_npc = self.npc_fov_maps[npc.id]
        visible_y_coords, visible_x_coords = np.where(fov_map_for_npc)
        for i in range(len(visible_x_coords)):
            vx, vy = visible_x_coords[i], visible_y_coords[i]
            if (vx,vy) in self.items_on_map and self.items_on_map[(vx,vy)]:
                npc.knowledge.perceived_item_tiles.append((vx,vy))


    def _update_light_level_and_fov(self):
        """Updates the current light level and FOV radius based on game time, handles torch burnout."""
        self._handle_player_light_source_burnout() # Check for burnout first

        time_ratio = (self.game_time % DAY_LENGTH_TICKS) / DAY_LENGTH_TICKS

        current_period = None
        # LIGHT_LEVEL_PERIODS is sorted by start_ratio. Find the current period.
        for i in range(len(LIGHT_LEVEL_PERIODS)):
            period = LIGHT_LEVEL_PERIODS[i]
            next_period_start_ratio = LIGHT_LEVEL_PERIODS[i+1]["start_ratio"] if (i+1) < len(LIGHT_LEVEL_PERIODS) else 1.0

            if period["start_ratio"] <= time_ratio < next_period_start_ratio:
                current_period = period
                break

        if not current_period: # Should always find one, default to last if somehow not.
            current_period = LIGHT_LEVEL_PERIODS[-1]
            # Or if time_ratio is 1.0, it should use the first period (midnight)
            if time_ratio == 1.0: # Exactly end of day, loop to first period
                 current_period = LIGHT_LEVEL_PERIODS[0]


        self.current_light_level_name = current_period["name"]

        # Map fov_config_key string to actual config variable
        if current_period["fov_config_key"] == "FOV_RADIUS_DAY":
            self.current_fov_radius = FOV_RADIUS_DAY
        elif current_period["fov_config_key"] == "FOV_RADIUS_DUSK_DAWN":
            self.current_fov_radius = FOV_RADIUS_DUSK_DAWN
        elif current_period["fov_config_key"] == "FOV_RADIUS_NIGHT":
            self.current_fov_radius = FOV_RADIUS_NIGHT
        elif current_period["fov_config_key"] == "FOV_RADIUS_PITCH_BLACK":
            self.current_fov_radius = FOV_RADIUS_PITCH_BLACK
        else: # Fallback
            self.current_fov_radius = FOV_RADIUS_DAY

        # Optional: Log change for debugging
        # if self.game_time % 10 == 0: # Log less frequently
        #     print(f"Time: {self.game_time}, Ratio: {time_ratio:.2f}, Light: {self.current_light_level_name}, FOV: {self.current_fov_radius}")


    def _get_pathfinding_cost(self, old_x, old_y, new_x, new_y):
        """
        Callback for tcod.path.AStar.
        Returns movement cost from (old_x, old_y) to (new_x, new_y).
        """
        if not (0 <= new_x < WORLD_WIDTH and 0 <= new_y < WORLD_HEIGHT):
            return 0  # Impassable (out of bounds)

        tile = self.get_tile_at(new_x, new_y)
        if not tile or not tile.passable:
            return 0  # Impassable

        # Diagonal movement cost can be higher if desired, e.g., sqrt(2) or 1.414
        # For simplicity, we'll use 1 for cardinal and diagonal.
        # tcod's AStar handles cardinal/diagonal based on graph/diagnal params.
        return 1


    def calculate_path(self, start_x: int, start_y: int, end_x: int, end_y: int) -> list[tuple[int, int]]:
        """
        Calculates a path from (start_x, start_y) to (end_x, end_y) using A* on a local cost map.
        Returns a list of (x, y) tuples, or an empty list if no path is found.
        """
        start_tile = self.get_tile_at(start_x, start_y)
        if not (start_tile and start_tile.passable):
            return []

        padding = 15
        min_x = max(0, min(start_x, end_x) - padding)
        max_x = min(WORLD_WIDTH - 1, max(start_x, end_x) + padding)
        min_y = max(0, min(start_y, end_y) - padding)
        max_y = min(WORLD_HEIGHT - 1, max(start_y, end_y) + padding)

        local_width = max_x - min_x + 1
        local_height = max_y - min_y + 1

        cost = np.ones((local_height, local_width), dtype=np.float32)

        for y_local in range(local_height):
            for x_local in range(local_width):
                x_world, y_world = min_x + x_local, min_y + y_local
                tile = self.get_tile_at(x_world, y_world)

                if not tile or not tile.passable:
                    cost[y_local, x_local] = 0
                else:
                    base_cost = 1.0
                    if hasattr(tile, 'properties') and tile.properties:
                        base_cost = float(tile.properties.get("movement_cost", 1.0))

                    if tile.is_hazard:
                        hazard_cost_value = 50
                        if tile.hazard_type == "fire_trap_active": hazard_cost_value = 100
                        elif tile.hazard_type == "water_deep": hazard_cost_value = 75
                        cost[y_local, x_local] = base_cost + hazard_cost_value
                    else:
                        cost[y_local, x_local] = base_cost

        astar = tcod.path.AStar(cost=cost, diagonal=1.41)

        start_x_local, start_y_local = start_x - min_x, start_y - min_y
        end_x_local, end_y_local = end_x - min_x, end_y - min_y

        try:
            path_indices_local = astar.get_path(start_x_local, start_y_local, end_x_local, end_y_local)
            path_coords = [(min_x + int(p[1]), min_y + int(p[0])) for p in path_indices_local]
            return path_coords
        except IndexError:
            return []

    def _is_predator(self, npc):
        if not isinstance(npc, Animal):
            return False
        animal_def = ANIMAL_DEFINITIONS.get(npc.animal_type, {})
        return "prey" in animal_def

    def _get_predator_target(self, predator):
        if not predator.task_target_entity_id:
            return None
        return next((n for n in self.npcs if n.id == predator.task_target_entity_id), None)

    def _update_npc_movement(self):
        """Updates NPC positions based on their current path."""
        # This combines both lists for iteration
        for npc in self.village_npcs + self.npcs:
            if npc.physical.is_dead:
                continue

            # --- Handle task-based path recalculation before movement ---
            # If hostile and needs to decide on a combat action that involves movement
            # This section ensures that an NPC's path is up-to-date with its target's position
            # right before it attempts to move.
            if npc.schedule.current_task == "following_player":
                if npc.task_target_entity_id == self.player.id:
                    # Recalculate path to player if not close enough
                    if abs(npc.x - self.player.x) > 2 or abs(npc.y - self.player.y) > 2:
                        dest_x, dest_y = self._find_best_adjacent_tile(self.player.x, self.player.y, npc)
                        if dest_x is not None and (npc.schedule.current_destination_coords != (dest_x, dest_y)):
                            path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = (dest_x, dest_y)
            elif npc.schedule.current_task == "combat_action_attack_player":
                # If in range, just attack, don't move. The attack itself is in this task block.
                # If not in range, switch to move_to_attack.
                player = self.player
                if abs(npc.x - player.x) + abs(npc.y - player.y) <= npc.attack_range:
                    # Attack is handled by this task, so we just need to ensure we don't move after.
                    self.npc_attempt_attack_player(npc, player)
                    npc.schedule.current_path = [] # Clear path after attack
                    npc.schedule.current_destination_coords = None
                    continue # End turn for this NPC
                else:
                    # Not in range, so must move. Change task and let move_to_attack logic below handle pathing.
                    npc.schedule.current_task = "combat_action_move_to_attack_player"
                    npc.schedule.current_path = [] # Clear old path
                    npc.schedule.current_destination_coords = None


            elif npc.schedule.current_task == "combat_action_flee_from_player":
                 # Recalculate flee path if there isn't one or it's very short (destination reached)
                if not npc.schedule.current_path or npc.schedule.current_destination_coords is None:
                    player_x, player_y = self.player.x, self.player.y
                    flee_distance = 15
                    # Vector from player to NPC
                    dx, dy = npc.x - player_x, npc.y - player_y
                    len_vec = math.sqrt(dx*dx + dy*dy)
                    if len_vec > 0:
                        flee_x = npc.x + int((dx / len_vec) * flee_distance)
                        flee_y = npc.y + int((dy / len_vec) * flee_distance)
                    else: # On same tile, flee randomly
                        flee_x, flee_y = npc.x + random.randint(-flee_distance, flee_distance), npc.y + random.randint(-flee_distance, flee_distance)

                    # Clamp to world bounds
                    flee_x = max(0, min(WORLD_WIDTH - 1, flee_x))
                    flee_y = max(0, min(WORLD_HEIGHT - 1, flee_y))

                    path = self.calculate_path(npc.x, npc.y, flee_x, flee_y)
                    if path:
                        npc.schedule.current_path = path
                        npc.schedule.current_destination_coords = (flee_x, flee_y)
                    else:
                        npc.schedule.current_task = "combat_action_hold_position" # No path, so hold.

            elif npc.schedule.current_task == "fleeing_from_player":
                # Fleeing from player due to infamy
                if not npc.schedule.current_path:
                    flee_distance = 15
                    dx, dy = npc.x - self.player.x, npc.y - self.player.y
                    len_vec = math.sqrt(dx*dx + dy*dy)
                    if len_vec > 0:
                        flee_x = npc.x + int((dx / len_vec) * flee_distance)
                        flee_y = npc.y + int((dy / len_vec) * flee_distance)
                    else:
                        flee_x, flee_y = npc.x + random.randint(-flee_distance, flee_distance), npc.y + random.randint(-flee_distance, flee_distance)

                    flee_x = max(0, min(WORLD_WIDTH - 1, flee_x))
                    flee_y = max(0, min(WORLD_HEIGHT - 1, flee_y))

                    path = self.calculate_path(npc.x, npc.y, flee_x, flee_y)
                    if path:
                        npc.schedule.current_path = path
                        npc.schedule.current_destination_coords = (flee_x, flee_y)
                    else:
                        npc.schedule.current_task = "idle" # Can't flee, so just idle

            elif npc.schedule.current_task == "greeting_player":
                # Greeting player due to fame
                if not npc.schedule.current_path:
                    dest_x, dest_y = self._find_best_adjacent_tile(self.player.x, self.player.y, npc)
                    if dest_x is not None:
                        path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                        if path:
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = (dest_x, dest_y)
                        else:
                            npc.schedule.current_task = "idle" # Can't greet, so idle

            elif npc.schedule.current_task == "combat_action_move_to_attack_player":
                player = self.player
                # Recalculate path if no path, or if destination is not adjacent to player anymore
                needs_new_path = False
                if not npc.schedule.current_path or not npc.schedule.current_destination_coords:
                    needs_new_path = True
                elif abs(npc.schedule.current_destination_coords[0] - player.x) + abs(npc.schedule.current_destination_coords[1] - player.y) > npc.attack_range:
                     needs_new_path = True

                if needs_new_path:
                    # Find a new spot to path to, adjacent to the player
                    attack_pos_x, attack_pos_y = self._find_best_adjacent_tile_for_attack(player.x, player.y, npc)
                    if attack_pos_x is not None:
                        path = self.calculate_path(npc.x, npc.y, attack_pos_x, attack_pos_y)
                        if path:
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = (attack_pos_x, attack_pos_y)
                        else:
                            # Cannot find path to attack, so hold position
                            npc.schedule.current_task = "combat_action_hold_position"
                    else:
                        # No valid adjacent tile to attack from, hold position
                        npc.schedule.current_task = "combat_action_hold_position"

            # (Keep other elif blocks for path recalculation like move_to_cover, etc.)


            # --- Unified Path-Based Movement ---
            if npc.schedule.current_path:
                moves_made = 0
                max_moves = getattr(npc, 'speed', 1)
                while moves_made < max_moves and npc.schedule.current_path and len(npc.schedule.current_path) > 1:
                    next_x, next_y = npc.schedule.current_path[1] # Path index 0 is current pos

                    next_tile = self.get_tile_at(next_x, next_y)
                    if not (next_tile and next_tile.passable):
                        npc.schedule.current_path = []
                        npc.schedule.current_destination_coords = None
                        break

                    is_occupied = False
                    is_hunting_prey = self._is_predator(npc) and npc.schedule.current_task == "hunting"
                    for other_npc in self.village_npcs + self.npcs:
                        if other_npc.id != npc.id and other_npc.x == next_x and other_npc.y == next_y and not other_npc.physical.is_dead:
                            if is_hunting_prey and other_npc.id == npc.task_target_entity_id:
                                continue # Predator can move onto prey's tile
                            is_occupied = True
                            break

                    if is_occupied:
                        npc.schedule.current_path = []
                        npc.schedule.current_destination_coords = None
                        break

                    npc.x, npc.y = next_x, next_y
                    npc.schedule.current_path.pop(0)
                    moves_made += 1

                if not npc.schedule.current_path or len(npc.schedule.current_path) <= 1:
                    npc.schedule.current_path = []
                    # Destination reached, process arrival based on task
                    if npc.economic.profession == "Traveling Merchant" and npc.schedule.current_task == "traveling_to_village":
                        self.add_message_to_chat_log(f"{npc.name} has arrived at a village.")
                        npc.schedule.current_task = "lingering_in_village"
                        npc.leisure_timer = random.randint(DAY_LENGTH_TICKS // 2, DAY_LENGTH_TICKS)

                        arrival_village = self._get_village_for_npc(npc, by_coords=True)
                        if arrival_village:
                            key_npcs = [
                                other_npc for other_npc in self.village_npcs
                                if self._get_village_for_npc(other_npc) == arrival_village and
                                other_npc.economic.profession in ["Tavern Keeper", "Town Official", "Sheriff"]
                            ]
                            if key_npcs:
                                gossip_recipient = random.choice(key_npcs)
                                events_shared = 0
                                for event_id, event_obj in npc.known_events.items():
                                    if event_id not in gossip_recipient.known_events:
                                        gossip_recipient.known_events[event_id] = event_obj
                                        events_shared += 1
                                if events_shared > 0:
                                    self.add_message_to_chat_log(f"Debug: {npc.name} shared {events_shared} rumors with {gossip_recipient.name}.")

                        npc.known_events.clear()
                        village_center_x = (npc.x // CHUNK_SIZE) * CHUNK_SIZE + CHUNK_SIZE // 2
                        village_center_y = (npc.y // CHUNK_SIZE) * CHUNK_SIZE + CHUNK_SIZE // 2
                        for event in self.global_events:
                            if event.location:
                                dist_sq = (event.location[0] - village_center_x)**2 + (event.location[1] - village_center_y)**2
                                if dist_sq < (CHUNK_SIZE * 1.5)**2:
                                    if event.id not in npc.known_events:
                                        npc.known_events[event.id] = event
                        if npc.known_events:
                            self.add_message_to_chat_log(f"Debug: {npc.name} learned about {len(npc.known_events)} events in the new village.")

                    elif npc.schedule.current_task == "socializing" and npc.task_target_entity_id:
                        chat_partner = next((p for p in self.village_npcs if p.id == npc.task_target_entity_id), None)
                        if chat_partner and abs(npc.x - chat_partner.x) + abs(npc.y - chat_partner.y) <= 1:
                            # Successfully met up, now exchange gossip
                            # NPC shares one piece of news with partner
                            if npc.known_events:
                                event_id_to_share = random.choice(list(npc.known_events.keys()))
                                if event_id_to_share not in chat_partner.known_events:
                                    chat_partner.known_events[event_id_to_share] = npc.known_events[event_id_to_share]
                                    # self.add_message_to_chat_log(f"Debug: {npc.name} told {chat_partner.name} about event {event_id_to_share[:8]}.")

                            # Partner shares one piece of news back
                            if chat_partner.known_events:
                                event_id_to_share_back = random.choice(list(chat_partner.known_events.keys()))
                                if event_id_to_share_back not in npc.known_events:
                                    npc.known_events[event_id_to_share_back] = chat_partner.known_events[event_id_to_share_back]
                                    # self.add_message_to_chat_log(f"Debug: {chat_partner.name} told {npc.name} about event {event_id_to_share_back[:8]}.")

                            # Increase relationship
                            npc.relationships[chat_partner.id] = min(100, npc.relationships.get(chat_partner.id, 50) + 5)
                            chat_partner.relationships[npc.id] = min(100, chat_partner.relationships.get(npc.id, 50) + 5)


                        npc.schedule.current_task = "idle" # Done socializing for now
                    elif npc.schedule.current_task == "visiting friend" and npc.task_target_entity_id:
                        friend = next((p for p in self.village_npcs if p.id == npc.task_target_entity_id), None)
                        if friend and friend.home_building_id:
                            friend_home = self.buildings_by_id.get(friend.home_building_id)
                            if friend_home and (npc.x, npc.y) == (friend_home.global_center_x, friend_home.global_center_y):
                                # Successfully arrived at friend's house
                                npc.relationships[friend.id] = min(100, npc.relationships.get(friend.id, 50) + 10)
                                friend.relationships[npc.id] = min(100, friend.relationships.get(npc.id, 50) + 10)
                                # self.add_message_to_chat_log(f"Debug: {npc.name} is visiting {friend.name}, relationship increased.")
                        npc.schedule.current_task = "idle" # Done visiting
                    elif npc.schedule.current_task == "greeting_player":
                        # Successfully reached the player, initiate dialogue
                        self.add_message_to_chat_log(f"{npc.name} says hello!")
                        self.start_npc_dialogue(npc)
                        self.chat_ui_active = True
                        self.needs_text_input = True
                        npc.schedule.current_task = "idle"
                    elif npc.schedule.current_task == "approaching_player_for_help":
                        self.start_npc_dialogue(npc)
                        self.chat_ui_active = True
                        self.needs_text_input = True
                        npc.schedule.current_task = "idle"
                    elif npc.schedule.current_task == "courting":
                        partner = next((p for p in self.village_npcs if p.id == npc.task_target_entity_id), None)
                        if partner:
                            # Proposal logic
                            relationship_score = npc.social.relationships.get(partner.id, 0)
                            if relationship_score > 70: # High relationship needed
                                npc.social.family_ties["partner_id"] = partner.id
                                partner.social.family_ties["partner_id"] = npc.id
                                self.add_message_to_chat_log(f"{npc.name} and {partner.name} are now married!")
                                self.log_event(
                                    event_type="npc_marriage",
                                    description=f"{npc.name} and {partner.name} were married.",
                                    subject_id=npc.id,
                                    target_id=partner.id,
                                    location=(npc.x, npc.y)
                                )
                                # Post-marriage changes
                                if partner.schedule.home_building_id:
                                    if npc.schedule.home_building_id:
                                        old_home = self.buildings_by_id.get(npc.schedule.home_building_id)
                                        if old_home and npc in old_home.residents:
                                            old_home.residents.remove(npc)

                                    new_home = self.buildings_by_id.get(partner.schedule.home_building_id)
                                    if new_home:
                                        new_home.residents.append(npc)
                                        npc.schedule.home_building_id = partner.schedule.home_building_id
                                        self.add_message_to_chat_log(f"{npc.name} has moved in with {partner.name}.")

                            else:
                                self.add_message_to_chat_log(f"{npc.name} proposed to {partner.name}, but was rejected.")
                        npc.schedule.current_task = "idle"
                    elif npc.schedule.current_task == "going to work":
                        npc.schedule.current_task = "at work"
                    elif npc.schedule.current_task == "looking_for_work":
                        # Arrived at potential workplace
                        npc.schedule.current_task = "idle" # Or "lingering" if handled elsewhere, for now idle means they stay put
                        # self.add_message_to_chat_log(f"Debug: {npc.name} is looking for work at a building.")
                    elif npc.schedule.current_task == "leaving_village":
                        # NPC has arrived at the edge of the map
                        self._remove_npc_from_world(npc, reason="emigrated")
                        continue # Stop processing this NPC
                    elif npc.schedule.current_task in ["going home", "going home to sleep", "going to bed"]:
                        npc.schedule.current_task = "at home"
                    else:
                        npc.schedule.current_task = "idle" # Default state post-movement

                    npc.schedule.current_destination_coords = None

    def _get_building_global_center_coords(self, building_id: str) -> tuple[int, int] | None:
        """Gets a building's global center coordinates using the buildings_by_id lookup."""
        building = self.buildings_by_id.get(building_id)
        if building:
            return building.global_center_x, building.global_center_y
        return None

    def _get_time_of_day_str(self, game_time_tick: int, day_length: int) -> str:
        """Converts a game tick to a descriptive time of day string."""
        time_ratio = (game_time_tick % day_length) / day_length
        if 0 <= time_ratio < 0.1: return "Dead of Night"
        if 0.1 <= time_ratio < 0.25: return "Early Morning"
        if 0.25 <= time_ratio < 0.45: return "Morning"
        if 0.45 <= time_ratio < 0.60: return "Midday"
        if 0.60 <= time_ratio < 0.75: return "Afternoon"
        if 0.75 <= time_ratio < 0.90: return "Evening"
        return "Night"

    def _get_location_description(self, x: int, y: int) -> str:
        """Generates a brief description of a location based on its tile, building, or biome."""
        # 1. Check for building
        building = self.get_building_at(x, y)
        if building:
            building_name = building.building_type.replace('_', ' ')
            if building.building_type in ["house", "home"]:
                return f"in a {building_name}"
            else:
                return f"in the {building_name}"

        # 2. Check for specific outdoor features
        tile = self.get_tile_at(x, y)
        if tile:
            if tile.name == "Road":
                return "on a road"
            if tile.name == "Well":
                return "by the village well"
            if "water" in tile.name.lower():
                return "near the water"

        # 3. Fallback to biome
        chunk_x = x // CHUNK_SIZE
        chunk_y = y // CHUNK_SIZE
        if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
            chunk = self.chunks[chunk_y][chunk_x]
            biome_name = chunk.biome.replace('_', ' ')
            return f"in the {biome_name}"

        return "in an unknown area"

    def _find_best_adjacent_tile(self, target_x: int, target_y: int, entity) -> tuple[int | None, int | None]:
        """
        Finds a passable, unoccupied, adjacent tile to the target for the entity to move to.
        Prefers tiles closer to the entity if multiple are valid.
        """
        potential_spots = []
        # Check cardinal directions first
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            adj_x, adj_y = target_x + dx, target_y + dy

            # Basic validation
            if not (0 <= adj_x < WORLD_WIDTH and 0 <= adj_y < WORLD_HEIGHT):
                continue
            tile = self.get_tile_at(adj_x, adj_y)
            if not (tile and tile.passable):
                continue

            # Check for occupancy
            occupied = False
            for npc in self.village_npcs + self.npcs:
                if npc.id != entity.id and npc.x == adj_x and npc.y == adj_y and not npc.physical.is_dead:
                    occupied = True
                    break
            if occupied:
                continue

            dist_sq = (entity.x - adj_x)**2 + (entity.y - adj_y)**2
            potential_spots.append({'x': adj_x, 'y': adj_y, 'dist_sq': dist_sq})

        if not potential_spots:
            return None, None

        potential_spots.sort(key=lambda s: s['dist_sq'])
        return potential_spots[0]['x'], potential_spots[0]['y']

    def _find_nearest_map_edge(self, npc: NPC) -> tuple[int, int]:
        """Finds the nearest map edge coordinate for an NPC to exit."""
        dist_to_left = npc.x
        dist_to_right = WORLD_WIDTH - 1 - npc.x
        dist_to_top = npc.y
        dist_to_bottom = WORLD_HEIGHT - 1 - npc.y

        min_dist = min(dist_to_left, dist_to_right, dist_to_top, dist_to_bottom)

        if min_dist == dist_to_left:
            return (0, npc.y)
        elif min_dist == dist_to_right:
            return (WORLD_WIDTH - 1, npc.y)
        elif min_dist == dist_to_top:
            return (npc.x, 0)
        else:
            return (npc.x, WORLD_HEIGHT - 1)

    def _find_best_adjacent_tile_for_attack(self, target_x: int, target_y: int, attacker_npc: NPC) -> tuple[int | None, int | None]:
        """
        Finds a passable, unoccupied, adjacent tile to the target for the attacker to move to.
        Prefers tiles closer to the attacker if multiple are valid.
        Returns (x, y) or (None, None) if no suitable tile is found.
        """
        potential_spots = []
        # Order of adjacent tiles to check (N, S, E, W)
        adj_offsets = [(0, -1), (0, 1), (-1, 0), (1, 0)]

        for dx, dy in adj_offsets:
            adj_x, adj_y = target_x + dx, target_y + dy

            if not (0 <= adj_x < WORLD_WIDTH and 0 <= adj_y < WORLD_HEIGHT):
                continue # Out of bounds

            tile = self.get_tile_at(adj_x, adj_y)
            if not (tile and tile.passable):
                continue # Not passable

            # Check if occupied by another NPC (excluding the attacker itself)
            occupied_by_other_npc = False
            # Iterate over all relevant NPC lists
            for npc_list_to_check in [self.village_npcs, self.npcs]:
                for other_npc in npc_list_to_check:
                    if other_npc.id != attacker_npc.id and other_npc.x == adj_x and other_npc.y == adj_y and not other_npc.physical.is_dead:
                        occupied_by_other_npc = True
                        break
                if occupied_by_other_npc:
                    break
            if occupied_by_other_npc:
                continue

            # Ensure the spot is not the attacker's current location if they are already next to target
            # This prevents pathing to their own spot if they are already adjacent.
            if adj_x == attacker_npc.x and adj_y == attacker_npc.y:
                continue

            dist_sq = (attacker_npc.x - adj_x)**2 + (attacker_npc.y - adj_y)**2
            potential_spots.append({'x': adj_x, 'y': adj_y, 'dist_sq': dist_sq})

        if not potential_spots:
            return None, None

        potential_spots.sort(key=lambda s: s['dist_sq'])

        return potential_spots[0]['x'], potential_spots[0]['y']

    def _find_best_cover_spot(self, npc: NPC, threat_x: int, threat_y: int, max_radius: int = 7) -> tuple[int | None, int | None]:
        """
        Finds a passable, unoccupied tile that offers cover from the threat.
        Cover is defined by being adjacent to a tile with provides_cover_value > 0,
        where that cover-providing tile is between the spot and the threat,
        OR the spot itself provides cover.
        Prioritizes higher cover value, then closer distance to the NPC.
        """
        candidate_spots = []

        for r_loop in range(1, max_radius + 1):  # Iterate radius from 1 up to max_radius
            perimeter_offsets_this_radius = set()
            for i_loop in range(r_loop + 1):
                j_loop = r_loop - i_loop
                if i_loop == 0 and j_loop == 0 : continue

                points_to_add_from_ij = []
                if i_loop == 0:
                    points_to_add_from_ij.extend([(0,j_loop), (0,-j_loop), (j_loop,0), (-j_loop,0)])
                elif j_loop == 0:
                     points_to_add_from_ij.extend([(i_loop,0), (-i_loop,0), (0,i_loop), (0,-i_loop)])
                else:
                    points_to_add_from_ij.extend([(i_loop,j_loop), (-i_loop,j_loop), (i_loop,-j_loop), (-i_loop,-j_loop)])
                    if i_loop != j_loop:
                         points_to_add_from_ij.extend([(j_loop,i_loop), (-j_loop,i_loop), (j_loop,-i_loop), (-j_loop,-i_loop)])

                for p_dx, p_dy in points_to_add_from_ij:
                    if abs(p_dx) + abs(p_dy) == r_loop:
                        perimeter_offsets_this_radius.add((p_dx, p_dy))

            for spot_dx, spot_dy in perimeter_offsets_this_radius:
                spot_x, spot_y = npc.x + spot_dx, npc.y + spot_dy

                if not (0 <= spot_x < WORLD_WIDTH and 0 <= spot_y < WORLD_HEIGHT):
                    continue

                spot_tile = self.get_tile_at(spot_x, spot_y)
                if not (spot_tile and spot_tile.passable):
                    continue

                occupied = False
                for other_npc_list_to_check in [self.village_npcs, self.npcs]:
                    for other_npc in other_npc_list_to_check:
                        if other_npc.id != npc.id and other_npc.x == spot_x and other_npc.y == spot_y and not other_npc.physical.is_dead:
                            occupied = True; break
                    if occupied: break
                if occupied: continue

                current_max_cover_value_for_spot = 0.0
                if spot_tile.provides_cover_value > 0:
                     current_max_cover_value_for_spot = max(current_max_cover_value_for_spot, spot_tile.provides_cover_value)

                for adj_dx_neighbor in range(-1, 2):
                    for adj_dy_neighbor in range(-1, 2):
                        if adj_dx_neighbor == 0 and adj_dy_neighbor == 0: continue

                        cover_obj_x, cover_obj_y = spot_x + adj_dx_neighbor, spot_y + adj_dy_neighbor
                        if not (0 <= cover_obj_x < WORLD_WIDTH and 0 <= cover_obj_y < WORLD_HEIGHT): continue

                        cover_obj_tile = self.get_tile_at(cover_obj_x, cover_obj_y)
                        if not cover_obj_tile: continue

                        tile_cover_value = 0
                        if hasattr(cover_obj_tile, 'provides_cover_value'):
                            tile_cover_value = cover_obj_tile.provides_cover_value

                        if tile_cover_value > 0:
                            dist_sq_threat_to_spot = (spot_x - threat_x)**2 + (spot_y - threat_y)**2
                            dist_sq_threat_to_cover_obj = (cover_obj_x - threat_x)**2 + (cover_obj_y - threat_y)**2

                            if dist_sq_threat_to_cover_obj < dist_sq_threat_to_spot:
                                current_max_cover_value_for_spot = max(current_max_cover_value_for_spot, tile_cover_value)

                if current_max_cover_value_for_spot > 0:
                    euclidean_dist_sq_to_npc = spot_dx*spot_dx + spot_dy*spot_dy
                    candidate_spots.append({
                        'x': spot_x, 'y': spot_y,
                        'cover': current_max_cover_value_for_spot,
                        'dist_sq': euclidean_dist_sq_to_npc
                    })

        if not candidate_spots:
            return None, None

        candidate_spots.sort(key=lambda s: (-s['cover'], s['dist_sq']))

        return candidate_spots[0]['x'], candidate_spots[0]['y']

    def _update_npc_relationships_dynamic(self):
        """Periodically updates NPC relationships based on interactions, personality, and random chance."""
        if self.game_time % DAY_LENGTH_TICKS != 0: # Run once a day
            return

        for npc in self.village_npcs:
            if npc.physical.is_dead: continue

            # Decay/Growth towards baseline
            for target_id in list(npc.social.relationships.keys()):
                current_score = npc.social.relationships[target_id]

                # Decay logic: Drift towards 50 (neutral) if no recent significant interaction
                # This is a slow drift.
                if current_score > 50:
                    npc.social.relationships[target_id] = max(50, current_score - 1)
                elif current_score < 50:
                    npc.social.relationships[target_id] = min(50, current_score + 1)

            # Random relationship events
            if random.random() < 0.1: # 10% chance per day for a random social event
                other_npc = random.choice(self.village_npcs)
                if other_npc.id != npc.id and not other_npc.physical.is_dead:
                    # Check compatibility (simple personality check for now)
                    compatibility = 0
                    if npc.social.personality == other_npc.social.personality:
                        compatibility = 10

                    current_rel = npc.social.relationships.get(other_npc.id, 50)

                    # "Breakup" or fallout logic
                    if current_rel > 70 and random.random() < 0.05: # 5% chance for friends to fight
                        change = -20
                        self.add_message_to_chat_log(f"{npc.name} and {other_npc.name} had a falling out.")
                    # "Making up" logic
                    elif current_rel < 30 and random.random() < 0.05: # 5% chance for enemies to make up
                        change = 20
                        self.add_message_to_chat_log(f"{npc.name} and {other_npc.name} seem to be getting along better.")
                    else:
                        # General random fluctuation based on compatibility
                        change = random.randint(-5, 5) + compatibility

                    new_rel = max(0, min(100, current_rel + change))
                    npc.social.relationships[other_npc.id] = new_rel
                    other_npc.social.relationships[npc.id] = new_rel # Assuming symmetric for simple events

                    # Check for romantic breakup
                    partner_id = npc.social.family_ties.get("partner_id")
                    if partner_id == other_npc.id and new_rel < 30:
                        del npc.social.family_ties["partner_id"]
                        if "partner_id" in other_npc.social.family_ties:
                            del other_npc.social.family_ties["partner_id"]
                        self.add_message_to_chat_log(f"{npc.name} and {other_npc.name} have broken up.")

                        # Move out logic (simplified: if living together, one leaves)
                        if npc.schedule.home_building_id and npc.schedule.home_building_id == other_npc.schedule.home_building_id:
                             # Remove npc from current home residents
                             old_home = self.buildings_by_id.get(npc.schedule.home_building_id)
                             if old_home and npc in old_home.residents:
                                 old_home.residents.remove(npc)

                             npc.schedule.home_building_id = None # Become homeless momentarily
                             self.add_message_to_chat_log(f"{npc.name} has moved out.")

                             # Try to find a new vacant home
                             village = self._get_village_for_npc(npc)
                             if village:
                                 vacant_homes = [b for b in village.buildings if b.category == "residential" and not b.residents]
                                 if vacant_homes:
                                     new_home = random.choice(vacant_homes)
                                     npc.schedule.home_building_id = new_home.id
                                     new_home.residents.append(npc)
                                     self.add_message_to_chat_log(f"{npc.name} has found a new home.")

    def _update_npc_schedules(self):
        """
        Periodically updates NPC tasks based on game time and current state.
        Also handles routing to combat AI if NPC is hostile.
        """
        self._update_npc_relationships_dynamic()

        for npc in self.village_npcs + self.npcs:
            if npc.physical.is_dead:
                continue

            current_time_in_day = self.game_time % DAY_LENGTH_TICKS
            time_of_day_str = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)

            # --- NPC NEEDS AND STATUS UPDATE ---
            self._update_npc_temperature(npc)
            self._apply_temperature_effects(npc)
            if npc.economic.profession != "Creature":
                npc.physical.hunger = min(npc.physical.max_hunger, npc.physical.hunger + 2)
                npc.physical.thirst = min(npc.physical.max_thirst, npc.physical.thirst + 3)

            if self.game_time - npc.schedule.game_time_last_updated < NPC_SCHEDULE_UPDATE_INTERVAL:
                if npc.combat.is_hostile_to_player:
                    pass
                else:
                    continue

            npc.schedule.game_time_last_updated = self.game_time
            self._update_npc_fov(npc)

            # --- Mourning and Investigating Tasks ---
            if npc.schedule.current_task in ["mourning", "investigating"]:
                if npc.task_timer > 0:
                    npc.task_timer -= 1
                else:
                    npc.schedule.current_task = "idle"
                    npc.task_target_coords = None
                continue # Skip normal scheduling

            # --- FEAR SYSTEM (High Priority) ---
            can_be_frightened = (npc.economic.profession != "Creature" and
                                 not npc.combat.is_hostile_to_player and
                                 npc.schedule.current_task not in ["fleeing_from_threat", "alerting_guards", "combat_action_flee_from_player"])

            if can_be_frightened and npc.id in self.npc_fov_maps:
                fov_map = self.npc_fov_maps[npc.id]
                visible_npcs = [
                    other_npc for other_npc in self.npcs + self.village_npcs
                    if other_npc.id != npc.id and not other_npc.physical.is_dead and 0 <= other_npc.x < WORLD_WIDTH and 0 <= other_npc.y < WORLD_HEIGHT and fov_map[other_npc.x, other_npc.y]
                ]
                visible_wolves = [vn for vn in visible_npcs if isinstance(vn, Animal) and vn.animal_type == "wolf"]
                if len(visible_wolves) >= 2:
                    if not npc.is_frightened:
                        npc.is_frightened = True
                        npc.threat_source_ids = [wolf.id for wolf in visible_wolves]
                        self.add_message_to_chat_log(f"{npc.name} sees a wolf pack and is terrified!")
                        npc.schedule.current_path = []

            if npc.is_frightened:
                threats_still_visible = False
                if npc.id in self.npc_fov_maps:
                    fov_map = self.npc_fov_maps[npc.id]
                    for threat_id in npc.threat_source_ids:
                        # Check both lists for the threat
                        threat = next((n for n in self.npcs if n.id == threat_id), None)
                        if not threat:
                            threat = next((n for n in self.village_npcs if n.id == threat_id), None)

                        if threat and not threat.physical.is_dead and 0 <= threat.x < WORLD_WIDTH and 0 <= threat.y < WORLD_HEIGHT and fov_map[threat.x, threat.y]:
                            threats_still_visible = True
                            break
                if threats_still_visible:
                    if npc.economic.profession in ["Guard", "Sheriff"]:
                        if npc.schedule.current_task == "alerting_guards" and (not npc.schedule.current_path or len(npc.schedule.current_path) <= 1):
                            self.add_message_to_chat_log(f"{npc.name} raises the alarm about the threat!")
                            npc.combat.is_hostile_to_player = True
                            for other_npc in self.village_npcs:
                                if other_npc.id != npc.id and other_npc.economic.profession in ["Guard", "Sheriff"]:
                                    if abs(npc.x - other_npc.x) + abs(npc.y - other_npc.y) <= 15:
                                        other_npc.combat.is_hostile_to_player = True
                                        self.add_message_to_chat_log(f"{other_npc.name} hears the alarm and prepares for battle!")
                        elif npc.schedule.current_task != "alerting_guards":
                            npc.schedule.current_task = "alerting_guards"
                            npc_village = self._get_village_for_npc(npc)
                            alarm_spot = npc_village.interaction_points.get("town_square_center") if npc_village else None
                            if alarm_spot:
                                dest_x, dest_y = self._find_best_adjacent_tile(alarm_spot[0], alarm_spot[1], npc)
                                if dest_x is not None:
                                    path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                                    if path:
                                        npc.schedule.current_path = path
                                        npc.schedule.current_destination_coords = (dest_x, dest_y)
                    else:
                        if npc.schedule.current_task != "fleeing_from_threat":
                            npc.schedule.current_task = "fleeing_from_threat"
                            safe_spot = self.buildings_by_id.get(npc.schedule.home_building_id) or self._find_nearest_tavern(npc)
                            if safe_spot:
                                dest_x, dest_y = self._find_best_adjacent_tile(safe_spot.global_center_x, safe_spot.global_center_y, npc)
                                if dest_x is not None:
                                    path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                                    if path:
                                        npc.schedule.current_path = path
                                        npc.schedule.current_destination_coords = (dest_x, dest_y)
                else:
                    npc.is_frightened = False
                    npc.threat_source_ids = []
                    npc.schedule.current_task = "idle"
                    npc.schedule.current_path = []
                    self.add_message_to_chat_log(f"{npc.name} calms down as the threat is gone.")
                continue

            if npc.combat.is_hostile_to_player:
                self._handle_npc_combat_turn(npc)
                # If creature is not actively pathing from combat AI (e.g. holding, or just attacked)
                # and not investigating a sound, they could wander a bit.
                if not npc.schedule.current_path and npc.schedule.current_task not in ["investigating_sound", "combat_action_attack_player"]:
                    if random.random() < 0.1: # Small chance to wander if not actively fighting/pathing
                        dx, dy = random.choice([(0,1), (0,-1), (1,0), (-1,0)])
                        potential_x, potential_y = npc.x + dx, npc.y + dy
                        target_tile = self.get_tile_at(potential_x, potential_y)
                        if target_tile and target_tile.passable:
                            npc.schedule.current_path = [(npc.x, npc.y), (potential_x, potential_y)]
                            npc.schedule.current_destination_coords = (potential_x, potential_y)
                            npc.schedule.current_task = "wandering_hostile" # A specific task if needed

            # --- Sound Perception (runs for all NPCs, might make non-hostile investigate or hostile change target/behavior) ---
            heard_compelling_sound = False
            if self.sound_events:
                for sound in self.sound_events:
                    if sound.get("source_id") and sound["source_id"] == npc.id: continue

                    dist_to_sound = math.sqrt((npc.x - sound["x"])**2 + (npc.y - sound["y"])**2)
                    if dist_to_sound <= npc.hearing_radius and dist_to_sound <= sound["volume"]:
                        if npc.schedule.current_task not in ["combat_action_attack_player", "combat_action_flee_from_player", "combat_action_move_to_attack_player", "investigating_sound"]:
                            sound_type = sound["type"]
                            if sound_type in ["combat_attack", "tree_fall"]: # Hostile creatures also investigate these
                                npc.schedule.current_task = "investigating_sound"
                                npc.schedule.current_destination_coords = (sound["x"], sound["y"])
                                npc.schedule.current_path = []
                                self.add_message_to_chat_log(f"{npc.name} heard a {sound_type} and looks towards it.")
                                heard_compelling_sound = True
                                break

            if heard_compelling_sound:
                if npc.schedule.current_task == "investigating_sound" and npc.schedule.current_destination_coords and not npc.schedule.current_path:
                    path = self.calculate_path(npc.x, npc.y, npc.schedule.current_destination_coords[0], npc.schedule.current_destination_coords[1])
                    if path: npc.schedule.current_path = path
                    else: npc.schedule.current_task = "idle_confused"; npc.schedule.current_destination_coords = None

            # --- Animal Behavior (Predator & Prey) ---
            elif isinstance(npc, Animal):
                animal_def = ANIMAL_DEFINITIONS.get(npc.animal_type, {})

                # 1. PREDATOR AI (Highest Priority)
                is_predator = "prey" in animal_def
                is_hungry_predator = is_predator and npc.physical.hunger >= npc.physical.max_hunger * 0.7
                if is_hungry_predator or npc.schedule.current_task == "hunting":
                    if npc.schedule.current_task != "hunting":
                        # Find nearest prey
                        nearest_prey = None
                        min_dist_sq = float('inf')
                        for other_npc in self.npcs:
                            if other_npc.id != npc.id and isinstance(other_npc, Animal) and other_npc.animal_type in animal_def.get("prey", []):
                                dist_sq = (npc.x - other_npc.x)**2 + (npc.y - other_npc.y)**2
                                if dist_sq < min_dist_sq and dist_sq < 20**2:
                                    min_dist_sq = dist_sq
                                    nearest_prey = other_npc
                        if nearest_prey:
                            npc.schedule.current_task = "hunting"
                            npc.task_target_entity_id = nearest_prey.id
                            # self.add_message_to_chat_log(f"The {npc.name} has caught the scent of a {nearest_prey.name} and begins to hunt.")

                    if npc.schedule.current_task == "hunting":
                        prey = self._get_predator_target(npc)
                        if prey and not prey.physical.is_dead:
                            distance_to_prey = abs(npc.x - prey.x) + abs(npc.y - prey.y)
                            attack_range = getattr(npc, 'attack_range', 1)
                            if distance_to_prey <= attack_range:
                                print(f"DEBUG: {npc.name} attacking {prey.name} at tick {self.game_time}")
                                self.npc_attempt_attack_npc(npc, prey)
                                npc.schedule.current_path = []
                                npc.schedule.current_destination_coords = None
                            else:
                                if not npc.schedule.current_path or npc.schedule.current_destination_coords != (prey.x, prey.y):
                                    path = self.calculate_path(npc.x, npc.y, prey.x, prey.y)
                                    if path:
                                        npc.schedule.current_path = path
                                        npc.schedule.current_destination_coords = (prey.x, prey.y)
                        else:
                            npc.schedule.current_task = "idle"
                            npc.task_target_entity_id = None
                        continue

                # 2. PREY/FLEEING AI (Second Priority)
                flee_radius = 15
                should_flee = False
                threat = None
                distance_to_player = math.sqrt((npc.x - self.player.x)**2 + (npc.y - self.player.y)**2)
                if distance_to_player < flee_radius:
                    should_flee = True
                    threat = self.player

                if not should_flee:
                    for other_npc in self.npcs:
                        if other_npc.id != npc.id and isinstance(other_npc, Animal) and other_npc.animal_type in animal_def.get("predators", []):
                            distance_to_predator = math.sqrt((npc.x - other_npc.x)**2 + (npc.y - other_npc.y)**2)
                            if distance_to_predator < flee_radius:
                                should_flee = True
                                threat = other_npc
                                break

                if should_flee and threat:
                    if npc.schedule.current_task != "fleeing":
                        self.add_message_to_chat_log(f"The {npc.name} spots the {threat.name if hasattr(threat, 'name') else 'player'} and bolts!")
                        npc.schedule.current_task = "fleeing"

                    dx = npc.x - threat.x
                    dy = npc.y - threat.y
                    dist = math.sqrt(dx*dx + dy*dy)
                    if dist > 0:
                        flee_x = npc.x + int(dx/dist * flee_radius)
                        flee_y = npc.y + int(dy/dist * flee_radius)
                        flee_x = max(0, min(WORLD_WIDTH - 1, flee_x))
                        flee_y = max(0, min(WORLD_HEIGHT - 1, flee_y))
                        path = self.calculate_path(npc.x, npc.y, flee_x, flee_y)
                        if path:
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = (flee_x, flee_y)
                    continue

                if npc.schedule.current_task == "fleeing" and not should_flee:
                    npc.schedule.current_task = "idle"

                # 3. TERRITORIAL and NEUTRAL BEHAVIORS
                if npc.behavior == "Territorial":
                    if not npc.den_location:
                        npc.den_location = (npc.x, npc.y)

                    dist_to_den = math.sqrt((self.player.x - npc.den_location[0])**2 + (self.player.y - npc.den_location[1])**2)
                    if dist_to_den < 10 and not npc.combat.is_hostile_to_player:
                        self.add_message_to_chat_log(f"The {npc.name} becomes aggressive as you approach its den!")
                        npc.combat.is_hostile_to_player = True

                elif npc.behavior == "Wander-Neutral":
                    dist_to_player = math.sqrt((npc.x - self.player.x)**2 + (npc.y - self.player.y)**2)
                    if dist_to_player < 3 and not npc.combat.is_hostile_to_player:
                        self.add_message_to_chat_log(f"The {npc.name} feels threatened and becomes hostile!")
                        npc.combat.is_hostile_to_player = True

                # 4. OTHER BEHAVIORS (Lower Priority)
                if npc.is_pregnant:
                    npc.pregnancy_timer -= 1
                    if npc.pregnancy_timer <= 0:
                        npc.is_pregnant = False
                        spawn_x, spawn_y = self._find_best_adjacent_tile(npc.x, npc.y, npc)
                        if spawn_x is not None:
                            new_animal = Animal(spawn_x, spawn_y, name=f"Baby {npc.animal_type}", animal_type=npc.animal_type)
                            new_animal.char = ord(animal_def.get("char", 'a').lower())
                            new_animal.color = animal_def.get("color")
                            new_animal.max_hp = animal_def.get("max_hp", 10) // 2
                            new_animal.hp = new_animal.max_hp
                            new_animal.behavior = "Wander-Flee"
                            new_animal.gender = random.choice(["male", "female"])
                            self.npcs.append(new_animal)
                            self.add_message_to_chat_log(f"A baby {npc.animal_type} has been born!")
                        else:
                            npc.pregnancy_timer = 1

                if npc.behavior == "Follow-Owner" and npc.owner == self.player:
                    distance_to_player = math.sqrt((npc.x - self.player.x)**2 + (npc.y - self.player.y)**2)
                    if distance_to_player > 3 and not npc.schedule.current_path:
                        target_x, target_y = self._find_best_adjacent_tile(self.player.x, self.player.y, npc)
                        if target_x is not None:
                            path = self.calculate_path(npc.x, npc.y, target_x, target_y)
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = (target_x, target_y)
                                npc.schedule.current_task = "following"

                elif animal_def.get("can_mate") and animal_def.get("mating_season") == self.seasons[self.current_season_index] and not npc.is_pregnant:
                    if npc.schedule.current_task not in ["seeking_mate", "mating"]:
                        for other_npc in self.npcs:
                            if isinstance(other_npc, Animal) and other_npc.id != npc.id and \
                               other_npc.animal_type == npc.animal_type and other_npc.gender != npc.gender and \
                               not other_npc.is_pregnant:
                                distance_to_mate = math.sqrt((npc.x - other_npc.x)**2 + (npc.y - other_npc.y)**2)
                                if distance_to_mate < 20:
                                    npc.schedule.current_task = "seeking_mate"
                                    npc.task_target_entity_id = other_npc.id
                                    break

                    if npc.schedule.current_task == "seeking_mate" and npc.task_target_entity_id:
                        mate = next((n for n in self.npcs if n.id == npc.task_target_entity_id), None)
                        if mate:
                            distance_to_mate = math.sqrt((npc.x - mate.x)**2 + (npc.y - mate.y)**2)
                            if distance_to_mate <= 1:
                                if npc.gender == "female":
                                    npc.is_pregnant = True
                                    npc.pregnancy_timer = animal_def.get("gestation_period_days", 7) * DAY_LENGTH_TICKS
                                    self.add_message_to_chat_log(f"A wild {npc.animal_type} has become pregnant.")
                                npc.schedule.current_task = "idle"
                            else:
                                target_x, target_y = self._find_best_adjacent_tile(mate.x, mate.y, npc)
                                if target_x is not None:
                                    path = self.calculate_path(npc.x, npc.y, target_x, target_y)
                                    if path:
                                        npc.schedule.current_path = path
                                        npc.schedule.current_destination_coords = (target_x, target_y)

                elif npc.schedule.current_task in ["idle", "wandering"] and not npc.schedule.current_path:
                    # Hunger increases when idle
                    if npc.physical.hunger < npc.physical.max_hunger:
                        npc.physical.hunger += 1

                    if random.random() < 0.2:
                        dx, dy = random.choice([(0,1), (0,-1), (1,0), (-1,0)])
                        potential_x, potential_y = npc.x + dx, npc.y + dy
                        target_tile = self.get_tile_at(potential_x, potential_y)
                        if target_tile and target_tile.passable:
                            if npc.behavior == "Wander-Water" and target_tile.name not in ["Water", "Deep Water"]:
                                continue
                            npc.schedule.current_path = [(npc.x, npc.y), (potential_x, potential_y)]
                            npc.schedule.current_destination_coords = (potential_x, potential_y)
                            npc.schedule.current_task = "wandering"

            # Standard scheduling logic ONLY if NOT hostile by default (e.g. not a Creature) AND not investigating a sound
            elif npc.economic.profession != "Creature" and not npc.combat.is_hostile_to_player and \
                 npc.schedule.current_task not in ["attacking_player", "moving_to_attack_player", "fleeing_from_player",
                                          "holding_position_combat", "combat_action_use_healing_item",
                                          "combat_action_move_to_cover", "investigating_sound"]:

                # --- Temperature-based Warmth Seeking (High Priority) ---
                if "Freezing" in npc.physical.status_effects and npc.schedule.current_task != "seeking_warmth":
                    npc.schedule.previous_task = npc.schedule.current_task if npc.schedule.current_task not in ["idle", "wandering"] else "idle"
                    npc.schedule.current_task = "seeking_warmth"
                    heat_source_coords = self._find_nearest_heat_source(npc)
                    if heat_source_coords:
                        dest_x, dest_y = self._find_best_adjacent_tile(heat_source_coords[0], heat_source_coords[1], npc)
                        if dest_x is not None:
                            path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = (dest_x, dest_y)
                    else:
                        # Fallback: huddle indoors at home
                        home_building = self.buildings_by_id.get(npc.schedule.home_building_id)
                        if home_building:
                            home_coords = (home_building.global_center_x, home_building.global_center_y)
                            path = self.calculate_path(npc.x, npc.y, home_coords[0], home_coords[1])
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = home_coords
                                npc.schedule.current_task = "huddling_indoors"

                # --- Weather-based Shelter Seeking ---
                is_bad_weather = self.weather in ["rain", "snow"]
                npc_is_sheltered = self._check_for_shelter(npc.x, npc.y)

                if is_bad_weather and not npc_is_sheltered and npc.schedule.current_task != "seeking_shelter":
                    npc.schedule.previous_task = npc.schedule.current_task if npc.schedule.current_task not in ["idle", "wandering"] else "idle"
                    npc.schedule.current_task = "seeking_shelter"
                    # Find shelter: home first, then tavern
                    shelter_building = self.buildings_by_id.get(npc.schedule.home_building_id)
                    if not shelter_building:
                        shelter_building = self._find_nearest_tavern(npc)

                    if shelter_building:
                        shelter_coords = (shelter_building.global_center_x, shelter_building.global_center_y)
                        path = self.calculate_path(npc.x, npc.y, shelter_coords[0], shelter_coords[1])
                        if path:
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = shelter_coords
                elif not is_bad_weather and npc.schedule.current_task == "seeking_shelter":
                    # Weather cleared, resume previous task
                    npc.schedule.current_task = npc.schedule.previous_task or "idle"
                    npc.schedule.previous_task = None
                    npc.schedule.current_path = []
                    npc.schedule.current_destination_coords = None


                needs_based_action_taken = False

                # --- Proactive Help-Seeking & Quest Generation ---
                if not needs_based_action_taken and not hasattr(npc, 'active_quest') and random.random() < 0.1:
                    critically_hungry = npc.physical.hunger >= 90
                    critically_thirsty = npc.physical.thirst >= 90

                    if critically_hungry or critically_thirsty:
                        knows_food_source = "the tavern" in npc.knowledge.known_locations or "bakery" in npc.knowledge.known_locations
                        knows_water_source = "the village well" in npc.knowledge.known_locations

                        needs_help = False
                        quest_item, quest_count, quest_type_for_help = None, 0, None

                        if critically_hungry and not knows_food_source:
                            npc.knowledge.help_needed = "food"
                            needs_help = True
                            quest_item = "raw_fish" # Example item
                            quest_count = random.randint(3, 5)
                            quest_type_for_help = "food"
                        elif critically_thirsty and not knows_water_source:
                            npc.knowledge.help_needed = "water"
                            needs_help = True
                            # Water is not an inventory item, so this is a placeholder.
                            # A real water quest might be "fix the well" or similar.
                            # For now, we'll make it a food quest as a fallback.
                            quest_item = "bread"
                            quest_count = 1
                            quest_type_for_help = "thirst" # Still indicates the root cause

                        if needs_help and quest_item:
                            quest_id = f"fetch_{quest_item}_{npc.id}_{self.game_time}"
                            quest = Quest(
                                quest_id=quest_id,
                                title=f"A Desperate Need for {quest_item.replace('_', ' ').title()}",
                                description=f"{npc.name} is in dire need of {quest_count} {quest_item.replace('_', ' ')}.",
                                quest_type="fetch",
                                quest_giver_id=npc.id
                            )
                            quest.item_key = quest_item
                            quest.required_count = quest_count
                            setattr(npc, 'active_quest', quest) # Attach the quest to the NPC
                            self.add_message_to_chat_log(f"Debug: {npc.name} generated quest '{quest.title}'.")


                        if needs_help and npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.x, self.player.y]:
                            npc.schedule.current_task = "approaching_player_for_help"
                            dest_x, dest_y = self._find_best_adjacent_tile(self.player.x, self.player.y, npc)
                            if dest_x is not None:
                                path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                                if path:
                                    npc.schedule.current_path = path
                                    npc.schedule.current_destination_coords = (dest_x, dest_y)
                                    needs_based_action_taken = True

                # --- Crime Reporting Task ---
                if npc.schedule.current_task == "going_to_report_crime":
                    if npc.task_target_coords:
                        # Check if at the sheriff's office
                        if (npc.x, npc.y) == npc.task_target_coords:
                            self.add_message_to_chat_log(f"{npc.name} reports your crimes to the authorities!")
                            self.player.economic.bounty += 50 # Example bounty increase
                            self.add_message_to_chat_log(f"Your bounty has increased by 50. Total bounty: {self.player.economic.bounty}.")
                            npc.schedule.current_task = "idle" # Or return to previous task
                            npc.task_target_coords = None
                        else:
                            # Path to the sheriff's office if not already pathing
                            if not npc.schedule.current_path or npc.schedule.current_destination_coords != npc.task_target_coords:
                                path = self.calculate_path(npc.x, npc.y, npc.task_target_coords[0], npc.task_target_coords[1])
                                if path:
                                    npc.schedule.current_path = path
                                    npc.schedule.current_destination_coords = npc.task_target_coords
                                else:
                                    npc.schedule.current_task = "idle_confused" # Can't reach the office
                    needs_based_action_taken = True


                # --- Thirst Fulfillment ---
                if not needs_based_action_taken and (npc.physical.thirst >= 70 or npc.schedule.current_task == "seeking_water"):
                    if npc.schedule.current_task != "seeking_water":
                        npc.schedule.previous_task = npc.schedule.current_task if npc.schedule.current_task not in ["idle", "wandering"] else "idle"
                        npc.schedule.current_task = "seeking_water"

                    npc_village = self._get_village_for_npc(npc)
                    if npc_village and "well" in npc_village.interaction_points and npc_village.interaction_points["well"]:
                        well_coords = npc_village.interaction_points["well"][0] # Assume one well for now
                        if (npc.x, npc.y) == well_coords:
                            npc.physical.thirst = 0
                            # self.add_message_to_chat_log(f"{npc.name} drinks from the well and is no longer thirsty.")
                            npc.schedule.current_task = npc.schedule.previous_task or "idle"
                            npc.schedule.previous_task = None
                        else:
                            # Path to the well if not already pathing
                            if not npc.schedule.current_path or npc.schedule.current_destination_coords != well_coords:
                                path = self.calculate_path(npc.x, npc.y, well_coords[0], well_coords[1])
                                if path:
                                    npc.schedule.current_path = path
                                    npc.schedule.current_destination_coords = well_coords
                                else:
                                    npc.schedule.current_task = "idle_confused" # Can't reach the well
                    needs_based_action_taken = True

                # --- Hunger Fulfillment ---
                elif npc.physical.hunger >= 70 or npc.schedule.current_task == "seeking_food":
                    if not needs_based_action_taken and npc.schedule.current_task != "seeking_food":
                        npc.schedule.previous_task = npc.schedule.current_task if npc.schedule.current_task not in ["idle", "wandering"] else "idle"
                        npc.schedule.current_task = "seeking_food"

                    # 1. Try eating from personal inventory first
                    found, consumed = self._npc_eat_from_inventory(npc, npc.economic.npc_inventory, is_building_inventory=False)
                    if consumed:
                        npc.schedule.current_task = npc.schedule.previous_task or "idle"
                        npc.schedule.previous_task = None
                    else:
                        # 2. If no food in pack, try to go home to eat
                        home_building = self.buildings_by_id.get(npc.schedule.home_building_id)
                        if home_building:
                            is_at_home = (npc.x, npc.y) == (home_building.global_center_x, home_building.global_center_y) # Simplified check
                            if is_at_home:
                                found_home, consumed_home = self._npc_eat_from_inventory(npc, home_building.building_inventory, is_building_inventory=True)
                                if consumed_home:
                                    npc.schedule.current_task = npc.schedule.previous_task or "idle"
                                    npc.schedule.previous_task = None
                                else:
                                    # At home, but no food. What to do now?
                                    # self.add_message_to_chat_log(f"{npc.name} is hungry at home, but there is no food.")
                                    npc.schedule.current_task = "wandering_hungry" # A new state
                                    npc.schedule.previous_task = None
                            else:
                                # Not at home, check if there's food there before pathing
                                has_food_at_home = any(ITEM_DEFINITIONS.get(k,{}).get("on_use",{}).get("reduces_hunger",0) > 0 for k,v in home_building.building_inventory.items() if v > 0)
                                if has_food_at_home:
                                    home_coords = (home_building.global_center_x, home_building.global_center_y)
                                    if not npc.schedule.current_path or npc.schedule.current_destination_coords != home_coords:
                                        path = self.calculate_path(npc.x, npc.y, home_coords[0], home_coords[1])
                                        if path:
                                            npc.schedule.current_path = path
                                            npc.schedule.current_destination_coords = home_coords
                                        else:
                                            npc.schedule.current_task = "idle_confused" # Can't path home
                                else:
                                    # No food at home, try to buy food if they have money
                                    if npc.economic.money > 10: # Arbitrary threshold to decide to buy food
                                        food_vendor_building = self._find_nearest_food_vendor(npc)
                                        if food_vendor_building:
                                            npc.schedule.current_task = "going_to_buy_food"
                                            vendor_coords = (food_vendor_building.global_center_x, food_vendor_building.global_center_y)
                                            if not npc.schedule.current_path or npc.schedule.current_destination_coords != vendor_coords:
                                                path = self.calculate_path(npc.x, npc.y, vendor_coords[0], vendor_coords[1])
                                                if path:
                                                    npc.schedule.current_path = path
                                                    npc.schedule.current_destination_coords = vendor_coords
                                                else:
                                                    npc.schedule.current_task = "idle_confused" # Can't path to vendor
                                        else:
                                            # No vendor, wander hungry
                                            npc.schedule.current_task = "wandering_hungry"
                                    else:
                                        # No food at home and not enough money
                                        npc.schedule.current_task = "wandering_hungry"
                                    npc.schedule.previous_task = None
                        else:
                            # Homeless and hungry.
                            npc.schedule.current_task = "wandering_hungry_homeless"

                    needs_based_action_taken = True
                elif npc.schedule.current_task == "going_to_buy_food":
                    food_vendor_building = self._find_nearest_food_vendor(npc)
                    if food_vendor_building and (npc.x, npc.y) == (food_vendor_building.global_center_x, food_vendor_building.global_center_y):
                        # At the vendor, attempt to buy food
                        food_to_buy = None
                        food_price = 0
                        village = self._get_village_for_npc(npc)
                        for item_key, quantity in food_vendor_building.building_inventory.items():
                            if quantity > 0:
                                item_def = ITEM_DEFINITIONS.get(item_key, {})
                                if item_def.get("on_use", {}).get("reduces_hunger", 0) > 0:
                                    food_to_buy = item_key
                                    food_price = self.get_dynamic_price(item_key, village)
                                    break

                        if food_to_buy and npc.economic.money >= food_price:
                            food_vendor_building.building_inventory[food_to_buy] -= 1
                            npc.economic.money -= food_price
                            npc.economic.npc_inventory[food_to_buy] = npc.economic.npc_inventory.get(food_to_buy, 0) + 1
                            # self.add_message_to_chat_log(f"{npc.name} bought a {food_to_buy} for {food_price} coins.")
                            # Now that food is in inventory, the main hunger logic will handle eating it next tick
                            npc.schedule.current_task = "seeking_food"
                        else:
                            # No food to buy or can't afford it
                            npc.schedule.current_task = "wandering_hungry"
                    needs_based_action_taken = True


                # --- NPC Item Pickup Decision ---
                # This decision should happen before regular scheduling if items are perceived.
                made_item_decision = False
                if npc.knowledge.perceived_item_tiles and npc.schedule.current_task in ["idle", "wandering", "at home", "at work"]: # Can decide to pickup even at work/home if item is compelling
                    perceived_items_list = []
                    for item_x, item_y in npc.knowledge.perceived_item_tiles:
                        if (item_x, item_y) in self.items_on_map and self.items_on_map[(item_x, item_y)]:
                            # For simplicity, consider the first item on the tile for the prompt
                            # A more complex NPC might evaluate all items on a tile.
                            item_on_tile = self.items_on_map[(item_x, item_y)][0]
                            item_def = ITEM_DEFINITIONS.get(item_on_tile["item_key"])
                            if item_def:
                                perceived_items_list.append({
                                    "item_key": item_on_tile["item_key"],
                                    "name": item_def.get("name", item_on_tile["item_key"]),
                                    "quantity": item_on_tile["quantity"],
                                    "distance": abs(npc.x - item_x) + abs(npc.y - item_y), # Manhattan
                                    "coords": [item_x, item_y]
                                })

                    if perceived_items_list:
                        # Summarize inventory for the prompt (e.g., first 3-5 item names)
                        inventory_summary_parts = []
                        count = 0
                        for key, quant in npc.economic.npc_inventory.items():
                            if count < 5:
                                inventory_summary_parts.append(f"{quant}x {ITEM_DEFINITIONS.get(key, {}).get('name', key)}")
                                count +=1
                            else:
                                inventory_summary_parts.append("...")
                                break
                        inventory_summary = ", ".join(inventory_summary_parts) if inventory_summary_parts else "empty"

                        pickup_prompt = LLM_PROMPTS["npc_item_pickup_decision"].format(
                            npc_name=npc.name,
                            npc_personality=npc.social.personality,
                            npc_current_task=npc.schedule.current_task,
                            npc_inventory_summary=inventory_summary,
                            npc_equipped_weapon_name=ITEM_DEFINITIONS.get(npc.equipment.weapon, {}).get("name", "None") if npc.equipment.weapon else "None",
                            npc_equipped_armor_name=ITEM_DEFINITIONS.get(npc.equipment.body, {}).get("name", "None") if npc.equipment.body else "None",
                            perceived_items_list_str=json.dumps(perceived_items_list, indent=2) # Pretty print for LLM
                        )
                        pickup_response_str = self._call_ollama(pickup_prompt)
                        if pickup_response_str:
                            try:
                                pickup_decision = json.loads(pickup_response_str)
                                action = pickup_decision.get("action")
                                reasoning = pickup_decision.get("reasoning", f"{npc.name} considers the items.")

                                # Log reasoning if player can hear/see (simplified check)
                                dist_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y)
                                if dist_to_player <= self.player.physical.hearing_radius and dist_to_player <= npc.speech_volume and \
                                   (npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.x, self.player.y]): # visible
                                    self.add_message_to_chat_log(f"({reasoning})")


                                if action == "pickup_item":
                                    target_coords_list = pickup_decision.get("target_coords")
                                    item_key_to_pickup = pickup_decision.get("item_key_to_pickup")
                                    if target_coords_list and item_key_to_pickup:
                                        npc.schedule.current_task = "task_going_to_pickup_item"
                                        npc.task_target_coords = tuple(target_coords_list)
                                        npc.task_target_item_details = {"item_key": item_key_to_pickup}
                                        npc.schedule.current_path = [] # Clear path for new task
                                        made_item_decision = True
                                        # self.add_message_to_chat_log(f"Debug: {npc.name} decided to pick up {item_key_to_pickup} at {target_coords_list}.")
                            except json.JSONDecodeError:
                                # self.add_message_to_chat_log(f"Error decoding item pickup decision for {npc.name}: {pickup_response_str}")
                                pass # Fall through to regular scheduling

                # Original scheduling logic starts here, only if no item pickup decision was made
                if not made_item_decision and not needs_based_action_taken and npc.schedule.current_task in ["idle", "at home", "at work", "idle_confused", "wandering"] and not npc.schedule.current_path:
                    current_time_in_day = self.game_time % DAY_LENGTH_TICKS
                    time_of_day_str = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)

                new_task_label = None
                llm_chosen_goal = None # e.g. "Go to work"
                destination_coords = None

                # --- Determine NPC's location status ---
                is_at_home = False
                if npc.schedule.home_building_id:
                    home_coords = self._get_building_global_center_coords(npc.schedule.home_building_id)
                    if home_coords and (npc.x, npc.y) == home_coords:
                        is_at_home = True

                is_at_work = False
                job_type = "Unemployed"
                if npc.schedule.work_building_id:
                    work_building = self.buildings_by_id.get(npc.schedule.work_building_id)
                    if work_building:
                        job_type = work_building.building_type # Or a more specific job role if defined
                        work_coords = (work_building.global_center_x, work_building.global_center_y)
                        if work_coords and (npc.x, npc.y) == work_coords:
                            is_at_work = True

                # --- LLM-driven Goal Selection ---
                if USE_LLM_FOR_SCHEDULES:
                    prompt = LLM_PROMPTS["npc_daily_goal"].format(
                        npc_name=npc.name,
                        npc_personality=npc.social.personality,
                        npc_current_task=npc.schedule.current_task,
                        is_at_home=is_at_home,
                        is_at_work=is_at_work,
                        has_job=bool(npc.schedule.work_building_id),
                        job_type=job_type,
                        time_of_day_str=time_of_day_str,
                        current_light_level_name=self.current_light_level_name # Pass light level
                    )
                    response_str = self._call_ollama(prompt)
                    if response_str:
                        try:
                            response_json = json.loads(response_str)
                            llm_chosen_goal = response_json.get("goal")
                            # self.add_message_to_chat_log(f"LLM choice for {npc.name}: {llm_chosen_goal}")
                        except json.JSONDecodeError:
                            # self.add_message_to_chat_log(f"LLM schedule for {npc.name} - JSON decode error: {response_str}")
                            llm_chosen_goal = "Stay put" # Fallback
                    else:
                        # self.add_message_to_chat_log(f"LLM schedule for {npc.name} - No response, defaulting to Stay put.")
                        llm_chosen_goal = "Stay put" # Fallback if LLM fails

                    # Map LLM goal to tasks and destinations
                    if llm_chosen_goal == "Go to work" and npc.schedule.work_building_id and not is_at_work:
                        dest_coords_temp = self._get_building_global_center_coords(npc.schedule.work_building_id)
                        if dest_coords_temp:
                            new_task_label = "going to work"
                            destination_coords = dest_coords_temp
                    elif llm_chosen_goal == "Go home" and npc.schedule.home_building_id and not is_at_home:
                        dest_coords_temp = self._get_building_global_center_coords(npc.schedule.home_building_id)
                        if dest_coords_temp:
                            new_task_label = "going home"
                            destination_coords = dest_coords_temp
                    elif llm_chosen_goal == "Wander the village":
                        # Pick a random passable point in the current chunk or nearby for simplicity
                        # This needs a robust implementation: find current chunk, pick random point
                        # For now, let's make them stay put if they choose to wander.
                        npc.schedule.current_task = "wandering" # No movement, just state change
                        # self.add_message_to_chat_log(f"{npc.name} is now wandering (staying put).")
                    elif llm_chosen_goal == "Stay put":
                        npc.schedule.current_task = "idle" if npc.schedule.current_task not in ["at home", "at work"] else npc.schedule.current_task
                        # self.add_message_to_chat_log(f"{npc.name} is staying put.")
                    # Add other goals like Socialize, Seek food later

                # --- Rule-based Goal Selection (Fallback or if USE_LLM_FOR_SCHEDULES is False) ---
                else:
                    work_start_tick = DAY_LENGTH_TICKS * WORK_START_TIME_RATIO
                    work_end_tick = DAY_LENGTH_TICKS * WORK_END_TIME_RATIO

                    # Payroll check at the end of the workday
                    current_day = self.game_time // DAY_LENGTH_TICKS
                    if npc.economic.profession != "Unemployed" and npc.schedule.work_building_id and npc.schedule.last_paid_day < current_day:
                        # Check if the workday is over for the current day
                        if self.game_time % DAY_LENGTH_TICKS >= work_end_tick:
                            profession_data = get_profession_data(npc.economic.profession)
                            if profession_data:
                                wage = profession_data.get("wage", 10) # Default wage if not specified
                                npc.economic.money += wage
                                npc.schedule.last_paid_day = current_day
                                # Optional: Log this event for debugging or storytelling
                                # self.add_message_to_chat_log(f"{npc.name} received {wage} coins for a day's work as a {npc.economic.profession}.")

                    # Define "night" for sleeping (e.g., last 20% of day or first 10%)
                    sleep_start_tick = DAY_LENGTH_TICKS * 0.85
                    sleep_end_tick = DAY_LENGTH_TICKS * 0.15 # Next day
                    is_night_time = current_time_in_day >= sleep_start_tick or current_time_in_day < sleep_end_tick
                    is_leisure_time = work_end_tick <= current_time_in_day < sleep_start_tick

                    # Priority: Go to work during work hours
                    if work_start_tick <= current_time_in_day < work_end_tick:
                        if npc.schedule.work_building_id and not is_at_work and npc.schedule.current_task != "going to work":
                            work_building_obj = self.buildings_by_id.get(npc.schedule.work_building_id)
                            # Future: Check for specific workstation in work_building_obj.interaction_points
                            # For now, path to building center for work.
                            dest_coords_temp = self._get_building_global_center_coords(npc.schedule.work_building_id)
                            if dest_coords_temp:
                                new_task_label = "going to work"
                                destination_coords = dest_coords_temp
                                if hasattr(npc, 'original_char_before_sleep'): npc.char = npc.original_char_before_sleep
                        elif npc.schedule.work_building_id and is_at_work:
                             npc.schedule.current_task = f"Working ({npc.economic.profession})" if npc.economic.profession != "Unemployed" else "At Work (Idle)"
                             if hasattr(npc, 'original_char_before_sleep'): npc.char = npc.original_char_before_sleep

                        # Unemployed Behavior: Look for work during "work hours"
                        elif npc.economic.profession.lower() == "unemployed" and npc.schedule.current_task != "looking_for_work":
                             if random.random() < 0.02: # Low chance each tick to decide to look for work
                                 npc_village = self._get_village_for_npc(npc)
                                 if npc_village:
                                     workplaces = [b for b in npc_village.buildings if "workplace" in b.category]
                                     if workplaces:
                                         target_workplace = random.choice(workplaces)
                                         dest_coords = (target_workplace.global_center_x, target_workplace.global_center_y)

                                         if (npc.x, npc.y) != dest_coords:
                                             new_task_label = "looking_for_work"
                                             destination_coords = dest_coords
                                             npc.leisure_timer = random.randint(50, 100) # Use timer to linger at workplace

                    # Leisure time logic
                    elif is_leisure_time and npc.schedule.current_task not in ["at leisure", "going to tavern", "socializing", "going home", "visiting friend"]:
                        if npc.leisure_timer > 0:
                            npc.leisure_timer -= 1
                        elif random.random() < 0.05: # 5% chance to go to the tavern
                            tavern = self._find_nearest_tavern(npc)
                            if tavern:
                                new_task_label = "going to tavern"
                                destination_coords = (tavern.global_center_x, tavern.global_center_y)
                        elif random.random() < 0.1: # 10% chance to just socialize with a nearby NPC
                            # Find a nearby NPC to chat with
                            potential_partners = [
                                p for p in self.village_npcs
                                if p.id != npc.id and not p.physical.is_dead and abs(npc.x - p.x) + abs(npc.y - p.y) < 20
                            ]
                            if potential_partners:
                                # Weight choice by relationship score
                                weights = [max(1, npc.social.relationships.get(p.id, 50)) for p in potential_partners]
                                chat_partner = random.choices(potential_partners, weights=weights, k=1)[0]

                                new_task_label = "socializing"
                                # Path to a tile adjacent to the partner
                                dest_x, dest_y = self._find_best_adjacent_tile(chat_partner.x, chat_partner.y, npc)
                                if dest_x is not None:
                                    destination_coords = (dest_x, dest_y)
                                    npc.task_target_entity_id = chat_partner.id
                                    npc.leisure_timer = random.randint(50, 150) # Chat for a bit
                        elif random.random() < 0.1:  # 10% chance to socialize
                            self._start_npc_socialization(npc)
                        elif random.random() < 0.05: # 5% chance to visit a friend
                            # Filter for NPCs with a positive relationship
                            friends = [n for n in self.village_npcs if n.id != npc.id and npc.social.relationships.get(n.id, 50) > 60]
                            if friends:
                                friend_to_visit = random.choice(friends)
                                if friend_to_visit.schedule.home_building_id:
                                    friend_home = self.buildings_by_id.get(friend_to_visit.schedule.home_building_id)
                                    if friend_home:
                                        new_task_label = "visiting friend"
                                        destination_coords = (friend_home.global_center_x, friend_home.global_center_y)
                                        npc.task_target_entity_id = friend_to_visit.id
                                        npc.leisure_timer = random.randint(100, 300) # Stay for a while
                        elif random.random() < 0.1: # 10% chance to act on knowledge
                            if npc.knowledge.known_locations:
                                location_name, location_coords = random.choice(list(npc.knowledge.known_locations.items()))
                                if location_coords != (npc.x, npc.y):
                                    new_task_label = f"acting on knowledge: visiting {location_name}"
                                    destination_coords = location_coords
                                    npc.leisure_timer = random.randint(100, 200)
                        elif random.random() < 0.05 or npc.economic.profession == "Fisherman": # Fishermen will also use this logic
                            npc_village = self._get_village_for_npc(npc)
                            if npc_village and "fishing_spot" in npc_village.interaction_points:
                                fishing_spot = random.choice(npc_village.interaction_points["fishing_spot"])
                                if npc.economic.profession == "Fisherman":
                                    new_task_label = "working_fishing"
                                else:
                                    new_task_label = "leisure_fishing"
                                destination_coords = fishing_spot
                                npc.leisure_timer = random.randint(100, 300)

                    if npc.schedule.current_task == "working_fishing" and (npc.x, npc.y) == destination_coords:
                        self.npc_attempt_fish(npc, npc.x, npc.y)

                    # Else, if it's night and they have a home
                    elif is_night_time and npc.schedule.home_building_id and npc.schedule.current_task not in ["sleeping", "going home to sleep"]:
                        home_building_obj = self.buildings_by_id.get(npc.schedule.home_building_id)
                        if home_building_obj:
                            sleep_spot_coords = home_building_obj.interaction_points.get("sleep_spot")
                            if is_at_home: # Already at home
                                if sleep_spot_coords and (npc.x, npc.y) == sleep_spot_coords: # At the bed
                                    npc.schedule.current_task = "sleeping"
                                    npc.original_char_before_sleep = npc.char
                                    npc.char = ord('z')
                                elif sleep_spot_coords and (npc.x, npc.y) != sleep_spot_coords: # At home, but not at bed
                                    new_task_label = "going to bed"
                                    destination_coords = sleep_spot_coords
                                elif not sleep_spot_coords and self._building_contains_item_with_interaction(home_building_obj, "sleep"):
                                    # Fallback if sleep_spot not recorded but bed exists (should not happen if decoration works)
                                    # For now, just mark as sleeping if at home center and bed exists broadly.
                                    npc.schedule.current_task = "sleeping"
                                    npc.original_char_before_sleep = npc.char
                                    npc.char = ord('z')
                                # else: npc stays "at home" if no bed / no specific sleep spot
                            else: # Not at home, but it's night -> go to bed if possible, else home center
                                if sleep_spot_coords:
                                    new_task_label = "going home to sleep" # Specific task
                                    destination_coords = sleep_spot_coords
                                else: # No specific bed location, just go to building center
                                    dest_coords_temp = self._get_building_global_center_coords(npc.schedule.home_building_id)
                                    if dest_coords_temp:
                                        new_task_label = "going home"
                                        destination_coords = dest_coords_temp

                    # Else (daytime, not work hours, or already finished work), go home (to building center) if not there
                    elif npc.schedule.home_building_id and not is_at_home and npc.schedule.current_task not in ["going home", "going home to sleep", "sleeping"]:
                        dest_coords_temp = self._get_building_global_center_coords(npc.schedule.home_building_id)
                        if dest_coords_temp:
                            new_task_label = "going home"
                            destination_coords = dest_coords_temp

                    # Wake up logic: If sleeping and it's no longer night
                    if npc.schedule.current_task == "sleeping" and not is_night_time:
                        npc.schedule.current_task = "at home" # Or "idle"
                        if hasattr(npc, 'original_char_before_sleep') and npc.char == ord('z'): # only restore if actually 'z'
                             npc.char = npc.original_char_before_sleep
                        # self.add_message_to_chat_log(f"{npc.name} woke up.")

                    # New marriage seeking logic
                    elif npc.schedule.current_task == "seeking_partner":
                        # Find a potential partner in the same village
                        potential_partners = [
                            p for p in self.village_npcs
                            if p.id != npc.id and not p.physical.is_dead and
                               p.age > 18 and not p.social.family_ties.get("partner_id") and
                               self._get_village_for_npc(p) == self._get_village_for_npc(npc)
                        ]

                        if potential_partners:
                            # Choose a partner, maybe weighted by relationship
                            weights = [max(1, npc.social.relationships.get(p.id, 50)) for p in potential_partners]
                            chosen_partner = random.choices(potential_partners, weights=weights, k=1)[0]

                            self.add_message_to_chat_log(f"Debug: {npc.name} is considering courting {chosen_partner.name}.")

                            # Path to a tile adjacent to the partner
                            dest_x, dest_y = self._find_best_adjacent_tile(chosen_partner.x, chosen_partner.y, npc)
                            if dest_x is not None:
                                destination_coords = (dest_x, dest_y)
                                new_task_label = "courting"
                                npc.task_target_entity_id = chosen_partner.id
                        else:
                            npc.schedule.current_task = "idle" # No one to court, go back to idle

                    elif is_leisure_time and npc.age > 18 and not npc.social.family_ties.get("partner_id"):
                        if random.random() < 0.01: # 1% chance each schedule update during leisure to seek a partner
                            npc.schedule.current_task = "seeking_partner"

                    # New Task: Fetching Water (example, low priority, during day, if not working/going to work)
                    # Only if not night time and not during work hours
                    is_day_leisure_time = not is_night_time and not (work_start_tick <= current_time_in_day < work_end_tick)
                    if not new_task_label and is_day_leisure_time and random.random() < 0.01 : # Low chance to decide to fetch water
                        # Find the NPC's village to get well location
                        npc_village = None
                        for y_idx, row in enumerate(self.chunks):
                            for x_idx, chk in enumerate(row):
                                if chk.village: # Assuming NPC is in a village chunk that has a village object
                                    # Check if this NPC belongs to this village (e.g. home is here)
                                    if npc.schedule.home_building_id and self.buildings_by_id.get(npc.schedule.home_building_id) in chk.village.buildings:
                                        npc_village = chk.village
                                        break
                            if npc_village: break

                        if npc_village and "well" in npc_village.interaction_points and npc_village.interaction_points["well"]:
                            well_coords = random.choice(npc_village.interaction_points["well"]) # Pick one if multiple wells
                            if (npc.x, npc.y) != well_coords:
                                new_task_label = "fetching water"
                                destination_coords = well_coords
                            else:
                                npc.schedule.current_task = "at the well" # Already there

                # --- Assign Path if new task and destination found ---
                if new_task_label and destination_coords:
                    # Ensure destination is pathable (or path to nearest passable)
                    # For now, assume center of building is generally inside and thus pathable floor.
                    # Or path to door if we define doors explicitly as entry points.

                    # Check if NPC is already at the destination
                    if (npc.x, npc.y) == destination_coords:
                        if new_task_label == "going to work":
                            npc.schedule.current_task = f"Working ({npc.economic.profession})" if npc.economic.profession != "Unemployed" else "At Work (Idle)"
                        elif new_task_label == "going home":
                            npc.schedule.current_task = "at home" # Will check for bed next cycle if night
                        else:
                            npc.schedule.current_task = "idle"
                    else:
                        path = self.calculate_path(npc.x, npc.y, destination_coords[0], destination_coords[1])
                        if path:
                            npc.schedule.current_path = path
                            npc.schedule.current_destination_coords = destination_coords
                            npc.schedule.current_task = new_task_label # Use new_task_label here
                            # Clear sub-task state if the new main task is not work-related or is a pathing task to work
                            if new_task_label not in ["going to work", "at work"] and not new_task_label.startswith("Working ("):
                                npc.current_sub_task = None
                                npc.sub_task_target_coords = None
                                npc.sub_task_zone_target = None
                                npc.sub_task_timer = 0
                                npc.current_sub_task_sequence_index = 0
                            # self.add_message_to_chat_log(f"{npc.name} starting path for task: {new_task_label} to {destination_coords}. Path length: {len(path)}")
                        else:
                            # self.add_message_to_chat_log(f"Could not find path for {npc.name} for task {new_task_label} to {destination_coords}")
                            npc.schedule.current_task = "idle_confused" # Cannot find path

            # --- Sheriff / Guard Hostility Check ---
            if npc.economic.profession in ["Sheriff", "Guard"] and not npc.combat.is_hostile_to_player:
                if self.player.economic.bounty >= 100: # Bounty threshold for arrest
                    # Check if player is visible to the Sheriff/Guard
                    if npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.x, self.player.y]:
                        self.add_message_to_chat_log(f"{npc.name} spots you and moves to arrest you for your crimes!")
                        npc.combat.is_hostile_to_player = True
                        # Their combat AI will now handle moving towards the player to "attack" (which will be arrest)

            # After all task decisions and path assignments:
            # If NPC is at work, handle specific work sub-tasks or general production.
            # This is also where NPCs who have arrived at work ("at work") will start their sub-task logic.
            if npc.schedule.current_task == "at work" or npc.schedule.current_task.startswith("Working ("): # Check both generic and specific working tasks
                # Sub-task logic is now the primary driver of production.
                # The old _handle_npc_production is removed.
                self._handle_npc_work_sub_tasks(npc)

            if npc.schedule.current_task != "sleeping" and hasattr(npc, 'original_char_before_sleep') and npc.char == ord('z'):
                if hasattr(npc, 'original_char_before_sleep'): # Ensure it exists before trying to access
                    npc.char = npc.original_char_before_sleep

            # --- Traveling Merchant AI ---
            if npc.economic.profession == "Traveling Merchant":
                if npc.schedule.current_task == "traveling_to_village" and not npc.schedule.current_path:
                    # Find a new village to travel to
                    all_villages = []
                    for y_chunk in range(self.chunk_height):
                        for x_chunk in range(self.chunk_width):
                            chunk = self.chunks[y_chunk][x_chunk]
                            if chunk.village:
                                all_villages.append(chunk.village)

                    if len(all_villages) > 1:
                        current_village = self._get_village_for_npc(npc)
                        target_village = random.choice([v for v in all_villages if v != current_village])

                        if target_village and target_village.buildings:
                            target_building = random.choice(target_village.buildings)
                            dest_x = target_building.global_center_x
                            dest_y = target_building.global_center_y

                            path = self.calculate_path(npc.x, npc.y, dest_x, dest_y)
                            if path:
                                npc.schedule.current_path = path
                                npc.schedule.current_destination_coords = (dest_x, dest_y)
                                self.add_message_to_chat_log(f"{npc.name} is traveling to a new village.")
                elif npc.schedule.current_task == "lingering_in_village":
                    if npc.leisure_timer > 0:
                        npc.leisure_timer -= 1

                        # Trade logic
                        current_village = self._get_village_for_npc(npc, by_coords=True)
                        if current_village and random.random() < 0.1: # 10% chance to trade each schedule update
                            # Sell high-demand goods
                            for item_key, quantity in list(npc.economic.npc_inventory.items()):
                                if item_key == "money": continue
                                demand = current_village.demand.get(item_key, 1)
                                supply = current_village.supply.get(item_key, 1)
                                if demand / supply > 1.5: # If demand is 50% higher than supply
                                    price = self.get_dynamic_price(item_key, current_village)
                                    npc.economic.npc_inventory[item_key] -= 1
                                    if npc.economic.npc_inventory[item_key] <= 0:
                                        del npc.economic.npc_inventory[item_key]
                                    npc.economic.money += price
                                    current_village.supply[item_key] = current_village.supply.get(item_key, 0) + 1
                                    self.add_message_to_chat_log(f"{npc.name} sold a {ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)} to the village.")

                            # Buy low-supply goods
                            inventory_space = 20 - sum(v for k, v in npc.economic.npc_inventory.items() if k != "money")
                            if inventory_space > 0:
                                for item_key, quantity in list(current_village.supply.items()):
                                    if item_key == "money": continue
                                    demand = current_village.demand.get(item_key, 1)
                                    supply = current_village.supply.get(item_key, 1)
                                    if supply / demand > 1.5: # If supply is 50% higher than demand
                                        price = self.get_dynamic_price(item_key, current_village)
                                        if npc.economic.money >= price:
                                            npc.economic.money -= price
                                            npc.economic.npc_inventory[item_key] = npc.economic.npc_inventory.get(item_key, 0) + 1
                                            current_village.supply[item_key] -= 1
                                            if current_village.supply[item_key] <= 0:
                                                del current_village.supply[item_key]
                                            self.add_message_to_chat_log(f"{npc.name} bought a {ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)} from the village.")
                                            break # Only buy one item per trade check
                    else:
                        npc.schedule.current_task = "traveling_to_village"
                elif npc.schedule.current_task == "idle" and random.random() < 0.1:
                     npc.schedule.current_task = "traveling_to_village"


            npc.schedule.game_time_last_updated = self.game_time

    def _find_nearest_tree_for_chopping(self, npc: NPC, work_building: Building) -> tuple[int, int] | None:
        """
        Finds the nearest choppable tree for the NPC, using the NPC's dynamic search radius.
        If no tree is found, the NPC's search radius is increased.
        Returns global (x,y) coordinates or None.
        """
        search_radius = npc.woodcutter_search_radius
        center_x, center_y = work_building.global_center_x, work_building.global_center_y
        closest_tree_coords = None
        min_dist_sq = float('inf')

        # Iterate in expanding square rings around the building's center
        for r in range(search_radius + 1):
            coords_in_ring = []
            if r == 0:
                coords_in_ring.append((center_x, center_y))
            else:
                # Top and bottom edges of the square ring
                for i in range(-r, r + 1):
                    coords_in_ring.append((center_x + i, center_y + r))
                    if r != 0: # Avoid double adding center row if r=0 was part of this loop
                        coords_in_ring.append((center_x + i, center_y - r))
                # Left and right edges (excluding corners already covered)
                for i in range(-r + 1, r):
                    coords_in_ring.append((center_x + r, center_y + i))
                    if r != 0: # Avoid double adding center column
                        coords_in_ring.append((center_x - r, center_y + i))

            current_ring_closest_tree = None
            current_ring_min_dist_sq = float('inf')

            for x, y in list(set(coords_in_ring)): # Use set to remove duplicates from ring generation
                if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
                    continue

                tile = self.get_tile_at(x, y)
                if isinstance(tile, Tree) and tile.is_choppable:
                    # Check if this tree is targeted by another NPC for chopping
                    is_targeted = False
                    for other_npc in self.village_npcs: # Check against all village NPCs
                        if other_npc.id != npc.id and \
                           other_npc.current_sub_task == "chop_trees" and \
                           other_npc.sub_task_target_coords == (x,y):
                            is_targeted = True
                            break
                    if is_targeted:
                        continue # Skip this tree as it's already targeted

                    dist_sq_from_npc = (npc.x - x)**2 + (npc.y - y)**2 # Distance from current NPC
                    if dist_sq_from_npc < current_ring_min_dist_sq:
                        current_ring_min_dist_sq = dist_sq_from_npc
                        current_ring_closest_tree = (x, y)

            if current_ring_closest_tree:
                # If we found a tree in this ring, it's the closest overall because we search radially.
                return current_ring_closest_tree

        npc.woodcutter_search_radius += 5
        return None

    def _find_target_coords_for_sub_task(self, npc: NPC, work_building: Building, sub_task_data: dict) -> tuple[int, int] | None:
        """Determines the global target coordinates for a given sub-task."""
        target_zone_tag = sub_task_data.get("target_zone_tag")
        if not target_zone_tag:
            # self.add_message_to_chat_log(f"Error: Sub-task {sub_task_data.get('id')} for {npc.name} has no target_zone_tag.")
            return None

        if target_zone_tag == "chopping_area":
            # For chopping, we find a dynamic tree target near the building.
            # The work_building itself is passed to help center the search.
            return self._find_nearest_tree_for_chopping(npc, work_building)
        elif target_zone_tag == "lumber_mill":
            # For fetching wood, find the nearest lumber mill
            lumber_mill = self._find_nearest_lumber_mill(npc)
            if lumber_mill:
                return (lumber_mill.global_center_x, lumber_mill.global_center_y)
            return None
        elif target_zone_tag == "farm":
            # For fetching wheat, find the nearest farm
            farm = self._find_nearest_farm(npc)
            if farm:
                return (farm.global_center_x, farm.global_center_y)
            return None
        elif target_zone_tag == "mill":
            # For fetching flour, find the nearest mill
            mill = self._find_nearest_mill(npc)
            if mill:
                return (mill.global_center_x, mill.global_center_y)
            return None
        elif target_zone_tag == "mine":
            # For fetching ore, find the nearest mine
            mine = self._find_nearest_mine(npc)
            if mine:
                return (mine.global_center_x, mine.global_center_y)
            return None
        elif npc.economic.profession == "Farmer" and target_zone_tag == "field_patch":
            field_tiles_coords = work_building.work_zone_tiles.get("field_patch", [])
            if not field_tiles_coords:
                # self.add_message_to_chat_log(f"Warning: Farm {work_building.id} has no field_patch zone defined.")
                return None

            target_tile_type_key = sub_task_data.get("target_tile_type_key") # e.g., "plains", "tilled_soil"
            if not target_tile_type_key:
                # self.add_message_to_chat_log(f"Error: Farmer sub-task {sub_task_data['id']} missing 'target_tile_type_key'.")
                return None

            # Specific check for "plant_seeds": ensure seeds are available BEFORE finding a tile
            if sub_task_data["id"] == "plant_seeds":
                seeds_to_consume = sub_task_data.get("consumes_item_from_workplace", {})
                seed_item_key = next(iter(seeds_to_consume), None) # Get the first seed type key
                if not seed_item_key or work_building.building_inventory.get(seed_item_key, 0) < seeds_to_consume[seed_item_key]:
                    # self.add_message_to_chat_log(f"Debug: {npc.name} wants to plant seeds, but farm has no {seed_item_key}.")
                    return None # Cannot plant if no seeds

            # Shuffle to vary the choice of tile a bit if multiple are suitable
            random.shuffle(field_tiles_coords)

            for tx, ty in field_tiles_coords:
                tile = self.get_tile_at(tx, ty)
                # Check if tile name matches the required type for the sub-task
                # Tile objects store their definition's key in tile.name if generated from TILE_DEFINITIONS keys
                # Or compare against the actual name string from TILE_DEFINITIONS
                expected_tile_name = TILE_DEFINITIONS.get(target_tile_type_key, {}).get("name")
                if tile and tile.name == expected_tile_name:
                    # TODO: Add a check here to ensure another NPC isn't already targeting this exact tile for the same sub-task type.
                    # This is similar to the tree targeting check. For now, proceed without it for simplicity.
                    return (tx, ty)
            # self.add_message_to_chat_log(f"Debug: {npc.name} could not find suitable '{expected_tile_name}' tile in field_patch for {sub_task_data['id']}.")
            return None
        else:
            # For other zones (like Woodcutter's log_pile_area), use pre-defined coordinates
            zone_coords_list = work_building.work_zone_tiles.get(target_zone_tag)
            if zone_coords_list:
                # Pick a random available coordinate from the list for now.
                # Could be smarter (e.g., closest, or one not currently targeted by another NPC).
                return random.choice(zone_coords_list)
            else:
                # self.add_message_to_chat_log(f"Warning: No coordinates defined for work zone '{target_zone_tag}' in building {work_building.id} for {npc.name}.")
                return None

    def _produce_sub_task_output(self, npc: NPC, work_building: Building, sub_task_data: dict, target_tile_obj: Tile | None = None) -> bool:
        """
        Handles item production or consumption for a completed sub-task.
        This now also handles transfers from NPC inventory to building inventory,
        and production based on tile properties (for harvesting).
        Returns True if all necessary consumptions were successful, False otherwise.
        """
        consumption_successful = True # Assume success unless specific consumption fails

        # 1. Consume from NPC inventory (if defined)
        consumes_from_npc_def = sub_task_data.get("consumes_item_from_npc_inventory")
        if consumes_from_npc_def:
            for item_key, quantity_needed in consumes_from_npc_def.items():
                current_npc_qty = npc.economic.npc_inventory.get(item_key, 0)
                if current_npc_qty >= quantity_needed:
                    npc.economic.npc_inventory[item_key] = current_npc_qty - quantity_needed
                    if npc.economic.npc_inventory[item_key] <= 0:
                        del npc.economic.npc_inventory[item_key]
                    # self.add_message_to_chat_log(f"Debug: {npc.name} consumed {quantity_needed} {item_key} from personal inventory.")
                else:
                    # self.add_message_to_chat_log(f"Debug: {npc.name} needed {quantity_needed} {item_key} from inventory for task, but only had {current_npc_qty}.")
                    consumption_successful = False
                    break # Stop further processing for this sub-task if NPC consumption fails
            if not consumption_successful:
                return # Early exit if NPC couldn't provide required items from its inventory

        # 2. Consume from Workplace inventory (if defined)
        # This should only happen if NPC consumption (if any) was successful
        if consumption_successful:
            consumes_from_building_def = sub_task_data.get("consumes_item_from_workplace")
            if consumes_from_building_def:
                for item_key, quantity_needed in consumes_from_building_def.items():
                    current_building_qty = work_building.building_inventory.get(item_key, 0)
                    if current_building_qty >= quantity_needed:
                        work_building.building_inventory[item_key] = current_building_qty - quantity_needed
                        if work_building.building_inventory[item_key] <= 0:
                            del work_building.building_inventory[item_key]
                        # self.add_message_to_chat_log(f"Debug: Task consumed {quantity_needed} {item_key} from {work_building.building_type}.")
                    else:
                        # self.add_message_to_chat_log(f"Debug: {work_building.building_type} needed {quantity_needed} {item_key} for task, but only had {current_building_qty}.")
                        consumption_successful = False
                        break # Stop further processing if building consumption fails
                if not consumption_successful:
                    # TODO: What if NPC items were consumed but building items were not? Rollback NPC consumption?
                    # For now, if building consumption fails, the process stops, potentially leaving NPC items consumed.
                    # This implies sub-tasks should be designed carefully (e.g., consume from NPC then deposit to building is one flow,
                    # consume from building to produce to building is another).
                    return False # Indicate consumption failed

        # 3. Deposit items to Workplace (if defined, and all consumptions were successful)
        if consumption_successful:
            deposits_to_building_def = sub_task_data.get("deposits_item_to_workplace")
            if deposits_to_building_def:
                for item_key, quantity_deposited in deposits_to_building_def.items():
                    current_building_qty = work_building.building_inventory.get(item_key, 0)
                    work_building.building_inventory[item_key] = current_building_qty + quantity_deposited
                    # item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    # self.add_message_to_chat_log(f"Debug: {npc.name} deposited {quantity_deposited} {item_name} to {work_building.building_type}.")

        # 4. Produce items at Workplace (if defined, and all consumptions were successful)
        if consumption_successful:
            # A. Check for tile-based harvest production first
            if sub_task_data.get("produces_item_at_workplace_from_tile_harvest") and target_tile_obj:
                if target_tile_obj.properties.get("is_harvestable"):
                    item_key = target_tile_obj.properties.get("harvest_yield_item_key")
                    quantity_produced = target_tile_obj.properties.get("harvest_yield_quantity", 0)
                    if item_key and quantity_produced > 0:
                        current_building_qty = work_building.building_inventory.get(item_key, 0)
                        work_building.building_inventory[item_key] = current_building_qty + quantity_produced
                        # item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                        # self.add_message_to_chat_log(f"Debug: {npc.name} harvested {quantity_produced} {item_name} into {work_building.building_type}.")

            # B. Standard sub-task defined production (if not tile harvest or in addition to)
            # Ensure this doesn't double-produce if tile harvest already happened for same item.
            # Current design: harvest flag is specific, so this is for other direct productions.
            produces_at_building_def = sub_task_data.get("produces_item_at_workplace")
            if produces_at_building_def:
                for item_key, quantity_produced in produces_at_building_def.items():
                    current_building_qty = work_building.building_inventory.get(item_key, 0)
                    work_building.building_inventory[item_key] = current_building_qty + quantity_produced
                    # item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    # Optional: Log production for player if they can see/hear the NPC
                    # dist_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y)
                    # if dist_to_player <= 10:
                    #    self.add_message_to_chat_log(f"{npc.name} finishes working and produces {quantity_produced} {item_name} at the {work_building.building_type}.")

        village = self._get_village_for_npc(npc)
        if village:
            if consumption_successful:
                produces = sub_task_data.get("produces_item_at_workplace", {})
                for item_key, qty in produces.items():
                    village.supply[item_key] = village.supply.get(item_key, 0) + qty

                consumes = sub_task_data.get("consumes_item_from_workplace", {})
                for item_key, qty in consumes.items():
                    village.supply[item_key] = village.supply.get(item_key, 0) - qty
                    village.demand[item_key] = village.demand.get(item_key, 0) + qty

        return consumption_successful


    def _handle_npc_work_sub_tasks(self, npc: NPC) -> bool:
        """
        Manages an NPC's progression through defined work sub-tasks for their profession.
        Returns True if sub-task logic was applied (even if just pathing or waiting),
        False if no sub-tasks are applicable or defined for this NPC's current state/profession.
        """
        if not npc.schedule.work_building_id or not npc.economic.profession:
            return False

        profession_data = get_profession_data(npc.economic.profession)
        if not profession_data or not profession_data.get("sub_tasks") or not profession_data.get("default_sub_task_sequence"):
            return False # No sub-tasks defined for this profession

        work_building = self.buildings_by_id.get(npc.schedule.work_building_id)
        if not work_building:
            # self.add_message_to_chat_log(f"Error: {npc.name} has work_building_id {npc.schedule.work_building_id} but building not found.")
            npc.current_task = "idle_confused"
            return True # Handled this confusion

        sub_task_sequence = profession_data["default_sub_task_sequence"]
        if not sub_task_sequence:
            return False # Empty sequence

        # If current sub-task is done (timer ran out or just finished one)
        if not npc.current_sub_task or (npc.sub_task_target_coords and (npc.x, npc.y) == npc.sub_task_target_coords and npc.sub_task_timer <= 0):

            # If a sub-task was just completed (timer is 0 or less, and was at target)
            if npc.current_sub_task and npc.sub_task_timer <= 0 and npc.sub_task_target_coords and (npc.x, npc.y) == npc.sub_task_target_coords:
                completed_sub_task_id = npc.current_sub_task
                completed_sub_task_data = get_sub_task_data(npc.economic.profession, completed_sub_task_id)

                if completed_sub_task_data:
                    if completed_sub_task_id == "chop_trees":
                        tree_tile_obj = self.get_tile_at(npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
                        if isinstance(tree_tile_obj, Tree) and tree_tile_obj.is_choppable:
                            original_tree_type = tree_tile_obj.tree_type
                            yielded_resources = tree_tile_obj.chop()
                            logs_collected = yielded_resources.get("raw_log", 0)

                            stump_key = tree_tile_obj.becomes_on_chop_key
                            stump_def = TILE_DEFINITIONS.get(stump_key)

                            if stump_def:
                                self._change_map_tile(npc.sub_task_target_coords, stump_def, original_tree_type=original_tree_type)
                                new_stump_tile = self.get_tile_at(npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
                                if new_stump_tile:
                                    new_stump_tile.regrowth_timer = 100

                            if logs_collected > 0:
                                npc.add_item("raw_log", logs_collected)
                        # else:
                            # self.add_message_to_chat_log(f"Debug: {npc.name} tried to chop at {npc.sub_task_target_coords}, but it wasn't a choppable tree.")
                    elif completed_sub_task_id == "mine_ore":
                        # Miner is at the mine face, generate ore
                        npc.add_item("iron_ore", 1)

                    elif completed_sub_task_id == "fetch_ore":
                        # Blacksmith is at the mine, try to buy ore
                        mine = self._find_nearest_mine(npc)
                        if mine:
                            village = self._get_village_for_npc(npc)
                            ore_price = self.get_dynamic_price("iron_ore", village)
                            ore_to_buy = 5 # Try to buy 5 ore
                            if npc.economic.money >= ore_price * ore_to_buy and mine.building_inventory.get("iron_ore", 0) >= ore_to_buy:
                                mine.building_inventory["iron_ore"] -= ore_to_buy
                                npc.economic.money -= ore_price * ore_to_buy
                                npc.add_item("iron_ore", ore_to_buy)
                                # self.add_message_to_chat_log(f"{npc.name} bought {ore_to_buy} iron ore.")

                    elif completed_sub_task_id == "fetch_wood":
                        # Carpenter is at the lumber mill, try to buy wood
                        lumber_mill = self.buildings_by_id.get(npc.sub_task_target_coords)
                        if lumber_mill and lumber_mill.building_type == "lumber_mill":
                            village = self._get_village_for_npc(npc)
                            plank_price = self.get_dynamic_price("wooden_plank", village)
                            planks_to_buy = 5 # Try to buy 5 planks
                            if npc.economic.money >= plank_price * planks_to_buy and lumber_mill.building_inventory.get("wooden_plank", 0) >= planks_to_buy:
                                lumber_mill.building_inventory["wooden_plank"] -= planks_to_buy
                                npc.economic.money -= plank_price * planks_to_buy
                                work_building.building_inventory["wooden_plank"] = work_building.building_inventory.get("wooden_plank", 0) + planks_to_buy
                                # self.add_message_to_chat_log(f"{npc.name} bought {planks_to_buy} planks.")

                    elif completed_sub_task_id == "craft_furniture":
                        # Carpenter is at their workbench, try to craft furniture
                        planks_needed = 2 # Example for a chair
                        if work_building.building_inventory.get("wooden_plank", 0) >= planks_needed:
                            work_building.building_inventory["wooden_plank"] -= planks_needed
                            work_building.building_inventory["wooden_chair"] = work_building.building_inventory.get("wooden_chair", 0) + 1
                            # self.add_message_to_chat_log(f"{npc.name} crafted a wooden chair.")

                    elif completed_sub_task_id == "fetch_wheat":
                        # Miller is at the farm, try to buy wheat
                        farm = self._find_nearest_farm(npc)
                        if farm:
                            village = self._get_village_for_npc(npc)
                            wheat_price = self.get_dynamic_price("wheat", village)
                            wheat_to_buy = 5 # Try to buy 5 wheat
                            if npc.economic.money >= wheat_price * wheat_to_buy and farm.building_inventory.get("wheat", 0) >= wheat_to_buy:
                                farm.building_inventory["wheat"] -= wheat_to_buy
                                npc.economic.money -= wheat_price * wheat_to_buy
                                work_building.building_inventory["wheat"] = work_building.building_inventory.get("wheat", 0) + wheat_to_buy
                                self.add_message_to_chat_log(f"{npc.name} the Miller bought {wheat_to_buy} wheat.")

                    elif completed_sub_task_id == "fetch_flour":
                        # Baker is at the mill, try to buy flour
                        mill = self._find_nearest_mill(npc)
                        if mill:
                            village = self._get_village_for_npc(npc)
                            flour_price = self.get_dynamic_price("flour", village)
                            flour_to_buy = 5 # Try to buy 5 flour
                            if npc.economic.money >= flour_price * flour_to_buy and mill.building_inventory.get("flour", 0) >= flour_to_buy:
                                mill.building_inventory["flour"] -= flour_to_buy
                                npc.economic.money -= flour_price * flour_to_buy
                                work_building.building_inventory["flour"] = work_building.building_inventory.get("flour", 0) + flour_to_buy
                    elif completed_sub_task_id == "write_book":
                        # Scribe is at their desk, generate a book
                        known_events_summary = " ".join([event.description for event in npc.knowledge.known_events.values()])
                        prompt = LLM_PROMPTS["scribe_write_book"].format(
                            scribe_name=npc.name,
                            scribe_personality=npc.social.personality,
                            known_events_summary=known_events_summary,
                            year=self.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4)
                        )
                        llm_response = self._call_ollama(prompt)
                        try:
                            book_data = json.loads(llm_response)
                            new_book = Book(
                                title=book_data.get("title", "Untitled"),
                                author_id=npc.id,
                                author_name=npc.name,
                                year_written=self.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4),
                                content=book_data.get("content", "..."),
                                book_type="chronicle"
                            )
                            self.books.append(new_book)
                            work_building.building_inventory[f"book_{new_book.id}"] = 1
                            self.add_message_to_chat_log(f"{npc.name} has written a new book titled '{new_book.title}'.")
                        except json.JSONDecodeError as e:
                            self.add_message_to_chat_log(f"Error parsing LLM response for book writing: {e}")
                    elif completed_sub_task_id == "compile_census":
                        birth_events = [e for e in self.global_events if e.type == 'npc_birth']
                        death_events = [e for e in self.global_events if e.type == 'entity_death']

                        birth_events_summary = "\n".join([e.description for e in birth_events]) or "None recorded."
                        death_events_summary = "\n".join([e.description for e in death_events]) or "None recorded."

                        prompt = LLM_PROMPTS["town_official_compile_census"].format(
                            official_name=npc.name,
                            official_personality=npc.social.personality,
                            year=self.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4),
                            birth_events_summary=birth_events_summary,
                            death_events_summary=death_events_summary
                        )
                        llm_response = self._call_ollama(prompt)
                        try:
                            book_data = json.loads(llm_response)
                            new_book = Book(
                                title=book_data.get("title", f"Census - Year {self.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4)}"),
                                author_id=npc.id,
                                author_name=npc.name,
                                year_written=self.game_time // (DAY_LENGTH_TICKS * DAYS_PER_SEASON * 4),
                                content=book_data.get("content", "..."),
                                book_type="census"
                            )
                            self.books.append(new_book)
                            work_building.building_inventory[f"book_{new_book.id}"] = 1
                            self.add_message_to_chat_log(f"{npc.name} has compiled the village census.")
                        except json.JSONDecodeError as e:
                            self.add_message_to_chat_log(f"Error parsing LLM response for census compilation: {e}")

                    elif completed_sub_task_id == "mill_flour":
                        # Miller is at their grinding stone, try to mill flour
                        wheat_needed = 1
                        if work_building.building_inventory.get("wheat", 0) >= wheat_needed:
                            work_building.building_inventory["wheat"] -= wheat_needed
                            work_building.building_inventory["flour"] = work_building.building_inventory.get("flour", 0) + 1
                            # self.add_message_to_chat_log(f"{npc.name} milled some flour.")

                    elif npc.economic.profession == "Farmer":
                        target_tile_obj = self.get_tile_at(npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
                        original_tile_name = target_tile_obj.name if target_tile_obj else "None"

                        if completed_sub_task_id == "till_soil":
                            expected_tile_name = TILE_DEFINITIONS.get(completed_sub_task_data.get("target_tile_type_key"), {}).get("name")
                            if target_tile_obj and original_tile_name == expected_tile_name:
                                becomes_key = completed_sub_task_data.get("becomes_tile_type_key")
                                new_tile_def = TILE_DEFINITIONS.get(becomes_key)
                                if new_tile_def:
                                    self._change_map_tile(npc.sub_task_target_coords, new_tile_def)
                                    # self.add_message_to_chat_log(f"Debug: {npc.name} tilled {original_tile_name} to {new_tile_def['name']} at {npc.sub_task_target_coords}.")

                        elif completed_sub_task_id == "plant_seeds":
                            expected_tile_name = TILE_DEFINITIONS.get(completed_sub_task_data.get("target_tile_type_key"), {}).get("name")
                            if target_tile_obj and original_tile_name == expected_tile_name:
                                # Seed consumption will be attempted by _produce_sub_task_output.
                                # It needs to return a status or the calling code needs to check inventory.
                                # For now, _produce_sub_task_output handles its own early exit if consumption fails.
                                consumption_succeeded = self._produce_sub_task_output(npc, work_building, completed_sub_task_data)

                                if consumption_succeeded: # Only change tile if seeds were successfully consumed
                                    becomes_key = completed_sub_task_data.get("becomes_tile_type_key")
                                    new_tile_def = TILE_DEFINITIONS.get(becomes_key)
                                    if new_tile_def:
                                        self._change_map_tile(npc.sub_task_target_coords, new_tile_def)
                                        # self.add_message_to_chat_log(f"Debug: {npc.name} planted seeds at {npc.sub_task_target_coords}, tile now {new_tile_def['name']}.")
                                # else:
                                    # self.add_message_to_chat_log(f"Debug: {npc.name} failed to plant seeds at {npc.sub_task_target_coords} due to lack of seeds.")

                        elif completed_sub_task_id == "harvest_crops":
                            expected_tile_name = TILE_DEFINITIONS.get(completed_sub_task_data.get("target_tile_type_key"), {}).get("name")
                            if target_tile_obj and original_tile_name == expected_tile_name and target_tile_obj.properties.get("is_harvestable"):
                                # Item production from tile's properties handled by _produce_sub_task_output
                                self._produce_sub_task_output(npc, work_building, completed_sub_task_data, target_tile_obj=target_tile_obj)

                                becomes_key = target_tile_obj.properties.get("becomes_on_harvest_key")
                                if not becomes_key:
                                     becomes_key = completed_sub_task_data.get("becomes_tile_type_key") # Fallback

                                new_tile_def = TILE_DEFINITIONS.get(becomes_key)
                                if new_tile_def:
                                    self._change_map_tile(npc.sub_task_target_coords, new_tile_def)
                                    # self.add_message_to_chat_log(f"Debug: {npc.name} harvested {original_tile_name} at {npc.sub_task_target_coords}, tile now {new_tile_def['name']}.")
                    else:
                        # Handle output/consumption for other (non-Farmer, non-Woodcutter chop) sub-tasks via the helper
                        self._produce_sub_task_output(npc, work_building, completed_sub_task_data)

                # Move to next sub-task in sequence - This is where the logic changes.
                # Instead of just incrementing, we will now search for the next VALID task.
                npc.current_sub_task = None # Force re-evaluation below

            # Set up the new sub-task
            if not npc.current_sub_task:
                found_viable_task = False
                # Iterate through the sequence from the last known index to find the next possible task.
                # We check up to `len(sub_task_sequence)` times to avoid an infinite loop if no task is possible.
                for i in range(len(sub_task_sequence)):
                    next_task_index = (npc.current_sub_task_sequence_index + i) % len(sub_task_sequence)
                    next_sub_task_id = sub_task_sequence[next_task_index]
                    current_sub_task_data = get_sub_task_data(npc.economic.profession, next_sub_task_id)

                    if not current_sub_task_data: continue # Skip if data is missing

                    # Check if this task is possible by trying to find a target.
                    target_coords = self._find_target_coords_for_sub_task(npc, work_building, current_sub_task_data)

                    if target_coords:
                        # Found a valid task. Set it as the current one.
                        npc.current_sub_task_sequence_index = next_task_index
                        npc.current_sub_task = next_sub_task_id
                        npc.sub_task_zone_target = current_sub_task_data.get("target_zone_tag")
                        npc.sub_task_target_coords = target_coords
                        npc.current_path = []
                        npc.sub_task_timer = current_sub_task_data.get("duration_ticks", 10)
                        found_viable_task = True
                        break # Exit the loop once a task is found

                if not found_viable_task:
                    # If no task in the entire sequence is possible, the NPC is stalled.
                    npc.current_task = f"Working ({npc.economic.profession} - No available tasks)"
                    return True # Handled for this cycle



        # If NPC has a sub-task and a target location for it
        if npc.current_sub_task and npc.sub_task_target_coords:
            sub_task_disp_name = get_sub_task_data(npc.economic.profession, npc.current_sub_task).get("display_name", npc.current_sub_task)

            if (npc.x, npc.y) != npc.sub_task_target_coords:
                # Path to target if not already there
                if not npc.schedule.current_path:
                    path = self.calculate_path(npc.x, npc.y, npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
                    if path:
                        npc.schedule.current_path = path
                        npc.schedule.current_destination_coords = npc.sub_task_target_coords # For _update_npc_movement
                        # Update task display for pathing to sub-task action
                        npc.current_task = f"Working ({npc.economic.profession} - {sub_task_disp_name} - Pathing)"
                    else:
                        # self.add_message_to_chat_log(f"{npc.name} cannot find path to {npc.sub_task_target_coords} for {npc.current_sub_task}.")
                        # Clear current sub-task details to retry finding location / path next time
                        npc.current_sub_task = None
                        npc.sub_task_target_coords = None
                        npc.sub_task_zone_target = None
                        npc.schedule.current_path = []
                        npc.schedule.current_destination_coords = None
                        npc.current_task = f"Working ({npc.economic.profession} - Pathing Failed)"
                else:
                     # Already pathing, ensure task display reflects this. _update_npc_movement handles the move.
                     npc.current_task = f"Working ({npc.economic.profession} - {sub_task_disp_name} - Pathing)"

            else: # NPC is at the sub-task target coordinates
                npc.schedule.current_path = [] # Clear path as arrived
                npc.schedule.current_destination_coords = None

                # Perform the action (decrement timer)
                npc.sub_task_timer -= 1

                # Update task display for performing action
                action_verb = get_sub_task_data(npc.economic.profession, npc.current_sub_task).get("action_verb", "working on")
                total_duration = get_sub_task_data(npc.economic.profession, npc.current_sub_task).get("duration_ticks", 10)
                progress = max(0, total_duration - npc.sub_task_timer)
                npc.current_task = f"Working ({npc.economic.profession} - {action_verb} {sub_task_disp_name} [{progress}/{total_duration}])"

                if npc.sub_task_timer <= 0:
                    # Action complete, output handled at start of next cycle. Current_sub_task will be cleared.
                    # self.add_message_to_chat_log(f"Debug: {npc.name} finished action for sub-task {npc.current_sub_task}.")

                    # Boost work performance for completing a sub-task
                    npc.economic.work_performance = min(100, npc.economic.work_performance + 5)

                    # The loop will pick this up at the top of the function next call.
                    pass
            return True # Sub-task logic was processed

        # If we reach here, no sub-task was found or processed, implying idleness at work
        # Decrease work performance slightly if supposed to be working but doing nothing
        if npc.schedule.current_task == "at work" or npc.schedule.current_task.startswith("Working ("):
             npc.economic.work_performance = max(0, npc.economic.work_performance - 1)

        return False # No current sub-task or target to act upon

    def _handle_npc_combat_turn(self, npc: NPC):
        """Handles an NPC's decision-making process during their combat turn."""
        if not npc.combat.is_hostile_to_player or npc.physical.is_dead:
            return

        # Gather context for LLM
        player = self.player
        distance_x = abs(npc.x - player.x)
        distance_y = abs(npc.y - player.y)
        manhattan_distance = distance_x + distance_y # Simple distance metric

        # Check if player is in attack range (Manhattan distance for melee)
        # Determine effective attack range and name based on equipped weapon
        effective_attack_range = npc.combat.attack_range # Default to base
        effective_attack_name = npc.combat.base_attack_name # Default to base

        if npc.equipment.weapon and npc.equipment.weapon in ITEM_DEFINITIONS:
            weapon_def = ITEM_DEFINITIONS[npc.equipment.weapon]
            effective_attack_range = weapon_def.get("properties", {}).get("attack_range", npc.combat.attack_range)
            effective_attack_name = weapon_def.get("name", npc.combat.base_attack_name)

        player_in_attack_range = (manhattan_distance <= effective_attack_range)

        # Placeholder for player's last action description
        player_last_action_desc = "player is nearby"

        # Determine if NPC can see the player
        can_see_player = False
        if npc.id in self.npc_fov_maps and \
           0 <= player.x < WORLD_WIDTH and 0 <= player.y < WORLD_HEIGHT:
            can_see_player = self.npc_fov_maps[npc.id][player.x, player.y]

        if not can_see_player:
            player_last_action_desc = "player disappeared from sight"

        has_healing_item = npc.economic.npc_inventory.get("healing_salve", 0) > 0

        # Pack behavior logic
        pack_members_nearby = 0
        if isinstance(npc, Animal) and npc.pack_id:
            for other_npc in self.npcs: # Check against all non-village NPCs
                if isinstance(other_npc, Animal) and other_npc.id != npc.id and other_npc.pack_id == npc.pack_id:
                    if abs(npc.x - other_npc.x) + abs(npc.y - other_npc.y) < 10: # Within 10 tiles
                        pack_members_nearby += 1

        prompt = LLM_PROMPTS["npc_combat_decision"].format(
            npc_name=npc.name,
            npc_personality=npc.social.personality,
            can_see_player=can_see_player,
            npc_combat_behavior=npc.combat.combat_behavior,
            npc_hp=npc.combat.hp,
            npc_max_hp=npc.combat.max_hp,
            npc_current_task=npc.schedule.current_task,
            npc_attack_name=effective_attack_name,
            npc_attack_range=effective_attack_range,
            has_healing_item=has_healing_item,
            player_x=player.x,
            player_y=player.y,
            npc_x=npc.x,
            npc_y=npc.y,
            distance_to_player=manhattan_distance,
            player_in_attack_range=player_in_attack_range,
            player_last_action_desc=player_last_action_desc,
            pack_members_nearby=pack_members_nearby,
        )

        response_str = self._call_ollama(prompt)
        if not response_str:
            # Fallback: if LLM fails, NPC might just try to attack if player is close, or do nothing
            if player_in_attack_range:
                npc.current_task = "combat_action_attack_player"
                self.add_message_to_chat_log(f"{npc.name} hesitates then glares menacingly (LLM Error).")
            else:
                npc.current_task = "combat_action_hold_position" # Or move towards if aggressive
                self.add_message_to_chat_log(f"{npc.name} seems confused by the situation (LLM Error).")
            npc.target_entity_id = player.id
            return

        try:
            response_json = json.loads(response_str)
            chosen_action = response_json.get("action")
            narrative = response_json.get("narrative", f"{npc.name} considers what to do...")

            self.add_message_to_chat_log(narrative) # Log NPC's thought/intent

            # Update NPC task based on LLM decision
            # The actual execution of these tasks (attack, pathfinding) will be handled
            # by other systems checking current_task.
            if chosen_action == "attack_player":
                if player_in_attack_range:
                    npc.current_task = "combat_action_attack_player"
                    # Sound emitted by npc_attempt_attack_player
                else:
                    # LLM chose attack but player not in range, so move to attack
                    npc.current_task = "combat_action_move_to_attack_player"
                    # self.add_message_to_chat_log(f"({npc.name} wants to attack but needs to get closer.)")
            elif chosen_action == "move_to_attack_player":
                if not player_in_attack_range:
                    npc.current_task = "combat_action_move_to_attack_player"
                else:
                    # LLM chose move but player is already in range, so attack
                    npc.current_task = "combat_action_attack_player"
                    # Sound emitted by npc_attempt_attack_player
                    # self.add_message_to_chat_log(f"({npc.name} decides to attack immediately as player is in range.)")
            elif chosen_action == "flee_from_player":
                npc.current_task = "combat_action_flee_from_player"
                npc.add_grudge(player.id, "Forced me to flee for my life.")
            elif chosen_action == "move_to_cover":
                cover_spot_x, cover_spot_y = self._find_best_cover_spot(npc, player.x, player.y)
                if cover_spot_x is not None:
                    npc.current_task = "combat_action_move_to_cover"
                    npc.task_target_coords = (cover_spot_x, cover_spot_y) # Store the specific cover spot
                    # self.add_message_to_chat_log(f"({npc.name} is heading to cover at ({cover_spot_x},{cover_spot_y}))")
                else:
                    # No cover found, default to holding position or another fallback
                    # self.add_message_to_chat_log(f"({npc.name} looked for cover but found none.)")
                    if npc.combat.hp < npc.combat.max_hp * 0.3 and npc.combat.combat_behavior == "cowardly": # If low health and cowardly, flee instead
                        npc.current_task = "combat_action_flee_from_player"
                        # self.add_message_to_chat_log(f"({npc.name} couldn't find cover and decides to flee instead!)")
                    else:
                        npc.current_task = "combat_action_hold_position"
            elif chosen_action == "use_healing_item":
                if npc.economic.npc_inventory.get("healing_salve", 0) > 0:
                    npc.current_task = "combat_action_use_healing_item"
                else:
                    # LLM hallucinated or NPC used its last salve since context was gathered. Fallback.
                    self.add_message_to_chat_log(f"({npc.name} wanted to heal but has no salve. Holding position.)")
                    npc.current_task = "combat_action_hold_position"
            elif chosen_action == "hold_position":
                npc.current_task = "combat_action_hold_position"
            else: # Unknown action or "use_ability" for now defaults to hold
                npc.current_task = "combat_action_hold_position"
                self.add_message_to_chat_log(f"({npc.name} considers an unknown action: {chosen_action}, defaults to holding position.)")

            npc.target_entity_id = player.id # All combat actions currently target the player

            # Clear path for any new movement decision, except if just attacking or holding or using item
            if chosen_action not in ["attack_player", "hold_position", "use_healing_item"]:
                npc.current_path = []

            # Clear specific task target coords if not moving to cover
            if chosen_action != "move_to_cover":
                npc.task_target_coords = None


        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"{npc.name} seems indecisive. (LLM Format Error: {response_str})")
            # Fallback on format error
            npc.current_task = "combat_action_hold_position"
            npc.target_entity_id = player.id

    def npc_attempt_attack_player(self, npc: NPC, player: Player):
        """Handles an NPC's attempt to attack the player."""
        if npc.is_dead or player.hp <= 0:
            return

        # --- ARREST LOGIC ---
        if npc.economic.profession in ["Sheriff", "Guard"] and self.player.economic.bounty >= 100 and not self.player.state.is_jailed:
            self.add_message_to_chat_log(f"{npc.name} apprehends you! You are under arrest.")
            self.serve_jail_time()
            # Stop the NPC's hostile actions after arrest
            npc.combat.is_hostile_to_player = False
            npc.current_task = "idle"
            npc.schedule.current_path = []
            return


        # Determine weapon details for the attack
        weapon_name = npc.combat.base_attack_name
        weapon_damage_description = npc.combat.base_attack_damage_dice

        if npc.equipment.weapon and npc.equipment.weapon in ITEM_DEFINITIONS:
            weapon_def = ITEM_DEFINITIONS[npc.equipment.weapon]
            weapon_name = weapon_def.get("name", npc.combat.base_attack_name)
            dice = weapon_def.get("properties", {}).get("damage_dice", npc.combat.base_attack_damage_dice)
            bonus = weapon_def.get("properties", {}).get("damage_bonus", 0)
            weapon_damage_description = f"{dice}"
            if bonus > 0:
                weapon_damage_description += f"+{bonus}"
            elif bonus < 0:
                weapon_damage_description += f"{bonus}"


        # Conceptual NPC melee skill
        npc_melee_skill = 5
        if npc.combat.combat_behavior == "aggressive": npc_melee_skill += 2
        if npc.economic.profession in ["Guard", "Sheriff"]: npc_melee_skill += 2
        npc_melee_skill = max(1, min(10, npc_melee_skill))

        # Updated player toughness description using the recalculated defense_bonus
        player_toughness_desc = "unarmored"
        if player.defense_bonus > 8:
            player_toughness_desc = "heavily armored"
        elif player.defense_bonus > 4:
            player_toughness_desc = "armored"
        elif player.defense_bonus > 0:
            player_toughness_desc = "lightly armored"


        prompt = LLM_PROMPTS["adjudicate_npc_attack"].format(
            npc_name=npc.name,
            weapon_name=weapon_name, # Use determined weapon name
            weapon_damage_description=weapon_damage_description, # Use determined damage description
            npc_melee_skill=npc_melee_skill,
            player_hp=player.hp,
            player_max_hp=player.max_hp,
            player_toughness_desc=player_toughness_desc
        )

        response_str = self._call_ollama(prompt)
        if not response_str:
            self.add_message_to_chat_log(f"{npc.name} swings wildly but misses! (LLM Comms Error)")
            return

        try:
            response_json = json.loads(response_str)
            hit = response_json.get("hit", False)
            damage_dealt = int(response_json.get("damage_dealt", 0))
            narrative = response_json.get("narrative_feedback", f"{npc.name} attacks!")
            # attacker_status_change = response_json.get("attacker_status_change", "none") # For future use

            self.add_message_to_chat_log(narrative)
            self.emit_sound(npc.x, npc.y, "combat_attack", volume=10, source_entity_id=npc.id) # Emit attack sound

            if hit and damage_dealt > 0:
                self.log_event(
                    event_type="combat_attack",
                    description="{subject} attacked {target}.",
                    subject_id=npc.id,
                    target_id=player.id,
                    location=(npc.x, npc.y)
                )
                actual_damage = player.take_damage(damage_dealt, world=self)
                if actual_damage > 0:
                    self.add_message_to_chat_log(f"You take {actual_damage} damage! Your HP is now {player.hp}/{player.max_hp}.")
                else:
                    self.add_message_to_chat_log(f"Your armor absorbs the blow!")

                if player.hp <= 0:
                    self.add_message_to_chat_log("You have been defeated!")
                    self.game_state = "PLAYER_DEAD"
                    self.log_event(
                        event_type="entity_death",
                        description="{subject} was killed by {target}.",
                        subject_id=player.id,
                        target_id=npc.id,
                        location=(player.x, player.y)
                    )
            elif hit and damage_dealt <= 0:
                self.add_message_to_chat_log(f"{npc.name}'s attack hits you but deals no damage.")

        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"{npc.name}'s attack is confusing. (LLM Format Error: {response_str})")
            self.emit_sound(npc.x, npc.y, "combat_attack", volume=8, source_entity_id=npc.id) # Still emit sound on error
        except ValueError: # For int(damage_dealt)
             self.add_message_to_chat_log(f"The LLM provided an invalid damage amount for {npc.name}'s attack: {response_json.get('damage_dealt') if 'response_json' in locals() else 'Unknown'}")
             self.emit_sound(npc.x, npc.y, "combat_attack", volume=8, source_entity_id=npc.id)

    def npc_attempt_attack_npc(self, attacker: NPC, target: NPC):
        """Handles an NPC's attempt to attack another NPC."""
        if attacker.physical.is_dead or target.physical.is_dead:
            return

        # Simple damage calculation for now, bypassing LLM for NPC vs NPC
        damage = random.randint(1, 4) # Example: 1d4 damage

        # Check if player can see the attack to log it
        can_player_see = self.player_fov_map[attacker.x, attacker.y] or self.player_fov_map[target.x, target.y]

        if can_player_see:
            self.add_message_to_chat_log(f"The {attacker.name} attacks the {target.name} for {damage} damage!")

        self.log_event(
            event_type="combat_attack",
            description="{subject} attacked {target}.",
            subject_id=attacker.id,
            target_id=target.id,
            location=(attacker.x, attacker.y)
        )

        was_killed = target.take_damage(damage, self)

        if was_killed:
            if can_player_see:
                self.add_message_to_chat_log(f"The {target.name} has been killed by the {attacker.name}!")
            self.handle_npc_death(target, killer_id=attacker.id)
            if self._is_predator(attacker):
                attacker.physical.hunger = 0
                attacker.schedule.current_task = "idle"
                attacker.task_target_entity_id = None

    def _find_nearest_food_vendor(self, npc: NPC) -> Building | None:
        """Finds the nearest building that sells food (e.g., general store, bakery)."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        food_vendors = [b for b in npc_village.buildings if b.building_type in ["general_store", "bakery"]]
        if not food_vendors:
            return None

        closest_vendor = None
        min_dist_sq = float('inf')

        for building in food_vendors:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_vendor = building

        return closest_vendor

    def _find_nearest_lumber_mill(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'lumber_mill' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        lumber_mills = [b for b in npc_village.buildings if b.building_type == "lumber_mill"]
        if not lumber_mills:
            return None

        closest_mill = None
        min_dist_sq = float('inf')

        for building in lumber_mills:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_mill = building

        return closest_mill

    def _find_nearest_mine(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'mine' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        mines = [b for b in npc_village.buildings if b.building_type == "mine"]
        if not mines:
            return None

        closest_mine = None
        min_dist_sq = float('inf')

        for building in mines:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_mine = building

        return closest_mine

    def _find_nearest_farm(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'farm' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        farms = [b for b in npc_village.buildings if b.building_type == "farm"]
        if not farms:
            return None

        closest_farm = None
        min_dist_sq = float('inf')

        for building in farms:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_farm = building

        return closest_farm

    def _find_nearest_mill(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'mill' type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            return None

        mills = [b for b in npc_village.buildings if b.building_type == "mill"]
        if not mills:
            return None

        closest_mill = None
        min_dist_sq = float('inf')

        for building in mills:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_mill = building

        return closest_mill

    def _get_village_for_npc(self, npc: NPC, by_coords: bool = False) -> Village | None:
        """
        Finds the village object an NPC is associated with.
        Can find by home building ID or by current coordinates.
        """
        if not by_coords and npc.schedule.home_building_id:
            # Find village by home building (for residents)
            for y_idx, row in enumerate(self.chunks):
                for x_idx, chk in enumerate(row):
                    if chk.village:
                        if self.buildings_by_id.get(npc.schedule.home_building_id) in chk.village.buildings:
                            return chk.village
        else:
            # Find village by current NPC coordinates (for travelers)
            chunk_x = npc.x // CHUNK_SIZE
            chunk_y = npc.y // CHUNK_SIZE
            if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
                chunk = self.chunks[chunk_y][chunk_x]
                if chunk.village:
                    return chunk.village
        return None

    def _find_nearest_building_of_type(self, npc: NPC, building_type: str) -> Building | None:
        """Finds the nearest building of a specific type in the NPC's village."""
        npc_village = self._get_village_for_npc(npc)
        if not npc_village:
            # If no village, maybe search all buildings in a radius? For now, only village NPCs report.
            return None

        target_buildings = [b for b in npc_village.buildings if b.building_type == building_type]
        if not target_buildings:
            return None

        closest_building = None
        min_dist_sq = float('inf')

        for building in target_buildings:
            dist_sq = (npc.x - building.global_center_x)**2 + (npc.y - building.global_center_y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_building = building

        return closest_building

    def _find_nearest_tavern(self, npc: NPC) -> Building | None:
        """Finds the nearest building with a 'tavern' type in the NPC's village."""
        return self._find_nearest_building_of_type(npc, "tavern")

    def _npc_eat_from_inventory(self, npc: NPC, inventory: dict, is_building_inventory: bool = False) -> tuple[bool, bool]:
        """
        Searches an inventory for food and consumes one item if found.
        Returns (found_food: bool, consumed_food: bool).
        `found_food` is True if any food item exists.
        `consumed_food` is True if a food item was successfully consumed.
        """
        food_item_key = None
        for item_key, qty in inventory.items():
            if qty > 0:
                item_def = ITEM_DEFINITIONS.get(item_key, {})
                on_use = item_def.get("on_use", {})
                if on_use.get("reduces_hunger", 0) > 0:
                    food_item_key = item_key
                    break  # Found a food item to eat

        if food_item_key:
            item_def = ITEM_DEFINITIONS[food_item_key]
            on_use = item_def["on_use"]
            inventory[food_item_key] -= 1
            if inventory[food_item_key] <= 0:
                del inventory[food_item_key]

            npc.hunger = max(0, npc.hunger - on_use["reduces_hunger"])

            # location = "at home" if is_building_inventory else "from their pack"
            # self.add_message_to_chat_log(f"{npc.name} eats a {item_def.get('name', food_item_key)} {location}.")

            return True, True  # Found food, and ate it

        return False, False  # Did not find food, did not eat

    def complete_contract_delivery(self, contract_id: str, turn_in_npc: NPC):
        """Handles player attempting to turn in a contract delivery."""
        if contract_id not in self.player.economic.active_contracts:
            self.add_message_to_chat_log("Error: Contract not found or already completed.")
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                 self.chat_ui_history.append((turn_in_npc.name, "Hmm, I don't recall that arrangement."))
            return

        contract = self.player.economic.active_contracts[contract_id]
        # Ensure this is the correct NPC to turn into, using npc_id stored in contract
        if contract.get("turn_in_npc_id") != turn_in_npc.id: # Check against NPC's actual ID
            self.add_message_to_chat_log("This is not the right person for this delivery.")
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                 self.chat_ui_history.append((turn_in_npc.name, "Are you sure you have that for me?"))
            return

        item_key = contract["item_key"]
        qty_needed = contract["quantity_needed"]
        player_has_qty = self.player.economic.inventory.get(item_key, 0)

        if player_has_qty >= qty_needed:
            self.player.economic.inventory[item_key] = player_has_qty - qty_needed
            if self.player.economic.inventory[item_key] <= 0:
                del self.player.economic.inventory[item_key]

            self.player.economic.money += contract["reward"]
            completion_msg = f"Delivery complete! You gave {qty_needed} {item_key}(s) and received {contract['reward']} money."
            self.add_message_to_chat_log(completion_msg) # Log to main game log

            # Add to chat UI history if chat is active with this NPC
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                self.chat_ui_history.append(("System", completion_msg))
                self.chat_ui_history.append((turn_in_npc.name, f"Excellent work! Here's your {contract['reward']} coins."))
                if len(self.chat_ui_history) > self.chat_ui_max_history:
                    self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]
                self.chat_ui_scroll_offset = 0

    def _get_witnesses_to_action(self, x: int, y: int, action_type: str) -> list['NPC']:
        """Finds NPCs who can see a location and would consider the action a crime."""
        witnesses = []
        for npc in self.village_npcs + self.npcs: # Check all NPCs
            if npc.is_dead or isinstance(npc, Animal): # Animals can't be witnesses
                continue

            # Check if the NPC can see the location of the crime
            if npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][x, y]:
                # Simple logic for now: most villagers will witness most crimes.
                # Future: More nuanced logic based on NPC personality, relationship to player, etc.
                if action_type in ["assault", "lockpicking", "theft"]:
                    # Guards and Sheriffs will always be witnesses
                    if npc.economic.profession in ["Guard", "Sheriff"]:
                        witnesses.append(npc)
                    # For other NPCs, maybe a chance based on personality
                    elif npc.social.personality not in ["careless", "fearful"]: # Example personalities who might not report
                        witnesses.append(npc)
        return witnesses

    def _get_interactables_at(self, x: int, y: int) -> list:
        """Returns a list of all interactable entities at a given coordinate."""
        entities = []

        # 1. Add the tile itself
        tile = self.get_tile_at(x, y)
        if tile:
            entities.append({"type": "tile", "data": tile, "name": tile.name})

        # 2. Add items on the ground
        if (x, y) in self.items_on_map:
            for item_info in self.items_on_map[(x, y)]:
                item_def = self.get_item_definition(item_info["item_key"])
                entities.append({
                    "type": "item",
                    "data": item_info,
                    "name": item_def.get("name", item_info["item_key"])
                })

        # 3. Add NPCs
        for npc in self.village_npcs + self.npcs:
            if npc.x == x and npc.y == y and not npc.is_dead:
                entities.append({"type": "npc", "data": npc, "name": npc.name})

        # 4. Add Buildings
        building = self.get_building_at(x,y)
        if building:
            entities.append({"type": "building", "data": building, "name": building.building_type})

        return entities

    def get_item_definition(self, item_key: str) -> dict | None:
        """
        Gets the definition for an item. Handles dynamic book keys.
        Returns a copy of the definition to prevent modification of the original.
        """
        if item_key.startswith("book_"):
            book_id = item_key.split("_", 1)[1]
            book = next((b for b in self.books if b.id == book_id), None)
            if book:
                base_def_key = f"book_{book.book_type}"
                base_def = ITEM_DEFINITIONS.get(base_def_key)
                if base_def:
                    # Create a copy and override dynamic properties
                    dynamic_def = base_def.copy()
                    dynamic_def["name"] = book.title
                    dynamic_def["description"] = f"A book titled '{book.title}' by {book.author_name}."
                    return dynamic_def
            # Fallback if book not found, return the base chronicle definition
            return ITEM_DEFINITIONS.get("book_chronicle", {}).copy()

        return ITEM_DEFINITIONS.get(item_key, {}).copy()

    def _get_actions_for_entity(self, entity: dict) -> list[str]:
        """Returns a list of available actions for a given entity dictionary."""
        actions = []
        entity_type = entity["type"]
        entity_data = entity["data"]

        if entity_type == "npc":
            if isinstance(entity_data, Animal):
                animal_def = ANIMAL_DEFINITIONS.get(entity_data.animal_type, {})
                if animal_def.get("rideable") and entity_data.is_tame and entity_data.owner == self.player:
                    if self.player.state.is_riding and self.player.state.riding_animal_id == entity_data.id:
                        actions.append("Dismount")
                    else:
                        actions.append("Ride")
                actions.append("Feed")
                actions.append("Attack")
            else: # It's a humanoid NPC
                actions.extend(["Talk", "Attack"])
                if entity_data.profession in ["Merchant", "Miller"]:
                    actions.append("Trade")
        elif entity_type == "item":
            actions.append("Pick up")
            if entity_data["item_key"].startswith("book_"):
                actions.append("Read")
        elif entity_type == "tile":
            if isinstance(entity_data, Tree) and entity_data.is_choppable:
                actions.append("Chop")
            elif entity_data.properties.get("is_door"):
                actions.append("Toggle Door")
            elif entity_data.name == "Animal Corpse":
                actions.append("Butcher")
            elif entity_data.name == "Plains" and self.player.has_item("stone_hoe"):
                actions.append("Till Soil")
            elif entity_data.name == "Tilled Soil" and self.player.has_item("wheat_seeds"):
                actions.append("Plant Seeds")
            elif entity_data.name == "Wheat":
                actions.append("Harvest")
        elif entity_type == "building":
            if entity_data.building_type == "house" and not entity_data.player_owned and not entity_data.residents:
                actions.append("Claim House")

        # Add a "Shear" action for shearable animals
        if entity_type == "npc" and isinstance(entity_data, Animal):
            animal_def = ANIMAL_DEFINITIONS.get(entity_data.animal_type, {})
            if "shearable" in animal_def:
                actions.append("Shear")

        actions.append("Examine") # Universal action
        return actions

    def serve_jail_time(self):
        """Handles the process of putting the player in jail."""
        # Find the nearest sheriff's office.
        sheriff_office = None
        min_dist_sq = float('inf')
        for building in self.buildings_by_id.values():
            if building.building_type == "sheriff_office":
                dist_sq = (self.player.x - building.global_center_x)**2 + (self.player.y - building.global_center_y)**2
                if dist_sq < min_dist_sq:
                    min_dist_sq = dist_sq
                    sheriff_office = building

        if not sheriff_office:
            self.add_message_to_chat_log("The sheriff pats you down but has nowhere to hold you. You're free to go... for now.")
            self.player.economic.bounty = self.player.economic.bounty // 2 # Reduce bounty anyway
            return

        # Dynamically create a 3x3 jail cell in the top-left corner of the building's interior.
        cell_origin_x = sheriff_office.global_origin_x + 1
        cell_origin_y = sheriff_office.global_origin_y + 1
        cell_center_x = cell_origin_x + 1
        cell_center_y = cell_origin_y + 1
        door_x, door_y = cell_origin_x + 1, cell_origin_y + 2

        jail_bar_def = TILE_DEFINITIONS["jail_bars"]
        iron_door_def = DECORATION_ITEM_DEFINITIONS["iron_door_closed"]
        floor_def = TILE_DEFINITIONS["wood_floor"]

        # Carve out the cell
        for y_offset in range(3):
            for x_offset in range(3):
                is_border = x_offset == 0 or x_offset == 2 or y_offset == 0 or y_offset == 2
                tile_x, tile_y = cell_origin_x + x_offset, cell_origin_y + y_offset

                if is_border:
                    if y_offset == 2 and x_offset == 1: # Door on the bottom wall
                        self._change_map_tile((tile_x, tile_y), iron_door_def)
                    else:
                        self._change_map_tile((tile_x, tile_y), jail_bar_def)
                else: # Interior of the cell
                    self._change_map_tile((tile_x, tile_y), floor_def)


        # Move player to cell
        self.player.x = cell_center_x
        self.player.y = cell_center_y
        self.player.state.is_jailed = True
        self.player.state.jail_cell_coords = (door_x, door_y) # Store the DOOR coordinates
        self.player.state.jail_time_remaining = 500 # Set jail time
        self.add_message_to_chat_log("You've been thrown in jail!")

        # Reduce bounty
        self.player.economic.bounty = 0
        self.add_message_to_chat_log("Your bounty has been cleared.")

        self._update_player_fov() # Update FOV from new position


        del self.player.economic.active_contracts[contract_id]

        # If chat UI was active, maybe close it or go back to general talk mode
        if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                self.chat_ui_mode = "talk" # Or could close: self.chat_ui_active = False; context.stop_text_input()
                                           # For now, let's keep it open in talk mode.
                # Add a follow-up generic line from NPC after payment.
                self.chat_ui_history.append((turn_in_npc.name, "Anything else I can help you with?"))


        else:
            needed_more = qty_needed - player_has_qty
            short_msg = f"You don't have enough {item_key}s. You still need {needed_more} more."
            self.add_message_to_chat_log(short_msg) # Log to main game log
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                self.chat_ui_history.append(("System", short_msg))
                self.chat_ui_history.append((turn_in_npc.name, f"Looks like you're still short on those. Come back when you have all {qty_needed}."))
                if len(self.chat_ui_history) > self.chat_ui_max_history:
                    self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]
                self.chat_ui_scroll_offset = 0

    def _get_chunk_from_building(self, building_to_find: Building) -> tuple[Chunk | None, int, int]:
        """Finds the chunk a building belongs to and its global starting coords."""
        # This is inefficient. Ideally, Building objects would store their parent chunk's coords or reference.
        for y_idx, chunk_row in enumerate(self.chunks):
            for x_idx, chunk in enumerate(chunk_row):
                if chunk and chunk.village and building_to_find in chunk.village.buildings:
                    return chunk, x_idx * CHUNK_SIZE, y_idx * CHUNK_SIZE
        return None, 0, 0

    def _building_contains_item_with_interaction(self, building: Building, interaction_hint: str) -> bool:
        """Checks if a building contains a decoration with a specific interaction_hint."""
        if not building:
            return False

        building_chunk, chunk_start_x, chunk_start_y = self._get_chunk_from_building(building)

        if not building_chunk or not building_chunk.is_generated or not building_chunk.tiles:
            # self.add_message_to_chat_log(f"Debug: Bed check - Building chunk {building_chunk.biome if building_chunk else 'N/A'} not generated or no tiles for building {building.id[:6]}")
            return False

        # Building.x and .y are local to the chunk's tile grid.
        # Iterate through the tiles *within the building's footprint on the chunk's tile grid*.
        for y_offset in range(building.height):
            for x_offset in range(building.width):
                # Don't check border walls of the building itself as locations for items like beds
                if x_offset == 0 or x_offset == building.width -1 or y_offset == 0 or y_offset == building.height -1:
                    continue

                tile_in_chunk_x = building.x + x_offset
                tile_in_chunk_y = building.y + y_offset

                if 0 <= tile_in_chunk_x < CHUNK_SIZE and 0 <= tile_in_chunk_y < CHUNK_SIZE:
                    tile = building_chunk.tiles[tile_in_chunk_y][tile_in_chunk_x]
                    if tile and hasattr(tile, 'properties') and tile.properties.get("interaction_hint") == interaction_hint:
                        # self.add_message_to_chat_log(f"Debug: Found '{interaction_hint}' in building {building.id[:6]} at {tile_in_chunk_x},{tile_in_chunk_y} (local)")
                        return True
        # self.add_message_to_chat_log(f"Debug: No '{interaction_hint}' found in building {building.id[:6]}")
        return False

    def _change_map_tile(self, coords: tuple[int, int], new_tile_def: dict, original_tree_type: str | None = None):
        """Changes a tile on the map to a new one based on a TILE_DEFINITION."""
        x, y = coords
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE

        if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
            chunk = self.chunks[chunk_y][chunk_x]
            if chunk and chunk.tiles:
                new_tile = Tile(
                    char=new_tile_def["char"],
                    color=new_tile_def["color"],
                    passable=new_tile_def["passable"],
                    name=new_tile_def["name"],
                    properties=new_tile_def.get("properties", {})
                )
                if original_tree_type:
                    new_tile.original_tree_type = original_tree_type

                chunk.tiles[local_y][local_x] = new_tile
                # Update transparency map
                self.transparency_map[y, x] = not new_tile.blocks_fov

    def player_attempt_chop_tree(self, tree_x: int, tree_y: int):
        """Handles the player's attempt to chop a tree at the given world coordinates."""
        axe_item_key = "axe_stone"
        if not self.player.has_item(axe_item_key):
            self.add_message_to_chat_log("You need an axe to chop trees.")
            return

        target_tile = self.get_tile_at(tree_x, tree_y)

    def player_attempt_butcher(self, corpse_x: int, corpse_y: int):
        """Handles the player's attempt to butcher an animal corpse."""
        # Check for required tool
        knife_item_key = "knife_stone"
        if not self.player.has_item(knife_item_key):
            self.add_message_to_chat_log("You need a knife to butcher a corpse.")
            return

        target_tile = self.get_tile_at(corpse_x, corpse_y)

        if not (target_tile and target_tile.name == "Animal Corpse"):
            self.add_message_to_chat_log("There is nothing to butcher here.")
            return

        animal_type = target_tile.properties.get("animal_type")
        if not animal_type or animal_type not in ANIMAL_DEFINITIONS:
            self.add_message_to_chat_log("This corpse is unidentifiable.")
            # Turn it into bones anyway to clear it
            self._change_map_tile((corpse_x, corpse_y), DECORATION_ITEM_DEFINITIONS["bones"])
            return

        self.add_message_to_chat_log(f"You begin butchering the {animal_type}...")

        animal_def = ANIMAL_DEFINITIONS[animal_type]
        loot_table = animal_def.get("loot_drops", {})
        items_looted_messages = []

        for item_key, loot_info in loot_table.items():
            if random.random() < loot_info.get("chance", 0):
                quantity_info = loot_info["quantity"]
                if isinstance(quantity_info, list) and len(quantity_info) == 2:
                    quantity = random.randint(quantity_info[0], quantity_info[1])
                else:
                    quantity = int(quantity_info)

                if quantity > 0:
                    self.player.add_item(item_key, quantity)
                    item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    items_looted_messages.append(f"{quantity}x {item_name}")

        if items_looted_messages:
            self.add_message_to_chat_log(f"You recovered: {', '.join(items_looted_messages)}.")
        else:
            self.add_message_to_chat_log("You failed to recover anything useful from the carcass.")

        # Replace corpse with bones
        self._change_map_tile((corpse_x, corpse_y), DECORATION_ITEM_DEFINITIONS["bones"])

    def player_attempt_feed_animal(self, animal_npc: Animal):
        """Handles the player's attempt to feed an animal."""
        if not isinstance(animal_npc, Animal):
            self.add_message_to_chat_log("You can't feed that.")
            return

        animal_def = ANIMAL_DEFINITIONS.get(animal_npc.animal_type)
        if not animal_def or not animal_def.get("tameable"):
            self.add_message_to_chat_log(f"The {animal_npc.name} is not interested in being fed.")
            return

        food_item_key = animal_def.get("favorite_food")
        taming_difficulty = animal_def.get("taming_difficulty", 5)
        taming_chance = 1.0 / taming_difficulty

        if not self.player.has_item(food_item_key):
            food_name = ITEM_DEFINITIONS.get(food_item_key, {}).get("name", food_item_key)
            self.add_message_to_chat_log(f"You need a {food_name} to feed the {animal_npc.name}.")
            return

        self.player.remove_item(food_item_key, 1)
        food_name = ITEM_DEFINITIONS.get(food_item_key, {}).get("name", food_item_key)
        self.add_message_to_chat_log(f"You offer a {food_name} to the {animal_npc.name}.")

        if random.random() < taming_chance:
            animal_npc.is_tame = True
            animal_npc.owner = self.player
            self.add_message_to_chat_log(f"The {animal_npc.name} seems to trust you now!")
            # Change behavior to follow owner
            animal_npc.behavior = "Follow-Owner"
        else:
            self.add_message_to_chat_log(f"The {animal_npc.name} ate the {food_name} but is still wary of you.")

    def player_attempt_ride_animal(self, animal_npc: Animal):
        """Handles the player's attempt to ride an animal."""
        if self.player.state.is_riding:
            self.add_message_to_chat_log("You are already riding something.")
            return

        animal_def = ANIMAL_DEFINITIONS.get(animal_npc.animal_type)
        if not (animal_def and animal_def.get("rideable") and animal_npc.is_tame and animal_npc.owner == self.player):
            self.add_message_to_chat_log(f"You can't ride the {animal_npc.name}.")
            return

        self.player.state.is_riding = True
        self.player.state.riding_animal_id = animal_npc.id
        animal_npc.is_being_ridden = True
        animal_npc.rider_id = self.player.id

        # Move player to the animal's location
        self.player.x = animal_npc.x
        self.player.y = animal_npc.y
        self._update_player_fov() # Update FOV from new position

        self.add_message_to_chat_log(f"You mount the {animal_npc.name}.")
        # The animal should stop its current path when mounted
        animal_npc.current_path = []
        animal_npc.current_destination_coords = None

    def player_attempt_shear(self, animal_npc: Animal):
        """Handles the player's attempt to shear a sheep."""
        if not isinstance(animal_npc, Animal) or "shearable" not in ANIMAL_DEFINITIONS.get(animal_npc.animal_type, {}):
            self.add_message_to_chat_log("You can't shear that.")
            return

        animal_def = ANIMAL_DEFINITIONS[animal_npc.animal_type]
        shearable_def = animal_def["shearable"]
        regrowth_days = shearable_def["regrowth_days"]
        days_since_shorn = (self.game_time - animal_npc.last_shorn_time) // DAY_LENGTH_TICKS

        if days_since_shorn < regrowth_days:
            self.add_message_to_chat_log(f"The {animal_npc.name} is not woolly enough to be shorn yet.")
            return

        # Check for shears tool
        if not self.player.has_item("shears"):
            self.add_message_to_chat_log("You need shears to shear a sheep.")
            return

        quantity_info = shearable_def["quantity"]
        if isinstance(quantity_info, list) and len(quantity_info) == 2:
            quantity = random.randint(quantity_info[0], quantity_info[1])
        else:
            quantity = int(quantity_info)

        if quantity > 0:
            item_yield_key = shearable_def["item_yield"]
            self.player.add_item(item_yield_key, quantity)
            item_name = ITEM_DEFINITIONS.get(item_yield_key, {}).get("name", item_yield_key)
            self.add_message_to_chat_log(f"You shear the {animal_npc.name} and get {quantity}x {item_name}.")
            animal_npc.last_shorn_time = self.game_time
        else:
            self.add_message_to_chat_log(f"You attempt to shear the {animal_npc.name}, but get no wool.")

    def player_attempt_dismount(self, animal_npc: Animal):
        """Handles the player's attempt to dismount an animal."""
        if not self.player.state.is_riding or self.player.state.riding_animal_id != animal_npc.id:
            self.add_message_to_chat_log("You are not riding this animal.")
            return

        # Find a safe spot to dismount to (adjacent and passable)
        dismount_x, dismount_y = self._find_best_adjacent_tile(animal_npc.x, animal_npc.y, self.player)

        if dismount_x is None:
            self.add_message_to_chat_log("There is no space to dismount here.")
            return

        # Update states
        self.player.state.is_riding = False
        self.player.state.riding_animal_id = None
        animal_npc.is_being_ridden = False
        animal_npc.rider_id = None

        # Move player
        self.player.x = dismount_x
        self.player.y = dismount_y
        self._update_player_fov()

        self.add_message_to_chat_log(f"You dismount the {animal_npc.name}.")

        if isinstance(target_tile, Tree) and target_tile.is_choppable:
            original_tree_type = target_tile.tree_type
            yielded_resources = target_tile.chop()

            if yielded_resources:
                self.add_message_to_chat_log(f"You chopped the {target_tile.original_name}!")
                self.emit_sound(tree_x, tree_y, "tree_fall", volume=15, source_entity_id=self.player.id)
                for resource_key, quantity in yielded_resources.items():
                    if resource_key in ITEM_DEFINITIONS:
                        self.player.add_item(resource_key, quantity)
                        self.add_message_to_chat_log(f"  + {quantity} {ITEM_DEFINITIONS[resource_key]['name']}")
                    else:
                        self.add_message_to_chat_log(f"  (Received undefined resource: {resource_key} x{quantity})")

                stump_key = target_tile.becomes_on_chop_key
                stump_def = TILE_DEFINITIONS.get(stump_key)
                if stump_def:
                    self._change_map_tile((tree_x, tree_y), stump_def, original_tree_type=original_tree_type)
                    new_stump_tile = self.get_tile_at(tree_x, tree_y)
                    if new_stump_tile:
                        new_stump_tile.regrowth_timer = 100

                # Handle axe degradation/breaking
                axe_def = ITEM_DEFINITIONS.get(axe_item_key)
                if axe_def and not axe_def.get("stackable", False):
                    degrade_chance = axe_def.get("properties", {}).get("durability_chance_to_degrade", 0.05) # 5% chance
                    if random.random() < degrade_chance:
                        axe_indices = self.player.get_item_instance_indices(axe_item_key)
                        if axe_indices:
                            axe_to_degrade = self.player.get_item_by_index(axe_indices[0])
                            if axe_to_degrade and "durability" in axe_to_degrade:
                                axe_to_degrade["durability"] -= 1
                                if axe_to_degrade["durability"] <= 0:
                                    self.player.remove_item(axe_item_key, 1, specific_instance_index=axe_indices[0])
                                    self.add_message_to_chat_log(f"Your {axe_def['name']} broke during use!")
                                    if "broken_tool_handle" in ITEM_DEFINITIONS:
                                        self.player.add_item("broken_tool_handle", 1)
                                        self.add_message_to_chat_log("You salvaged a broken tool handle.")
                                else:
                                    self.add_message_to_chat_log(f"Your {axe_def['name']} shows some wear.")
            else:
                self.add_message_to_chat_log("Nothing was yielded from the tree.")
        elif isinstance(target_tile, Tree) and not target_tile.is_choppable:
            self.add_message_to_chat_log(f"This {target_tile.name} has already been chopped.")
        else:
            self.add_message_to_chat_log("There's nothing to chop there.")

    def player_attempt_plant_sapling(self, target_x: int, target_y: int):
        """Handles the player's attempt to plant a sapling."""
        if not self.player.has_item("sapling"):
            self.add_message_to_chat_log("You don't have any saplings to plant.")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and target_tile.name in ["Plains", "Tilled Soil"]:
            self.player.remove_item("sapling", 1)
            sapling_def = TILE_DEFINITIONS["sapling"]
            self._change_map_tile((target_x, target_y), sapling_def)
            self.add_message_to_chat_log("You planted a sapling.")
        else:
            self.add_message_to_chat_log("You can't plant a sapling there.")

    def add_message_to_chat_log(self, message: str):
        self.chat_log.append(message)
        # Keep chat log to a reasonable size
        if len(self.chat_log) > 100:
            self.chat_log.pop(0)

    def player_attempt_sit(self, target_x: int, target_y: int):
        """Handles the player's attempt to sit on an object."""
        if self.player.state.is_sitting:
            # If already sitting and trying to interact with the same spot, stand up.
            if self.player.state.sitting_on_object_at == (target_x, target_y):
                self.player_attempt_stand_up()
            else:
                self.add_message_to_chat_log("You are already sitting. Stand up first ('E' or move).")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and hasattr(target_tile, 'properties'):
            interaction_hint = target_tile.properties.get("interaction_hint")
            if interaction_hint == "sit":
                self.player.state.is_sitting = True
                self.player.char = ord('s') # Example sitting character
                self.player.state.sitting_on_object_at = (target_x, target_y)
                self.add_message_to_chat_log(f"You sit down on the {target_tile.name}.")
            else:
                # self.add_message_to_chat_log("You can't sit there.") # Only message if no other interaction found by 'E'
                return False # Indicate sit failed, so 'E' can try other interactions like chop
        else:
            # self.add_message_to_chat_log("There's nothing to sit on there.")
            return False # Indicate sit failed
        return True # Indicate sit succeeded or an action related to sitting was taken

    def player_attempt_stand_up(self):
        """Handles the player standing up."""
        if self.player.state.is_sitting:
            self.player.state.is_sitting = False
            self.player.char = self.player.state.original_char
            self.add_message_to_chat_log("You stand up.")
            self.player.state.sitting_on_object_at = None
        # No message if not sitting, or handled by caller

    def player_attempt_sleep(self, target_x: int, target_y: int):
        """Handles the player's attempt to sleep in a bed."""
        if self.player.state.is_sitting:
            self.add_message_to_chat_log("You should stand up before trying to sleep.")
            return False

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and hasattr(target_tile, 'properties'):
            interaction_hint = target_tile.properties.get("interaction_hint")
            if interaction_hint == "sleep":
                self.add_message_to_chat_log(f"You lie down on the {target_tile.name} to rest.")
                self.player.state.is_sleeping = True # Brief state change

                # --- Advance Game Time (Simplified) ---
                # For a more complex simulation, this would involve a loop calling NPC updates.
                # For now, a simple jump. NPCs will "catch up" on their next schedule check.
                time_to_advance = DAY_LENGTH_TICKS // 3 # Sleep for 1/3 of a day (e.g., 8 hours)
                self.game_time += time_to_advance
                self.add_message_to_chat_log(f"Several hours pass...")

                # Optional: Player benefits
                heal_amount = self.player.combat.max_hp // 4 # Heal 25% of max HP
                self.player.combat.hp = min(self.player.combat.max_hp, self.player.combat.hp + heal_amount)
                if heal_amount > 0:
                     self.add_message_to_chat_log(f"You feel somewhat rested and heal for {heal_amount} HP.")
                else:
                    self.add_message_to_chat_log("You feel somewhat rested.")

                self.player.state.is_sleeping = False # Player wakes up
                return True # Sleep action was successful
            else:
                # Not a bed
                return False
        else:
            # No interactable tile
            return False

    def attempt_persuasion(self, npc_target: NPC, player_goal_text: str):
        """Handles the player's attempt to persuade an NPC."""
        if not npc_target:
            self.add_message_to_chat_log("No one specific to persuade.")
            return

        player_rep = self.player.social.reputation
        prompt = LLM_PROMPTS["npc_persuasion_check"].format(
            npc_name=npc_target.name,
            npc_personality=npc_target.social.personality,
            npc_attitude=npc_target.attitude_to_player,
            player_social_skill=self.player.social.social_skill,
            player_criminal_points=player_rep.get(REP_CRIMINAL, 0),
            player_hero_points=player_rep.get(REP_HERO, 0),
            player_persuasion_goal_text=player_goal_text
        )

        response_str = self._call_ollama(prompt)
        if not response_str:
            self.add_message_to_chat_log(f"{npc_target.name} doesn't seem to react to your attempt.")
            return

        try:
            response_json = json.loads(response_str)
            success = response_json.get("success", False)
            reaction_dialogue = response_json.get("reaction_dialogue", "...")
            new_attitude = response_json.get("new_attitude_to_player", npc_target.attitude_to_player)

            # Add NPC's reaction dialogue to chat UI history
            self.chat_ui_history.append((npc_target.name, reaction_dialogue))

            if new_attitude != npc_target.attitude_to_player:
                attitude_msg = f"({npc_target.name}'s attitude towards you is now '{new_attitude}')"
                self.chat_ui_history.append(("System", attitude_msg))
                # Also log to main game log for now, as attitude change is significant
                self.add_message_to_chat_log(attitude_msg)
                npc_target.attitude_to_player = new_attitude

            if success:
                success_msg = "(Your persuasion attempt seems successful!)"
                self.chat_ui_history.append(("System", success_msg))
                self.add_message_to_chat_log(success_msg) # Also log globally
                # Future: Implement actual game effect of success here
            else:
                failure_msg = "(Your persuasion attempt seems to have failed.)"
                self.chat_ui_history.append(("System", failure_msg))
                self.add_message_to_chat_log(failure_msg) # Also log globally
                # Future: Implement actual game effect of failure here

            # Ensure chat history doesn't exceed max and reset scroll
            if len(self.chat_ui_history) > self.chat_ui_max_history:
                self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]
            self.chat_ui_scroll_offset = 0
        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"{npc_target.name} gives a non-committal grunt. (LLM Format Error)")

    def _handle_npc_conversations(self):
        conversing_npcs = [npc for npc in self.village_npcs if npc.conversation_partner_id is not None]
        for npc in conversing_npcs:
            if npc.last_conversation_time + 10 < self.game_time:
                partner = next((p for p in self.village_npcs if p.id == npc.conversation_partner_id), None)
                if partner:
                    self._continue_npc_conversation(npc, partner)
                else:
                    npc.conversation_partner_id = None

    def _continue_npc_conversation(self, speaker, listener):
        if len(speaker.current_conversation) >= 6:
            self.add_message_to_chat_log(f"The conversation between {speaker.name} and {listener.name} ends.")
            speaker.conversation_partner_id = None
            listener.conversation_partner_id = None
            speaker.current_conversation = []
            listener.current_conversation = []
            speaker.conversation_cooldown = random.randint(100, 200)
            listener.conversation_cooldown = random.randint(100, 200)
            return

        event_summary = "the weather"
        if speaker.known_events:
            event = random.choice(list(speaker.known_events.values()))
            event_summary = event.description

        history = "\n".join(speaker.current_conversation)
        prompt = LLM_PROMPTS["npc_npc_conversation"].format(
            speaker_name=speaker.name,
            speaker_personality=speaker.personality,
            speaker_attitude_to_listener=speaker.relationships.get(listener.id, 50),
            listener_name=listener.name,
            listener_personality=listener.personality,
            event_summary=event_summary,
            conversation_history=history
        )
        dialogue = self._call_ollama(prompt)
        if dialogue:
            self.add_message_to_chat_log(f"{speaker.name} to {listener.name}: {dialogue}")
            speaker.current_conversation.append(f"{speaker.name}: {dialogue}")
            listener.current_conversation.append(f"{speaker.name}: {dialogue}")

        speaker.last_conversation_time = self.game_time
        listener.last_conversation_time = self.game_time

        # Swap speaker and listener for the next turn
        listener.conversation_partner_id = speaker.id
        speaker.conversation_partner_id = listener.id

    def _start_npc_socialization(self, npc: NPC):
        if npc.conversation_cooldown > 0:
            npc.conversation_cooldown -= 1
            return

        potential_partners = [
            p for p in self.village_npcs
            if p.id != npc.id and not p.physical.is_dead and abs(npc.x - p.x) + abs(npc.y - p.y) < 10
               and p.conversation_partner_id is None and p.conversation_cooldown == 0
        ]

        if not potential_partners:
            return

        partner = random.choice(potential_partners)
        npc.conversation_partner_id = partner.id
        partner.conversation_partner_id = npc.id
        npc.last_conversation_time = self.game_time
        partner.last_conversation_time = self.game_time

        # For now, let's just log that a conversation has started.
        self.add_message_to_chat_log(f"{npc.name} and {partner.name} start a conversation.")

    def player_attempt_attack(self, target_npc: NPC):
        if not target_npc:
            self.add_message_to_chat_log("No target selected for attack.")
            return

        if target_npc.is_dead:
            self.add_message_to_chat_log(f"{target_npc.name} is already defeated.")
            return

        player_weapon_name = "Fists"
        if self.player.economic.inventory.get("axe_stone", 0) > 0:
            player_weapon_name = ITEM_DEFINITIONS["axe_stone"]["name"]

        player_melee_skill = getattr(self.player, 'melee_skill', 5)

        # Determine NPC toughness description based on their defense bonus
        npc_toughness_desc = "unarmored"
        if target_npc.defense_bonus > 8:
            npc_toughness_desc = "heavily armored"
        elif target_npc.defense_bonus > 4:
            npc_toughness_desc = "armored"
        elif target_npc.defense_bonus > 0:
            npc_toughness_desc = "lightly armored"

        prompt = LLM_PROMPTS["adjudicate_player_attack"].format(
            player_weapon_name=player_weapon_name,
            player_melee_skill=player_melee_skill,
            npc_name=target_npc.name,
            npc_toughness=npc_toughness_desc
        )

        response_str = self._call_ollama(prompt)

        if not response_str:
            self.add_message_to_chat_log("Your attack seems to have no effect (LLM Comms Error).")
            if not target_npc.is_hostile_to_player and not target_npc.is_dead:
                target_npc.is_hostile_to_player = True
                self.add_message_to_chat_log(f"{target_npc.name} becomes hostile due to your aggression!")
            return

        try:
            response_json = json.loads(response_str)
            hit = response_json.get("hit", False)
            damage_dealt = int(response_json.get("damage_dealt", 0))
            narrative = response_json.get("narrative_feedback", "The confrontation is tense.")

            self.add_message_to_chat_log(narrative)
            self.emit_sound(self.player.x, self.player.y, "combat_attack", volume=10, source_entity_id=self.player.id) # Emit attack sound

            if hit and damage_dealt > 0:
                self.log_event(
                    event_type="combat_attack",
                    description="{subject} attacked {target}.",
                    subject_id=self.player.id,
                    target_id=target_npc.id,
                    location=(self.player.x, self.player.y)
                )
                target_npc.take_damage(damage_dealt, self)
                if target_npc.is_dead:
                    self.handle_npc_death(target_npc, killer_id=self.player.id)
            elif hit and damage_dealt <= 0: # A hit that does no damage
                self.add_message_to_chat_log(f"Your attack hits but glances off {target_npc.name} harmlessly!")

            if not target_npc.is_hostile_to_player and not target_npc.is_dead:
                 target_npc.is_hostile_to_player = True
                 self.add_message_to_chat_log(f"{target_npc.name} becomes hostile!")

        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"The outcome of your attack is unclear. (LLM Format Error: {response_str})")
            self.emit_sound(self.player.x, self.player.y, "combat_attack", volume=8, source_entity_id=self.player.id) # Still emit
            if not target_npc.is_hostile_to_player and not target_npc.is_dead:
                target_npc.is_hostile_to_player = True; self.add_message_to_chat_log(f"{target_npc.name} is angered by your confusing actions!")
        except ValueError:
            self.add_message_to_chat_log(f"The LLM provided an invalid damage amount: {response_json.get('damage_dealt') if 'response_json' in locals() else 'Unknown'}")
            self.emit_sound(self.player.x, self.player.y, "combat_attack", volume=8, source_entity_id=self.player.id) # Still emit
            if not target_npc.is_hostile_to_player and not target_npc.is_dead:
                target_npc.is_hostile_to_player = True; self.add_message_to_chat_log(f"{target_npc.name} is angered by your confusing actions!")

        # --- Witness Handling ---
        # After any attack attempt, check for witnesses to the crime of assault.
        witnesses = self._get_witnesses_to_action(target_npc.x, target_npc.y, "assault")
        if witnesses:
            self.player.adjust_reputation(REP_CRIMINAL, 10) # 10 criminal points for assault
            for witness in witnesses:
                # The victim won't also be a witness in the traditional sense, their reaction is hostility.
                if witness.id != target_npc.id:
                    self._handle_witness_reaction(witness, "assault", self.player, victim=target_npc)

    def _remove_npc_from_world(self, npc: NPC, reason="departed"):
        """
        Removes an NPC from the world lists (village_npcs, npcs, buildings) without killing them.
        Used for emigration or cleanup.
        """
        if npc in self.village_npcs:
            self.village_npcs.remove(npc)
        if npc in self.npcs:
            self.npcs.remove(npc)

        for building_obj in self.buildings_by_id.values():
            if npc in building_obj.residents:
                building_obj.residents.remove(npc)
            if npc in building_obj.occupants:
                building_obj.occupants.remove(npc)

        # Clear NPC from UI states if they were targeted
        if self.interaction_context["active"] and npc in self.interaction_context["target_entities"]:
            self.interaction_context["active"] = False
        if self.chat_ui_target_npc == npc: self.chat_ui_target_npc, self.chat_ui_active = None, False
        if self.trade_ui_npc_target == npc: self.trade_ui_npc_target, self.trade_ui_active = None, False
        if self.last_talked_to_npc == npc: self.last_talked_to_npc = None

        # self.add_message_to_chat_log(f"Debug: {npc.name} has {reason}.")

    def handle_npc_death(self, dead_npc: NPC, killer_id: int | None = None):
        self.add_message_to_chat_log(f"{dead_npc.name} has died!")

        self.log_event(
            event_type="entity_death",
            description="{subject} was killed by {target}.",
            subject_id=dead_npc.id,
            target_id=killer_id,
            location=(dead_npc.x, dead_npc.y)
        )

        npc_chunk_x, npc_chunk_y = dead_npc.x // CHUNK_SIZE, dead_npc.y // CHUNK_SIZE
        npc_local_x, npc_local_y = dead_npc.x % CHUNK_SIZE, dead_npc.y % CHUNK_SIZE

        corpse_placed_on_map = False
        if 0 <= npc_chunk_x < self.chunk_width and 0 <= npc_chunk_y < self.chunk_height:
            chunk = self.chunks[npc_chunk_y][npc_chunk_x]
            if chunk and chunk.tiles:
                corpse_key = "corpse_animal" if isinstance(dead_npc, Animal) else "corpse_humanoid"
                corpse_def = DECORATION_ITEM_DEFINITIONS.get(corpse_key)
                if corpse_def:
                    # Create a copy of the properties to avoid modifying the template
                    new_properties = corpse_def.get("properties", {}).copy()

                    # If it's an animal, store its type in the corpse's properties
                    if isinstance(dead_npc, Animal) and hasattr(dead_npc, 'animal_type'):
                        new_properties['animal_type'] = dead_npc.animal_type

                    chunk.tiles[npc_local_y][npc_local_x] = Tile(
                        char=corpse_def["char"], color=corpse_def["color"],
                        passable=corpse_def["passable"], name=corpse_def["name"],
                        properties=new_properties
                    )
                    corpse_placed_on_map = True

        if not corpse_placed_on_map: self.add_message_to_chat_log(f"(Could not place corpse for {dead_npc.name} on map)")

        self._remove_npc_from_world(dead_npc, reason="died")

        # --- Item Drops ---
        items_dropped_messages = []
        # Animal loot is now handled by butchering, so we only handle humanoid drops here.
        if not isinstance(dead_npc, Animal):
            # Drop items from inventory
            for item_key, quantity in list(dead_npc.economic.npc_inventory.items()):
                if item_key == "money": continue
                if quantity > 0:
                    self.drop_item_on_map(item_key, quantity, dead_npc.x, dead_npc.y)
                    item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    items_dropped_messages.append(f"{quantity}x {item_name}")

            # Chance to drop equipped items
            equipped_to_check = [dead_npc.equipment.weapon, dead_npc.equipment.body, dead_npc.equipment.head]
            for equipped_item_key in equipped_to_check:
                if equipped_item_key:
                    item_def = ITEM_DEFINITIONS.get(equipped_item_key, {})
                    base_drop_chance = 0.75
                    value = item_def.get("value", 0)
                    # Reduce drop chance for more valuable items
                    if value > 50:
                        drop_chance = base_drop_chance - 0.25
                    elif value > 25:
                        drop_chance = base_drop_chance - 0.1
                    else:
                        drop_chance = base_drop_chance

                    if random.random() < drop_chance:
                        self.drop_item_on_map(equipped_item_key, 1, dead_npc.x, dead_npc.y)
                        item_name = item_def.get("name", equipped_item_key)
                        items_dropped_messages.append(f"1x {item_name} (equipped)")

            if items_dropped_messages:
                self.add_message_to_chat_log(f"{dead_npc.name} dropped: {', '.join(items_dropped_messages)}.")
            else:
                self.add_message_to_chat_log(f"{dead_npc.name} dropped nothing of note.")

        # After death, emit a sound if appropriate (e.g. a shout or thud)
        # For now, let's assume death itself is not a loud sound unless it's a dramatic one.
        # self.emit_sound(dead_npc.x, dead_npc.y, "npc_death_cry", volume=8, source_entity_id=dead_npc.id)


    def player_attempt_pick_lock(self, target_x: int, target_y: int) -> bool:
        """Handles player's attempt to pick a lock."""
        if self.player.economic.inventory.get("lockpick", 0) <= 0:
            self.add_message_to_chat_log("You don't have any lockpicks.")
            return False

        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and target_tile.properties.get("is_lockable")):
            self.add_message_to_chat_log("There's nothing to pick here.")
            return False

        if not target_tile.properties.get("is_locked"):
            self.add_message_to_chat_log("It's already unlocked.")
            return True # Considered "handled" as there's no lock to pick

        lock_difficulty = target_tile.properties.get("lock_difficulty", 5)

        prompt = LLM_PROMPTS["action_lockpick_check"].format(
            player_lockpicking_skill=self.player.knowledge.lockpicking_skill,
            lock_difficulty=lock_difficulty
        )
        response_str = self._call_ollama(prompt)

        if not response_str:
            self.add_message_to_chat_log("You try the lock, but nothing happens. (LLM Error)")
            return True # Attempt was made

        try:
            response_json = json.loads(response_str)
            success = response_json.get("success", False)
            narrative = response_json.get("narrative_feedback", "You try the lock...")
            pick_broken = response_json.get("lockpick_broken", False)

            self.add_message_to_chat_log(narrative)

            if pick_broken:
                self.player.economic.inventory["lockpick"] -= 1
                self.add_message_to_chat_log("Your lockpick broke!")
                if self.player.economic.inventory["lockpick"] <= 0:
                    del self.player.economic.inventory["lockpick"]
                    self.add_message_to_chat_log("That was your last lockpick.")

            if success:
                target_tile.properties["is_locked"] = False

                # --- Jail Escape Logic ---
                if self.player.state.is_jailed and (target_x, target_y) == self.player.state.jail_cell_coords:
                    self.add_message_to_chat_log("With a final click, the cell door swings open. You're free!")
                    self.player.state.is_jailed = False
                    self.player.state.jail_cell_coords = None
                    # The door is now unlocked and will become passable after the toggle action.
                    return True # Escape successful


                # For now, just message. Actual content access is next step.
                # self.add_message_to_chat_log(f"The {target_tile.name} clicks open!")
                # Try to find which building this chest is in to list its inventory as a placeholder
                # This is a simplified way to get building inventory for a chest.
                # A chest might have its own inventory in the future.
                containing_building = self._get_building_by_tile_coords(target_x, target_y)
                if containing_building and containing_building.building_inventory:
                    item_list_str = ", ".join([f"{qty}x {ITEM_DEFINITIONS.get(key,{}).get('name',key)}" for key, qty in containing_building.building_inventory.items() if key != "money"])
                    if not item_list_str : item_list_str = "nothing of note"
                    self.add_message_to_chat_log(f"Inside the {target_tile.name} you find: {item_list_str}.")
                elif containing_building:
                    self.add_message_to_chat_log(f"The {target_tile.name} is empty.")

            # --- Witness Handling ---
            witnesses = self._get_witnesses_to_action(target_x, target_y, "lockpicking")
            if witnesses:
                self.player.adjust_reputation(REP_CRIMINAL, 5) # 5 criminal points for lockpicking
                for witness in witnesses:
                    self._handle_witness_reaction(witness, "lockpicking", self.player)

            return True # Lockpicking attempt was made
        except json.JSONDecodeError:
            self.add_message_to_chat_log("Your attempt to pick the lock yields an odd result. (LLM Format Error)")
            return True

    def _get_building_by_tile_coords(self, world_x: int, world_y: int) -> Building | None:
        """Helper to find which building a specific world tile is part of, if any."""
        # This could be slow if called frequently.
        # For now, it iterates all known buildings.
        for building_id, building_obj in self.buildings_by_id.items():
            # Check if (world_x, world_y) is within this building's footprint
            # Building stores its origin global_origin_x/y and dimensions width/height
            if (building_obj.global_origin_x <= world_x < building_obj.global_origin_x + building_obj.width and
                building_obj.global_origin_y <= world_y < building_obj.global_origin_y + building_obj.height):
                return building_obj
        return None

    def npc_toggle_door(self, requesting_npc: NPC, door_x: int, door_y: int) -> bool:
        """Handles an NPC's attempt to open or close a door. NPCs currently only open doors."""
        target_tile = self.get_tile_at(door_x, door_y)

        if target_tile and target_tile.properties.get("is_door"):
            is_open = target_tile.properties.get("is_open", False)

            if is_open: # NPCs currently don't try to close doors they pass through
                return True # Door is already open, action considered successful for pathing

            # Door is closed, NPC tries to open it
            new_state_key = target_tile.properties.get("opens_to")
            action_message = f"{requesting_npc.name} opens the {target_tile.name}."

            if new_state_key and new_state_key in DECORATION_ITEM_DEFINITIONS:
                new_door_def = DECORATION_ITEM_DEFINITIONS[new_state_key]

                chunk_x, chunk_y = door_x // CHUNK_SIZE, door_y // CHUNK_SIZE
                local_x, local_y = door_x % CHUNK_SIZE, door_y % CHUNK_SIZE

                self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
                    char=new_door_def["char"],
                    color=new_door_def["color"],
                    passable=new_door_def["passable"],
                    name=new_door_def["name"],
                    properties=new_door_def["properties"]
                )
                # self.add_message_to_chat_log(action_message) # Can be spammy
                return True
            else:
                # self.add_message_to_chat_log(f"The {target_tile.name} seems stuck for {requesting_npc.name}.")
                return False
        return False # Not a door

    def initialize_trade_session(self):
        """Populates snapshots of player and merchant inventories for the trade UI."""
        if not self.trade_ui_active or not self.trade_ui_npc_target:
            return

        self.trade_ui_player_inventory_snapshot = []
        self.trade_ui_merchant_inventory_snapshot = []
        self.trade_ui_player_item_index = 0
        self.trade_ui_merchant_item_index = 0
        self.trade_ui_player_selling = True # Default to player selling view

        merchant_village = self._get_village_for_npc(self.trade_ui_npc_target)

        # Player inventory snapshot: (item_key, quantity, price_to_sell_at)
        player_inventory_aggregated = {}
        for item in self.player.economic.inventory:
            key = item["key"]
            qty = item.get("quantity", 1)
            player_inventory_aggregated[key] = player_inventory_aggregated.get(key, 0) + qty

        for item_key, quantity in player_inventory_aggregated.items():
            item_def = ITEM_DEFINITIONS.get(item_key)
            if item_def:
                price = self.get_dynamic_price(item_key, merchant_village)
                self.trade_ui_player_inventory_snapshot.append((item_key, quantity, price))

        # Merchant inventory snapshot: (item_key, quantity, price_to_buy_at)
        # Merchant inventory is likely in their work building
        merchant_inventory_source = {}
        merchant_building = self.buildings_by_id.get(self.trade_ui_npc_target.work_building_id)
        if merchant_building and merchant_building.building_type in ["general_store", "mill"]:
            merchant_inventory_source = merchant_building.building_inventory
        else: # Fallback to NPC's personal inventory if no store or not a store
            merchant_inventory_source = self.trade_ui_npc_target.economic.npc_inventory

        for item_key, quantity in merchant_inventory_source.items():
            if item_key == "money": continue # Don't list merchant's money as a sellable item
            item_def = ITEM_DEFINITIONS.get(item_key)
            if item_def:
                price = self.get_dynamic_price(item_key, merchant_village)
                self.trade_ui_merchant_inventory_snapshot.append((item_key, quantity, price))

        # Sort by name for consistent display
        self.trade_ui_player_inventory_snapshot.sort(key=lambda x: ITEM_DEFINITIONS.get(x[0], {}).get("name", x[0]))
        self.trade_ui_merchant_inventory_snapshot.sort(key=lambda x: ITEM_DEFINITIONS.get(x[0], {}).get("name", x[0]))

    def handle_trade_action(self):
        """Processes a buy or sell action from the trade UI."""
        if not self.trade_ui_active or not self.trade_ui_npc_target:
            return

        merchant_npc = self.trade_ui_npc_target
        merchant_building = self.buildings_by_id.get(merchant_npc.work_building_id)
        merchant_village = self._get_village_for_npc(merchant_npc)

        # Determine merchant's actual inventory (store or personal)
        merchant_true_inventory = {}
        if merchant_building and merchant_building.building_type in ["general_store", "mill"]:
            merchant_true_inventory = merchant_building.building_inventory
        else:
            merchant_true_inventory = merchant_npc.economic.npc_inventory

        merchant_money = merchant_true_inventory.get("money", 0)

        if self.trade_ui_player_selling: # Player is selling
            if not self.trade_ui_player_inventory_snapshot: return
            item_key, _, price = self.trade_ui_player_inventory_snapshot[self.trade_ui_player_item_index]

            if self.player.has_item(item_key):
                if merchant_money >= price:
                    if self.player.remove_item(item_key, 1):
                        self.player.economic.money += price
                        merchant_true_inventory[item_key] = merchant_true_inventory.get(item_key, 0) + 1
                        merchant_true_inventory["money"] = merchant_money - price
                        self.add_message_to_chat_log(f"You sold 1 {ITEM_DEFINITIONS[item_key]['name']} for {price} money.")
                        if merchant_village:
                            merchant_village.supply[item_key] = merchant_village.supply.get(item_key, 0) + 1
                    else:
                        self.add_message_to_chat_log("Error: Could not remove item from inventory.")
                else:
                    self.add_message_to_chat_log(f"{merchant_npc.name} doesn't have enough money to buy that.")
            else:
                self.add_message_to_chat_log("Error: You don't have that item to sell (inventory mismatch).")

        else: # Player is buying (viewing merchant's items)
            if not self.trade_ui_merchant_inventory_snapshot: return
            item_key, _, price = self.trade_ui_merchant_inventory_snapshot[self.trade_ui_merchant_item_index]

            if merchant_true_inventory.get(item_key, 0) > 0:
                if self.player.economic.money >= price:
                    merchant_true_inventory[item_key] -= 1
                    if merchant_true_inventory[item_key] <= 0:
                        del merchant_true_inventory[item_key]
                    merchant_true_inventory["money"] = merchant_money + price

                    self.player.add_item(item_key, 1)
                    self.player.economic.money -= price
                    self.add_message_to_chat_log(f"You bought 1 {ITEM_DEFINITIONS[item_key]['name']} for {price} money.")
                    if merchant_village:
                        merchant_village.supply[item_key] = merchant_village.supply.get(item_key, 0) - 1
                else:
                    self.add_message_to_chat_log("You don't have enough money for that.")
            else:
                self.add_message_to_chat_log(f"Error: {merchant_npc.name} doesn't have that item in stock (inventory mismatch).")


    def player_attempt_toggle_door(self, target_x: int, target_y: int) -> bool:
        """Handles the player's attempt to open or close a door."""
        target_tile = self.get_tile_at(target_x, target_y)

        if target_tile and target_tile.properties.get("is_door"):
            is_open = target_tile.properties.get("is_open", False)
            new_state_key = None
            action_message = ""

            if is_open: # Door is open, try to close it
                new_state_key = target_tile.properties.get("closes_to")
                action_message = f"You close the {target_tile.name}."
            else: # Door is closed, try to open it
                new_state_key = target_tile.properties.get("opens_to")
                action_message = f"You open the {target_tile.name}."

            if new_state_key and new_state_key in DECORATION_ITEM_DEFINITIONS:
                new_door_def = DECORATION_ITEM_DEFINITIONS[new_state_key]

                # Get chunk and local coords to update the tile in the chunk's grid
                chunk_x, chunk_y = target_x // CHUNK_SIZE, target_y // CHUNK_SIZE
                local_x, local_y = target_x % CHUNK_SIZE, target_y % CHUNK_SIZE

                self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
                    char=new_door_def["char"],
                    color=new_door_def["color"],
                    passable=new_door_def["passable"],
                    name=new_door_def["name"],
                    properties=new_door_def["properties"]
                )
                self.add_message_to_chat_log(action_message)
                return True # Action taken
            else:
                self.add_message_to_chat_log(f"The {target_tile.name} seems stuck or improperly defined.")
                return False # Action failed
        return False # Not a door or no tile

    def start_npc_dialogue(self, npc_target: NPC):
        """Initiates dialogue with an NPC, getting their first line."""
        if not npc_target:
            return

        # Clear previous chat history for the new conversation
        self.chat_ui_history.clear()
        self.chat_ui_scroll_offset = 0
        self.chat_ui_input_line = ""

        player_rep = self.player.social.reputation

        # --- Gather Environmental and Memory Context ---
        time_of_day = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)
        current_weather = self.weather
        location_description = self._get_location_description(npc_target.x, npc_target.y)
        long_term_memory_summary = "\n- ".join(npc_target.knowledge.long_term_memory[-5:]) # Last 5 memories
        if not long_term_memory_summary:
            long_term_memory_summary = "No specific memories of the player."
        # ---

        relationship_score = npc_target.social.relationships.get(self.player.id, 50)

        prompt = LLM_PROMPTS["npc_conversation_greeting"].format(
            npc_name=npc_target.name,
            npc_personality=npc_target.social.personality,
            npc_attitude=npc_target.attitude_to_player,
            relationship_score=relationship_score,
            player_fame=self.player.social.fame,
            player_infamy=self.player.social.infamy,
            player_title=self.player.social.title,
            time_of_day=time_of_day,
            current_weather=current_weather,
            location_description=location_description,
            long_term_memory=long_term_memory_summary,
            npc_help_needed=npc_target.knowledge.help_needed
        )
        greeting = self._call_ollama(prompt)
        if not greeting:
            greeting = f"Hello. (LLM failed to provide greeting)"

        self.chat_ui_history.append((npc_target.name, greeting.strip()))

        # If the NPC has a dynamic quest to offer, add it to the dialogue
        if hasattr(npc_target, 'active_quest') and npc_target.active_quest:
            quest = npc_target.active_quest
            offer_text = f"I'm in a bit of a bind. I desperately need {quest.required_count} {quest.item_key.replace('_', ' ')}. Can you help me? (You can 'accept quest' or 'decline quest')"
            self.chat_ui_history.append((npc_target.name, offer_text))


        if len(self.chat_ui_history) > self.chat_ui_max_history:
            self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]

    def continue_npc_dialogue(self, npc_target: NPC, player_input_text: str):
        """Continues dialogue with an NPC based on player input and history."""
        if not npc_target:
            return

        # --- Handle special keywords before general conversation ---
        # --- Handle special keywords before general conversation ---
        # Quest completion
        if 'complete quest' in player_input_text.lower():
            for quest_id, quest_data in self.player.knowledge.active_quests.items():
                if quest_data["quest_giver_id"] == npc_target.id:
                    self.complete_quest(quest_id, npc_target)
                    return # End dialogue turn

        # Quest acceptance/rejection
        if hasattr(npc_target, 'active_quest') and npc_target.active_quest:
            quest = npc_target.active_quest
            if 'accept' in player_input_text.lower():
                self.player.knowledge.active_quests[quest.id] = {
                    "title": quest.title,
                    "description": quest.description,
                    "type": quest.type,
                    "quest_giver_id": quest.quest_giver_id,
                    "item_to_fetch_key": quest.item_key,
                    "item_fetch_count": quest.required_count,
                    "progress": 0
                }
                self.chat_ui_history.append((npc_target.name, "Oh, thank you! Please hurry!"))
                npc_target.active_quest = None # Quest is now with the player
                return
            elif 'decline' in player_input_text.lower():
                self.chat_ui_history.append((npc_target.name, "Oh, I see. I'll have to find another way then."))
                npc_target.active_quest = None # NPC gives up offering this quest for now
                return

        share_keywords = ["i know where", "let me tell you about", "have you seen"]
        if any(keyword in player_input_text.lower() for keyword in share_keywords):
            shared = False
            for loc_id, coords in self.player.knowledge.known_locations.items():
                building = self.buildings_by_id.get(loc_id)
                if building and building.building_type.replace('_', ' ') in player_input_text.lower():
                    loc_name = building.building_type.replace('_', ' ')
                    if loc_name not in npc_target.knowledge.known_locations:
                        npc_target.knowledge.known_locations[loc_name] = coords
                        npc_target.relationships[self.player.id] = npc_target.relationships.get(self.player.id, 50) + 10
                        self.chat_ui_history.append((npc_target.name, f"Oh, the {loc_name}? I didn't know where that was. Thank you!"))
                        shared = True
                        break
            if not shared:
                self.chat_ui_history.append((npc_target.name, "I'm not sure what you mean."))
            return

        gossip_keywords = ["gossip", "rumors", "news", "hear anything"]
        if any(keyword in player_input_text.lower() for keyword in gossip_keywords):
            if not npc_target.known_events:
                self.chat_ui_history.append((npc_target.name, "I haven't heard anything interesting lately."))
            else:
                # Select a random event to gossip about
                event_to_share = random.choice(list(npc_target.known_events.values()))

                # Get names and relationships for the prompt
                subject = next((n for n in self.village_npcs + self.npcs if n.id == event_to_share.subject_id), self.player if event_to_share.subject_id == self.player.id else None)
                target = next((n for n in self.village_npcs + self.npcs if n.id == event_to_share.target_id), self.player if event_to_share.target_id == self.player.id else None) if event_to_share.target_id else None

                subject_name = getattr(subject, 'name', 'Someone') if subject else 'Someone'
                target_name = getattr(target, 'name', 'someone') if target else 'someone'

                subject_title = getattr(subject, 'title', '') if subject else ''
                target_title = getattr(target, 'title', '') if target else ''

                gossip_prompt = LLM_PROMPTS["npc_share_gossip"].format(
                    npc_name=npc_target.name,
                    npc_personality=npc_target.social.personality,
                    npc_relationship_with_player=npc_target.social.relationships.get(self.player.id, 50),
                    npc_relationship_with_subject=npc_target.social.relationships.get(event_to_share.subject_id, 50),
                    npc_relationship_with_target=npc_target.social.relationships.get(event_to_share.target_id, 50) if event_to_share.target_id else 50,
                    event_description=event_to_share.description,
                    subject_name=subject_name,
                    target_name=target_name,
                    subject_title=subject_title,
                    target_title=target_title
                )
                gossip_dialogue = self._call_ollama(gossip_prompt)
                if not gossip_dialogue:
                    gossip_dialogue = "I... uh... forget what I was going to say."

                self.chat_ui_history.append((npc_target.name, gossip_dialogue.strip()))
            # End the turn after sharing gossip
            return

        # Format conversation history for the prompt
        formatted_history = []
        # Take last N messages for context window (e.g., last 10 lines, 5 exchanges)
        history_context_limit = 10
        recent_history = self.chat_ui_history[-(history_context_limit-1):] if len(self.chat_ui_history) > 1 else self.chat_ui_history

        for speaker, text in recent_history:
            if speaker == "Player": # Assuming "Player" is the key for player lines
                formatted_history.append(f"Player: {text}")
            else: # NPC lines
                formatted_history.append(f"{speaker}: {text}")
        history_str = "\n".join(formatted_history)

        # --- Gather Environmental and Memory Context ---
        time_of_day = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)
        current_weather = self.weather
        location_description = self._get_location_description(npc_target.x, npc_target.y)
        long_term_memory_summary = "\n- ".join(npc_target.knowledge.long_term_memory[-5:]) # Last 5 memories
        if not long_term_memory_summary:
            long_term_memory_summary = "No specific memories of the player."
        # ---

        relationship_score = npc_target.relationships.get(self.player.id, 50)

        prompt = LLM_PROMPTS["npc_conversation_continue"].format(
            npc_name=npc_target.name,
            npc_personality=npc_target.social.personality,
            relationship_score=relationship_score,
            player_fame=self.player.social.fame,
            player_infamy=self.player.social.infamy,
            player_title=self.player.social.title,
            conversation_history=history_str,
            player_input=player_input_text,
            npc_current_task=npc_target.schedule.current_task,
            time_of_day=time_of_day,
            current_weather=current_weather,
            location_description=location_description,
            long_term_memory=long_term_memory_summary
        )

        response_str = self._call_ollama(prompt)
        if not response_str:
            self.chat_ui_history.append((npc_target.name, "... (LLM failed to respond)"))
            return

        try:
            response_json = json.loads(response_str)
            npc_response = response_json.get("response", "...")
            goal = response_json.get("goal", "continue_conversation")

            self.chat_ui_history.append((npc_target.name, npc_response.strip()))
            self._handle_npc_goal(npc_target, goal, player_input_text)

        except json.JSONDecodeError:
            # If the LLM fails to return valid JSON, just treat the whole response as dialogue
            self.chat_ui_history.append((npc_target.name, response_str.strip()))

        # After NPC response, check if this NPC should offer a job
        if npc_target.economic.profession == "Lumber Mill Foreman" and f"lumber_delivery_{npc_target.id}" not in self.player.economic.active_contracts:
            # Check if player's response was affirmative to a previous implicit offer or just general talk
            # This is tricky without more state. For now, let's assume if they talk to Foreman, job is offered.
            # A better way: Foreman's initial greeting (start_npc_dialogue) could offer.
            # Or, if player says "work" or "job".
            # For simplicity now: if player just said something, and no active contract, Foreman offers.

            # Define contract details
            contract_id = f"lumber_delivery_{npc_target.id}"
            item_needed = "log"
            quantity_needed = 10
            reward_amount = 50 # Example reward
            item_name_plural = "logs" # For the prompt

            offer_prompt = LLM_PROMPTS["npc_job_offer_lumber"].format(
                npc_name=npc_target.name,
                npc_profession=npc_target.economic.profession,
                npc_personality=npc_target.social.personality,
                npc_attitude=npc_target.attitude_to_player,
                player_criminal_points=self.player.social.reputation.get(REP_CRIMINAL,0),
                player_hero_points=self.player.social.reputation.get(REP_HERO,0),
                quantity_needed=quantity_needed,
                item_name_plural=item_name_plural,
                reward_amount=reward_amount
            )
            job_offer_dialogue = self._call_ollama(offer_prompt)
            if not job_offer_dialogue:
                job_offer_dialogue = f"I might have some work for you... if you're interested. Need {quantity_needed} {item_name_plural} for {reward_amount} coins."

            self.chat_ui_history.append((npc_target.name, job_offer_dialogue.strip()))
            # Store pending offer to be accepted on player's next input if affirmative
            self.player.economic.pending_contract_offer = {
                "contract_id": contract_id, "npc_id": npc_target.id,
                "item_key": item_needed, "quantity_needed": quantity_needed,
            "reward": reward_amount, "npc_offerer_id": npc_target.id
            }
            self.chat_ui_history.append(("System", "The Foreman has offered you a job. Type 'yes' or 'accept' to take it."))

        # --- Quest Offering Logic (Example: Sheriff offers "kill_wolves_01") ---
        # This is a simplified trigger; more robust would be keyword matching or LLM intent.
        if npc_target.economic.profession == "Sheriff" and "kill_wolves_01" not in self.player.knowledge.active_quests and \
           "kill_wolves_01" not in self.player.knowledge.completed_quests:

            quest_def = QUEST_DEFINITIONS.get("kill_wolves_01")
            if quest_def:
                offer_dialogue = quest_def.get("dialogue_offer", "I might have a task for you...")
                self.chat_ui_history.append((npc_target.name, offer_dialogue))
                self.add_message_to_chat_log(f"Quest Offered: {quest_def['title']}")

        if len(self.chat_ui_history) > self.chat_ui_max_history:
            self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]

    def _handle_npc_goal(self, npc: NPC, goal: str, player_input: str):
        """Handles the goal set for an NPC by the LLM during conversation."""
        if goal == "follow_player":
            npc.schedule.current_task = "following_player"
            npc.task_target_entity_id = self.player.id
            npc.schedule.current_path = []  # Clear path to allow recalculation
            self.add_message_to_chat_log(f"{npc.name} is now following you.")
        elif goal == "go_to_location":
            # Placeholder for future implementation where the LLM might specify coordinates
            self.add_message_to_chat_log(f"{npc.name} wants to go to a location mentioned.")
            # Example: npc.schedule.current_task = "going_to_location"
            # npc.task_target_coords = (x, y) # (extracted from player_input or LLM response)
        elif goal == "start_trade":
            if npc.economic.profession == "Merchant":
                self.game_state = "TRADE_MENU"
                self.trade_ui_npc_target = npc
                self.initialize_trade_session()
            else:
                self.add_message_to_chat_log(f"{npc.name} seems to want to trade, but isn't a merchant.")
        elif goal == "end_conversation":
            self._summarize_and_store_conversation(npc, self.chat_ui_history)
            self.game_state = "PLAYING"
            self.chat_ui_active = False
            # The main loop needs to stop text input
            self.needs_text_input = False

    def _summarize_and_store_conversation(self, npc: NPC, conversation_history: list):
        """Summarizes a conversation and stores it in the NPC's long-term memory."""
        if not conversation_history:
            return

        formatted_history = []
        for speaker, text in conversation_history:
            if speaker == "Player":
                formatted_history.append(f"Player: {text}")
            else:
                formatted_history.append(f"{speaker}: {text}")
        history_str = "\n".join(formatted_history)

        prompt = LLM_PROMPTS["summarize_conversation_for_memory"].format(
            npc_name=npc.name,
            npc_personality=npc.social.personality,
            conversation_history=history_str
        )
        summary = self._call_ollama(prompt)

        if summary and len(summary) > 10: # Avoid storing short errors or empty strings
            npc.knowledge.long_term_memory.append(summary)
            # Keep memory from growing too large
            if len(npc.knowledge.long_term_memory) > 20:
                npc.knowledge.long_term_memory.pop(0)


    def _call_ollama(self, prompt: str) -> str:
        """Makes a request to the Ollama API and returns the response."""
        if not ENABLE_OLLAMA_CONNECTION:
            return "{}"
        try:
            response = requests.post(
                OLLAMA_ENDPOINT + "/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=15 # 15 second timeout, increased from 5
            )
            response.raise_for_status()
            full_response = response.json()["response"]
            # This logic to extract JSON is good, but let's assume for now the model might not always return valid JSON.
            # We will just return the raw response if it's not JSON, and let the calling function handle it.
            return full_response.strip()
        except requests.exceptions.RequestException as e:
            # Don't print to the console during gameplay, as it can be disruptive.
            # A proper logging system would be better for production. For now, we'll just return "".
            # print(f"Error communicating with Ollama: {e}")
            return ""

    def log_event(self, event_type: str, description: str, subject_id: int, target_id: int | None = None, location: tuple[int, int] | None = None):
        """Creates an Event object and adds it to the global event log."""
        new_event = Event(
            event_type=event_type,
            description=description,
            subject_id=subject_id,
            target_id=target_id,
            location=location,
            game_time=self.game_time
        )
        self.global_events.append(new_event)
        # Keep the event log from growing indefinitely
        if len(self.global_events) > 200: # Max 200 recent events
            self.global_events.pop(0)

    def _find_nearest_heat_source(self, npc: NPC) -> tuple[int, int] | None:
        """Finds the nearest lit heat source for an NPC."""
        closest_source_coords = None
        min_dist_sq = float('inf')

        # 1. Check a radius around the NPC
        for y in range(npc.y - 10, npc.y + 11):
            for x in range(npc.x - 10, npc.x + 11):
                if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
                    tile = self.get_tile_at(x, y)
                    if tile and hasattr(tile, 'properties') and tile.properties.get("heat_source"):
                        dist_sq = (npc.x - x)**2 + (npc.y - y)**2
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq
                            closest_source_coords = (x, y)

        # 2. Check NPC's home for heat sources
        home_building = self.buildings_by_id.get(npc.schedule.home_building_id)
        if home_building:
            for y in range(home_building.global_origin_y, home_building.global_origin_y + home_building.height):
                for x in range(home_building.global_origin_x, home_building.global_origin_x + home_building.width):
                    tile = self.get_tile_at(x, y)
                    if tile and hasattr(tile, 'properties') and tile.properties.get("heat_source"):
                        dist_sq = (npc.x - x)**2 + (npc.y - y)**2
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq
                            closest_source_coords = (x, y)

        # 3. Check the local tavern
        tavern = self._find_nearest_tavern(npc)
        if tavern:
            for y in range(tavern.global_origin_y, tavern.global_origin_y + tavern.height):
                for x in range(tavern.global_origin_x, tavern.global_origin_x + tavern.width):
                    tile = self.get_tile_at(x, y)
                    if tile and hasattr(tile, 'properties') and tile.properties.get("heat_source"):
                        dist_sq = (npc.x - x)**2 + (npc.y - y)**2
                        if dist_sq < min_dist_sq:
                            min_dist_sq = dist_sq
                            closest_source_coords = (x, y)

        return closest_source_coords

    def _water_crops(self):
        """Increments the growth of crops when it rains."""
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if not chunk.is_generated:
                    continue

                for y_local in range(CHUNK_SIZE):
                    for x_local in range(CHUNK_SIZE):
                        tile = chunk.tiles[y_local][x_local]
                        if tile and tile.name == "Growing Wheat":
                            tile.properties["growth_progress"] += 5 # Example growth increment

    def _update_weather(self):
        """Dynamically updates weather and handles its effects."""
        self.weather_change_timer -= 1
        if self.weather_change_timer <= 0:
            current_season = self.seasons[self.current_season_index]
            possible_weathers = []
            for weather, data in WEATHER_DEFINITIONS.items():
                if current_season in data["seasons"]:
                    possible_weathers.append(weather)

            if possible_weathers:
                self.weather = random.choice(possible_weathers)
                self.add_message_to_chat_log(f"The weather has changed to {self.weather}.")

            self.weather_change_timer = random.randint(DAY_LENGTH_TICKS // 2, DAY_LENGTH_TICKS * 2)

        if self.weather == "rain":
            self._water_crops()
            for y_chunk in range(self.chunk_height):
                for x_chunk in range(self.chunk_width):
                    chunk = self.chunks[y_chunk][x_chunk]
                    if not chunk.is_generated:
                        continue

                    for y_local in range(CHUNK_SIZE):
                        for x_local in range(CHUNK_SIZE):
                            tile = chunk.tiles[y_local][x_local]
                            if tile and hasattr(tile, 'properties') and "extinguishes_to" in tile.properties:
                                world_x = x_chunk * CHUNK_SIZE + x_local
                                world_y = y_chunk * CHUNK_SIZE + y_local
                                if not self._check_for_shelter(world_x, world_y):
                                    extinguishes_to_key = tile.properties["extinguishes_to"]
                                    new_tile_def = TILE_DEFINITIONS.get(extinguishes_to_key) or DECORATION_ITEM_DEFINITIONS.get(extinguishes_to_key)
                                    if new_tile_def:
                                        self._change_map_tile((world_x, world_y), new_tile_def)

    def _update_world_environment(self):
        """Handles time-based environmental changes like tree regrowth."""
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if not chunk.is_generated:
                    continue

                for y_local in range(CHUNK_SIZE):
                    for x_local in range(CHUNK_SIZE):
                        tile = chunk.tiles[y_local][x_local]

                        # Tree regrowth from stump
                        if hasattr(tile, 'regrowth_timer') and tile.regrowth_timer > 0:
                            tile.regrowth_timer -= 1
                            if tile.regrowth_timer <= 0:
                                if hasattr(tile, 'original_tree_type') and tile.original_tree_type:
                                    tree_type = tile.original_tree_type
                                    world_x = x_chunk * CHUNK_SIZE + x_local
                                    world_y = y_chunk * CHUNK_SIZE + y_local

                                    new_tree = None
                                    if tree_type == "oak":
                                        new_tree = OakTree(world_x, world_y)
                                    elif tree_type == "apple":
                                        new_tree = AppleTree(world_x, world_y)
                                    elif tree_type == "pear":
                                        new_tree = PearTree(world_x, world_y)

                                    if new_tree:
                                        chunk.tiles[y_local][x_local] = new_tree
                                        # Also update the global transparency map for FOV
                                        self.transparency_map[world_x, world_y] = True # Trees are not transparent


                        # Sapling growth into tree
                        elif tile.name == "Sapling" and "growth_timer" in tile.properties:
                            tile.properties["growth_timer"] -= 1
                            if tile.properties["growth_timer"] <= 0:
                                # Determine what kind of tree it becomes
                                tree_type = tile.properties.get("evolves_to", "oak") # Default to oak
                                world_x = x_chunk * CHUNK_SIZE + x_local
                                world_y = y_chunk * CHUNK_SIZE + y_local

                                new_tree = None
                                if tree_type == "oak":
                                    new_tree = OakTree(world_x, world_y)
                                elif tree_type == "apple":
                                    new_tree = AppleTree(world_x, world_y)
                                elif tree_type == "pear":
                                    new_tree = PearTree(world_x, world_y)

                                if new_tree:
                                    chunk.tiles[y_local][x_local] = new_tree
                                    self.transparency_map[world_x, world_y] = True # Update transparency map

                        # Crop growth
                        elif tile.name == "Growing Wheat":
                            # Increment growth progress over time
                            tile.properties["growth_progress"] += 1
                            if tile.properties["growth_progress"] >= tile.properties["growth_needed"]:
                                evolves_to_key = tile.properties.get("evolves_to")
                                if evolves_to_key:
                                    new_tile_def = TILE_DEFINITIONS.get(evolves_to_key)
                                    if new_tile_def:
                                        world_x = x_chunk * CHUNK_SIZE + x_local
                                        world_y = y_chunk * CHUNK_SIZE + y_local
                                        self._change_map_tile((world_x, world_y), new_tile_def)


    def _populate_npcs(self):
        # This function is now empty as village NPCs are populated in _populate_village_npcs
        # and other NPCs (like animals) are spawned during biome generation.
        pass

    def _initialize_economy(self, village: Village):
        """Calculates initial supply and demand for a village."""
        village.supply = {}
        village.demand = {}

        # Calculate initial supply from all building inventories in the village
        for building in village.buildings:
            for item_key, quantity in building.building_inventory.items():
                village.supply[item_key] = village.supply.get(item_key, 0) + quantity

        # Calculate baseline demand from NPC professions and basic needs
        for npc in self.village_npcs:
            if self._get_village_for_npc(npc) != village:
                continue

            # Basic needs demand (e.g., food)
            village.demand["bread"] = village.demand.get("bread", 0) + 2 # Example: each NPC creates demand for 2 bread

            # Professional needs demand
            profession_data = get_profession_data(npc.economic.profession)
            if profession_data and profession_data.get("sub_tasks"):
                for sub_task in profession_data["sub_tasks"]:
                    consumes = sub_task.get("consumes_item_from_workplace", {})
                    for item_key, qty in consumes.items():
                        village.demand[item_key] = village.demand.get(item_key, 0) + 5 # Baseline demand of 5 for each required resource

    def _populate_village_npcs(self, chunk: Chunk, village: Village, chunk_coord_x: int, chunk_coord_y: int): # Added chunk_coord_x, chunk_coord_y
        """Populates a village with NPCs, assigning them homes and potentially jobs."""
        # chunk_global_start_x and chunk_global_start_y are now implicitly handled by Building.global_center_x/y
        # No longer need to calculate chunk_global_start_x/y here from chunk_coord_x/y for NPC placement if using building centers.

        num_npcs = random.randint(max(1, len(village.buildings) // 2), len(village.buildings))
        if not village.buildings:
            num_npcs = 0

        residential_buildings = [b for b in village.buildings if b.category == "residential"]
        workplace_buildings = [b for b in village.buildings if "workplace" in b.category] # e.g., "civic_workplace", "commercial_workplace"

        available_homes = list(residential_buildings)
        available_workplaces = list(workplace_buildings)
        random.shuffle(available_homes)
        random.shuffle(available_workplaces)

        for i in range(num_npcs):
            # npc_data = {
            #     "name": f"Villager {i+1}",
            #     "dialogue": ["Greetings."],
            #     "personality": "commoner",
            #     "family_ties": "none",
            #     "attitude_to_player": "neutral",
            #     "wealth_level": random.choice(["poor", "average", "wealthy"]),
            #     "combat_behavior": "defensive",
            #     "base_attack_name": "fists"
            # }
            llm_prompt = LLM_PROMPTS["npc_personality"].format(
                player_criminal_points=self.player.social.reputation.get(REP_CRIMINAL, 0),
                player_hero_points=self.player.social.reputation.get(REP_HERO, 0),
                name_hint="",
                personality_hint="",
                family_ties_hint="",
                attitude_to_player_hint=""
            )
            llm_response = self._call_ollama(llm_prompt)
            try:
                npc_data = json.loads(llm_response)
                # Assign home
                if not available_homes:
                    # self.add_message_to_chat_log("Warning: No available homes for new NPC.")
                    # Create NPC without a home, or handle differently
                    home_building = None
                    npc_x = chunk_coord_x * CHUNK_SIZE + CHUNK_SIZE // 2
                    npc_y = chunk_coord_y * CHUNK_SIZE + CHUNK_SIZE // 2
                else:
                    home_building = available_homes.pop(0)
                    # Place NPC at the global center of their home building
                    npc_x = home_building.global_center_x
                    npc_y = home_building.global_center_y

                # Ensure NPC is within world bounds (still good practice)
                npc_x = max(0, min(WORLD_WIDTH - 1, npc_x))
                npc_y = max(0, min(WORLD_HEIGHT - 1, npc_y))

                # Assign workplace (optional)
                work_building = None
                if available_workplaces and random.random() < 0.7: # 70% chance to get a job if available
                    work_building = available_workplaces.pop(0) # Assign and remove

                npc = NPC(
                    x=npc_x,
                    y=npc_y,
                    name=npc_data.get("name", f"Villager {i+1}"),
                    dialogue=npc_data.get("dialogue", ["Greetings."]),
                    personality=npc_data.get("personality", "commoner"),
                    family_ties=npc_data.get("family_ties", "none"),
                    attitude_to_player=npc_data.get("attitude_to_player", "neutral"),
                    player_id=self.player.id
                )

                # Assign wealth (randomly for now) - This is now part of LLM prompt for personality
                npc.economic.wealth_level = npc_data.get("wealth_level", random.choice(["poor", "average", "wealthy"]))

                # Combat AI attributes from LLM
                npc.combat.combat_behavior = npc_data.get("combat_behavior", "defensive")
                npc.combat.base_attack_name = npc_data.get("base_attack_name", "fists")

                # Basic logic for damage dice based on attack name or behavior
                # More sophisticated logic could be added here, e.g., guards get better defaults
                if "knife" in npc.combat.base_attack_name.lower() or \
                   "dagger" in npc.combat.base_attack_name.lower() or \
                   "tool" in npc.combat.base_attack_name.lower() or \
                   "hammer" in npc.combat.base_attack_name.lower() or \
                   "claws" in npc.combat.base_attack_name.lower() or \
                   "teeth" in npc.combat.base_attack_name.lower() or \
                   "spear" in npc.combat.base_attack_name.lower():
                    npc.combat.base_attack_damage_dice = "1d4"
                elif "sword" in npc.combat.base_attack_name.lower() or \
                     "axe" in npc.combat.base_attack_name.lower() or \
                     "mace" in npc.combat.base_attack_name.lower():
                    npc.combat.base_attack_damage_dice = "1d6"
                else: # fists, kick, staff, etc.
                    npc.combat.base_attack_damage_dice = "1d3"

                if npc.combat.combat_behavior == "aggressive" and npc.combat.base_attack_damage_dice == "1d3":
                    npc.combat.base_attack_damage_dice = "1d4" # Aggressive NPCs might hit a bit harder by default

                npc.combat.attack_range = 1 # Default melee

                # Assign profession based on work building
                if work_building:
                    npc.schedule.work_building_id = work_building.id
                    work_building.occupants.append(npc) # Store NPC object for now
                    # Simple profession mapping
                    if work_building.building_type == "sheriff_office":
                        npc.economic.profession = "Sheriff"
                    elif work_building.building_type == "capital_hall":
                        npc.economic.profession = "Town Official"
                    elif work_building.building_type == "general_store" or \
                         "shop" in work_building.building_type or \
                         "market" in work_building.building_type:
                        npc.economic.profession = "Merchant"
                    elif work_building.building_type == "tavern":
                        npc.economic.profession = "Tavern Keeper"
                    elif work_building.building_type == "lumber_mill":
                        is_foreman_assigned_to_mill = any(
                            other_npc.economic.profession == "Lumber Mill Foreman" and other_npc.schedule.work_building_id == work_building.id
                            for other_npc in self.village_npcs + self.npcs
                        )
                        if not is_foreman_assigned_to_mill:
                            npc.economic.profession = "Lumber Mill Foreman"
                        else:
                            npc.economic.profession = "Woodcutter"
                    elif work_building.building_type == "farm":
                         npc.economic.profession = "Farmer"
                    elif work_building.building_type == "mine":
                         npc.economic.profession = "Miner"
                    elif work_building.building_type == "carpenter_shop":
                        npc.economic.profession = "Carpenter"
                    elif work_building.building_type == "mill":
                        npc.economic.profession = "Miller"
                    elif work_building.building_type == "bakery":
                        npc.economic.profession = "Baker"
                    elif work_building.building_type == "fishing_hut":
                        npc.economic.profession = "Fisherman"
                    elif work_building.building_type == "library":
                        npc.economic.profession = "Scribe"
                    else:
                        npc.economic.profession = work_building.building_type.replace("_", " ").title()
                else:
                    npc.economic.profession = "Unemployed"

                # If NPC is a Merchant and assigned to a general store, pre-populate store inventory
                if npc.economic.profession == "Merchant" and work_building and work_building.building_type == "general_store":
                    # Add some starting cash for the store to buy items
                    work_building.building_inventory["money"] = random.randint(150, 500)
                    # Add some items for sale
                    work_building.building_inventory["axe_stone"] = random.randint(1, 3)
                    work_building.building_inventory["healing_salve"] = random.randint(3, 8)
                    work_building.building_inventory["wooden_plank"] = random.randint(10, 30)
                    if random.random() < 0.5: # Chance to have some logs
                        work_building.building_inventory["log"] = random.randint(5, 20)
                    # self.add_message_to_chat_log(f"Stocked General Store ({work_building.id[:6]}) for Merchant {npc.name}.")

                if home_building:
                    npc.home_building_id = home_building.id
                    home_building.residents.append(npc)
                    # Seed initial knowledge of home and workplace
                    npc.knowledge.known_locations[f"my home"] = (home_building.global_center_x, home_building.global_center_y)
                if work_building:
                    npc.knowledge.known_locations[f"my workplace"] = (work_building.global_center_x, work_building.global_center_y)

                # A subset of villagers know about key public locations to bootstrap knowledge spread
                if random.random() < 0.3: # 30% of villagers have this extra knowledge
                    tavern = next((b for b in village.buildings if b.building_type == "tavern"), None)
                    if tavern:
                        npc.knowledge.known_locations["the tavern"] = (tavern.global_center_x, tavern.global_center_y)

                    general_store = next((b for b in village.buildings if b.building_type == "general_store"), None)
                    if general_store:
                        npc.knowledge.known_locations["the general store"] = (general_store.global_center_x, general_store.global_center_y)

                    if "well" in village.interaction_points and village.interaction_points["well"]:
                        well_coords = village.interaction_points["well"][0]
                        npc.knowledge.known_locations["the village well"] = well_coords

                # Chance to give NPC a healing salve
                if random.random() < 0.33: # 33% chance
                    npc.economic.npc_inventory["healing_salve"] = npc.economic.npc_inventory.get("healing_salve", 0) + 1
                    # self.add_message_to_chat_log(f"Debug: {npc.name} received a healing salve.")

                # Assign starting equipment based on role/behavior
                if npc.economic.profession in ["Sheriff", "Guard"] or npc.combat.combat_behavior == "aggressive":
                    if "rusty_sword" in ITEM_DEFINITIONS:
                        npc.economic.npc_inventory["rusty_sword"] = npc.economic.npc_inventory.get("rusty_sword", 0) + 1
                        npc.equipment.weapon = "rusty_sword"
                        # self.add_message_to_chat_log(f"Debug: {npc.name} equipped a rusty_sword.")
                    if "leather_jerkin" in ITEM_DEFINITIONS:
                        npc.economic.npc_inventory["leather_jerkin"] = npc.economic.npc_inventory.get("leather_jerkin", 0) + 1
                        npc.equipment.body = "leather_jerkin"
                        # self.add_message_to_chat_log(f"Debug: {npc.name} equipped a leather_jerkin.")
                    # Optionally, add a helmet too
                    if random.random() < 0.5 and "iron_helmet" in ITEM_DEFINITIONS: # 50% chance for guards/aggressive to also have helmet
                        npc.economic.npc_inventory["iron_helmet"] = npc.economic.npc_inventory.get("iron_helmet", 0) + 1
                        npc.equipment.head = "iron_helmet"


                self.village_npcs.append(npc)
                self.add_message_to_chat_log(
                    f"Generated Villager: {npc.name} (Wealth: {npc.economic.wealth_level}, Prof: {npc.economic.profession}). "
                    f"Home: {home_building.building_type if home_building else 'N/A'}. "
                    f"Work: {work_building.building_type if work_building else 'N/A'}."
                )

            except json.JSONDecodeError as e:
                self.add_message_to_chat_log(f"Error parsing LLM response for Villager NPC: {e}")
                self.add_message_to_chat_log(f"LLM Response: {llm_response}")
            except IndexError: # Ran out of homes or workplaces
                self.add_message_to_chat_log(f"Could not place NPC {npc_data.get('name', 'Unknown')} due to lack of available buildings.")


    def _handle_npc_speech(self):
        current_time = time.time()
        player_rep = self.player.social.reputation  # Get player rep once

        # Ensure self.npcs and self.village_npcs are initialized
        if not hasattr(self, 'npcs'):
            self.npcs = []
        if not hasattr(self, 'village_npcs'):
            self.village_npcs = []

        for npc in self.npcs + self.village_npcs:
            if current_time - npc.last_speech_time > random.randint(10, 30):
                # Ambient speech might be general, or react to player if nearby and reputation is notable
                prompt = (
                    f"NPC {npc.name} (Personality: {npc.social.personality}, Attitude to Player: {npc.attitude_to_player}, Family: {npc.social.family_ties}) "
                    f"is going about their day. The player's reputation is: "
                    f"Criminal Points: {player_rep.get(REP_CRIMINAL, 0)}, Hero Points: {player_rep.get(REP_HERO, 0)}. "
                    f"Generate a short, in-character ambient thought or statement from {npc.name}. "
                    f"It could be about their current (unspecified) activity, the village, a general thought, "
                    f"or a comment related to the player if their reputation is particularly high or low and the player is assumed to be generally known or nearby. "
                    f"Keep it concise."
                )
                llm_dialogue = self._call_ollama(prompt)
                if llm_dialogue:
                    # Check if player can hear this NPC
                    distance_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y) # Manhattan distance

                    can_hear = False
                    if distance_to_player <= self.player.physical.hearing_radius and \
                       distance_to_player <= npc.speech_volume:
                        can_hear = True

                    if can_hear:
                        # For now, keep existing message format.
                        # Could later add "(you overhear)" or similar if NPC not visible.
                        self.add_message_to_chat_log(f"{npc.name}: {llm_dialogue.strip()}")
                    # Else, player doesn't hear it, so don't add to log.

                    npc.last_speech_time = current_time # Update speech time regardless of player hearing

    def decorate_building_interior(self, building: Building, chunk: Chunk):
        decoration_data = {'decorations': []}
        # if building.building_type == 'house':
        #     decoration_data['decorations'].append({'type': 'bed_simple', 'x': 1, 'y': 1})
        #     decoration_data['decorations'].append({'type': 'wooden_table', 'x': building.width - 2, 'y': 1})
        #     decoration_data['decorations'].append({'type': 'wooden_chair', 'x': building.width - 3, 'y': 1})
        llm_response = '' # Ensure llm_response is defined # Added chunk to access village lore
        # Ensure we have the village object if the building is in a village POI
        village = None
        if chunk and chunk.poi_type == "village" and chunk.village:
            village = chunk.village

        # self.add_message_to_chat_log(f"Decorating {building.building_type} ({building.id[:6]}) in village (Lore: {'Yes' if village and village.lore else 'No'}). Residents: {len(building.residents)}")

        # --- Gather Context for LLM ---
        village_lore_summary = "This building stands alone, its story yet unwritten."
        if village and village.lore:
            # Summarize lore if too long, or use as is if short.
            # For now, using first 150 chars as a simple summary.
            village_lore_summary = village.lore[:150].strip() + "..." if len(village.lore) > 150 else village.lore.strip()
            if not village_lore_summary: village_lore_summary = "A quiet, unassuming village."


        inhabitant_details_parts = []
        if building.residents:
            for i, resident_npc in enumerate(building.residents):
                detail = (
                    f"Inhabitant {i+1}: Name: {resident_npc.name}, "
                    f"Personality: {resident_npc.social.personality}, "
                    f"Wealth: {resident_npc.economic.wealth_level}, "
                    f"Profession: {resident_npc.economic.profession}."
                )
                inhabitant_details_parts.append(detail)

        if not inhabitant_details_parts:
            inhabitant_details = "This building is currently unoccupied or its inhabitants are unknown."
            # Potentially assign a default "generic poor family" if building type implies residence but no one is assigned
            if building.category == "residential":
                 inhabitant_details = "A simple family of modest means is presumed to live here."
        else:
            inhabitant_details = "\n".join(inhabitant_details_parts)

        decoration_items_list = ", ".join(DECORATION_ITEM_DEFINITIONS.keys())

        prompt = LLM_PROMPTS["building_interior"].format(
            building_type=building.building_type,
            width=building.width,
            height=building.height,
            village_lore_summary=village_lore_summary,
            inhabitant_details=inhabitant_details,
            decoration_items=decoration_items_list
        )

        # self.add_message_to_chat_log(f"Decorating prompt for {building.id[:6]}:\n{prompt}") # For debugging the full prompt

        llm_response = self._call_ollama(prompt)
        try:
            # If the response is a valid JSON, use it. Otherwise, fallback to placeholder.
            decoration_data = json.loads(llm_response)
        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"LLM failed to provide valid JSON for {building.building_type} interior. Using placeholder.")
            decoration_data = {"decorations": []}
            if building.building_type == "house":
                decoration_data["decorations"].append({"type": "bed_simple", "x": 1, "y": 1})
                decoration_data["decorations"].append({"type": "wooden_table", "x": building.width - 2, "y": 1})
                decoration_data["decorations"].append({"type": "wooden_chair", "x": building.width - 3, "y": 1})

        try:
            for item in decoration_data.get("decorations", []):
                item_type = item.get("type")
                item_x = item.get("x")
                item_y = item.get("y")

                if item_type and item_x is not None and item_y is not None:
                    # Ensure item is within building bounds
                    if 0 < item_x < building.width -1 and 0 < item_y < building.height -1: # Ensure not on wall
                        global_x = building.global_origin_x + item_x
                        global_y = building.global_origin_y + item_y

                        decoration_tile_def = DECORATION_ITEM_DEFINITIONS.get(item_type)
                        if decoration_tile_def:
                            tile_in_chunk_x = building.x + item_x
                            tile_in_chunk_y = building.y + item_y

                            if 0 <= tile_in_chunk_x < CHUNK_SIZE and 0 <= tile_in_chunk_y < CHUNK_SIZE:
                                chunk.tiles[tile_in_chunk_y][tile_in_chunk_x] = Tile(
                                    char=decoration_tile_def["char"],
                                    color=decoration_tile_def["color"],
                                    passable=decoration_tile_def["passable"],
                                    name=decoration_tile_def.get("name", item_type),
                                    properties=decoration_tile_def.get("properties", {})
                                )

                                interaction_hint = decoration_tile_def.get("properties", {}).get("interaction_hint")
                                if interaction_hint == "sleep":
                                    if "sleep_spot" not in building.interaction_points:
                                        building.interaction_points["sleep_spot"] = (global_x, global_y)
                            else:
                                print(f"Error: Calculated tile coords for item '{item_type}' are out of chunk bounds.")
                        else:
                            print(f"Unknown decoration item type: {item_type}")
                    else:
                        print(f"Decoration item {item_type} out of bounds for building at ({building.x}, {building.y})")
        except Exception as e:
            print(f"Error during placeholder decoration: {e}")

        building.interior_decorated = True

    def _spawn_traveling_merchants(self):
        """Spawns a few traveling merchants in random villages."""
        all_villages = []
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if chunk.village:
                    all_villages.append(chunk.village)

        if not all_villages:
            return

        num_merchants = 2 # Let's spawn 2 for now
        for i in range(num_merchants):
            start_village = random.choice(all_villages)

            # Find a building in the village to place the merchant
            if not start_village.buildings:
                continue

            start_building = random.choice(start_village.buildings)
            start_x = start_building.global_center_x
            start_y = start_building.global_center_y

            prompt = LLM_PROMPTS["npc_personality"].format(
                player_criminal_points=self.player.social.reputation.get(REP_CRIMINAL, 0),
                player_hero_points=self.player.social.reputation.get(REP_HERO, 0),
                name_hint="a traveling merchant",
                personality_hint="worldly, business-savvy, friendly",
                family_ties_hint="none",
                attitude_to_player_hint="neutral"
            )
            llm_response = self._call_ollama(prompt)
            try:
                npc_data = json.loads(llm_response)

                merchant = NPC(
                    x=start_x,
                    y=start_y,
                    name=npc_data.get("name", f"Traveling Merchant {i+1}"),
                    dialogue=npc_data.get("dialogue", ["Looking for a deal?"]),
                    personality=npc_data.get("personality", "merchant"),
                    family_ties=npc_data.get("family_ties", "none"),
                    attitude_to_player=npc_data.get("attitude_to_player", "neutral"),
                    player_id=self.player.id
                )
                merchant.economic.profession = "Traveling Merchant"
                merchant.economic.money = random.randint(200, 500)
                # Give them some goods to sell
                merchant.economic.npc_inventory["healing_salve"] = random.randint(5, 15)
                merchant.economic.npc_inventory["iron_ingot"] = random.randint(3, 10)
                # merchant.npc_inventory["cloth"] = random.randint(10, 20)

                # Set their initial AI state
                merchant.current_task = "traveling_to_village"

                self.npcs.append(merchant) # Add them to the general NPC list, not a specific village
                self.add_message_to_chat_log(f"A traveling merchant, {merchant.name}, has begun their journey.")

            except json.JSONDecodeError as e:
                self.add_message_to_chat_log(f"Error parsing LLM response for Traveling Merchant: {e}")

    def talk_to_npc(self):
        # Find the closest NPC and interact with them
        closest_npc = None
        min_dist = float('inf')
        for npc in self.npcs + self.village_npcs:
            dist = math.sqrt((self.player.x - npc.x)**2 + (self.player.y - npc.y)**2)
            if dist < min_dist:
                min_dist = dist
                closest_npc = npc

        if closest_npc and min_dist <= 2: # Within 2 tiles
            # Use LLM for dynamic dialogue
            player_rep = self.player.social.reputation
            prompt = (
                f"The player (Criminal Points: {player_rep.get(REP_CRIMINAL, 0)}, Hero Points: {player_rep.get(REP_HERO, 0)}) "
                f"approaches {closest_npc.name}. "
                f"{closest_npc.name} is {closest_npc.social.personality}, their family ties are '{closest_npc.social.family_ties.get('description')}', "
                f"and their current attitude towards the player is '{closest_npc.attitude_to_player}'. "
                f"Generate a short, in-character dialogue response from {closest_npc.name} to the player. "
                f"The dialogue should reflect their personality, current attitude, and potentially acknowledge the player's reputation if significant. Keep it concise."
            )
            llm_dialogue = self._call_ollama(prompt)
            # self.add_message_to_chat_log(f"{closest_npc.name}: {llm_dialogue}") # Use chat log for consistency
            print(f"\n{closest_npc.name}: {llm_dialogue}") # Keep print for now as it's more direct for dialogue
            self.last_talked_to_npc = closest_npc # Store for potential follow-up actions like persuasion
        else:
            print("No one to talk to nearby.")
            self.last_talked_to_npc = None

    def _initialize_chunks(self):
        """Initializes chunk data based on the world generator's macro map."""
        chunks = [[None for _ in range(self.chunk_width)] for _ in range(self.chunk_height)]
        for y in range(self.chunk_height):
            for x in range(self.chunk_width):
                biome = self.generator.get_biome_at(x, y)
                poi_type = self.generator.get_poi_at(x, y, biome)
                chunks[y][x] = Chunk(biome, poi_type)
        return chunks

    def _find_starting_position(self):
        """
        Finds a suitable starting tile for the player, ensuring it's not too close to the edge.
        """
        center_x, center_y = self.player.x, self.player.y
        margin = 15  # Keep player this many tiles away from the edge

        # Check if the initial center position is already valid and safe
        if (margin <= center_x < WORLD_WIDTH - margin and
            margin <= center_y < WORLD_HEIGHT - margin and
            self.get_tile_at(center_x, center_y) and self.get_tile_at(center_x, center_y).passable):
            return

        # Search outwards from the center
        for r in range(1, max(WORLD_WIDTH, WORLD_HEIGHT) // 2):
            # Check top and bottom rows of the expanding search box
            for x_offset in range(-r, r + 1):
                for y_sign in [-1, 1]:
                    tx, ty = center_x + x_offset, center_y + (r * y_sign)

                    # Boundary and margin check
                    if not (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        continue

                    tile = self.get_tile_at(tx, ty)
                    if tile and tile.passable and "water" not in tile.name.lower():
                        chunk = self.chunks[ty // CHUNK_SIZE][tx // CHUNK_SIZE]
                        if chunk.biome == "plains": # Prioritize plains
                            self.player.x, self.player.y = tx, ty
                            return

            # Check left and right columns
            for y_offset in range(-r + 1, r):
                for x_sign in [-1, 1]:
                    tx, ty = center_x + (r * x_sign), center_y + y_offset

                    # Boundary and margin check
                    if not (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        continue

                    tile = self.get_tile_at(tx, ty)
                    if tile and tile.passable and "water" not in tile.name.lower():
                        chunk = self.chunks[ty // CHUNK_SIZE][tx // CHUNK_SIZE]
                        if chunk.biome == "plains": # Prioritize plains
                            self.player.x, self.player.y = tx, ty
                            return

        # Fallback if no plains found, search again for any passable tile within margin
        for r in range(1, max(WORLD_WIDTH, WORLD_HEIGHT) // 2):
            for x_offset in range(-r, r + 1):
                for y_sign in [-1, 1]:
                    tx, ty = center_x + x_offset, center_y + (r * y_sign)
                    if (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        tile = self.get_tile_at(tx, ty)
                        if tile and tile.passable and "water" not in tile.name.lower():
                            self.player.x, self.player.y = tx, ty
                            return
            for y_offset in range(-r + 1, r):
                for x_sign in [-1, 1]:
                    tx, ty = center_x + (r * x_sign), center_y + y_offset
                    if (margin <= tx < WORLD_WIDTH - margin and margin <= ty < WORLD_HEIGHT - margin):
                        tile = self.get_tile_at(tx, ty)
                        if tile and tile.passable and "water" not in tile.name.lower():
                            self.player.x, self.player.y = tx, ty
                            return

        print("Warning: No passable starting tile found within the safe margin. Player may be stuck.")

    def _generate_chunk_detail(self, chunk: Chunk, chunk_coord_x: int, chunk_coord_y: int):
        """Generates the detailed tiles for a chunk based on its biome and POI."""
        if chunk.is_generated: return

        if chunk.poi_type == "village":
            chunk.village = Village()
            chunk.village.lore = "The mists of time have obscured this village's history." # Fallback
            
            tiles = self._generate_village_layout(chunk, chunk_coord_x, chunk_coord_y)
        elif chunk.poi_type == "ruin":
            chunk.ruin = Ruin()
            chunk.ruin.lore = "The origins of this place are lost to time."

            tiles = self._generate_ruin_layout(chunk, chunk_coord_x, chunk_coord_y)
        else:
            # Generate the base biome tiles
            biome_def = TILE_DEFINITIONS[chunk.biome]
            tiles = [[Tile(biome_def["char"], biome_def["color"], biome_def["passable"], biome_def["name"], properties={}) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

            # If the biome is plains, add some detail
            if chunk.biome == "plains":
                for y_local in range(CHUNK_SIZE):
                    for x_local in range(CHUNK_SIZE):
                        # Add patches of tall grass, flowers, and then attempt to place trees
                        # Ensure trees don't overwrite existing non-plains features if any were placed by other logic (though unlikely here)
                        if tiles[y_local][x_local].name == "Plains": # Only try to place on base plains tiles
                            if random.random() < 0.03: # 3% chance for any tree
                                tree_type_roll = random.random()
                                tree_x_world = chunk_coord_x * CHUNK_SIZE + x_local
                                tree_y_world = chunk_coord_y * CHUNK_SIZE + y_local
                                if tree_type_roll < 0.4: # 40% of that 3% are Oaks
                                    tiles[y_local][x_local] = OakTree(tree_x_world, tree_y_world)
                                elif tree_type_roll < 0.7: # 30% are Apple
                                    tiles[y_local][x_local] = AppleTree(tree_x_world, tree_y_world)
                                else: # 30% are Pear
                                    tiles[y_local][x_local] = PearTree(tree_x_world, tree_y_world)
                                # Update transparency map for the new tree
                                if 0 <= tree_y_world < WORLD_HEIGHT and 0 <= tree_x_world < WORLD_WIDTH:
                                    self.transparency_map[tree_y_world, tree_x_world] = False # Trees block FOV
                            elif random.random() < 0.01: # 1% chance for a sapling
                                sapling_def = TILE_DEFINITIONS["sapling"]
                                tiles[y_local][x_local] = Tile(sapling_def["char"], sapling_def["color"], sapling_def["passable"], sapling_def["name"], properties=sapling_def.get("properties", {}).copy())
                            elif random.random() < 0.15: # 15% chance for tall grass (if not a tree)
                                tiles[y_local][x_local] = Tile(TILE_DEFINITIONS["tall_grass"]["char"], TILE_DEFINITIONS["tall_grass"]["color"], TILE_DEFINITIONS["tall_grass"]["passable"], TILE_DEFINITIONS["tall_grass"]["name"], TILE_DEFINITIONS["tall_grass"].get("properties", {}))
                            elif random.random() < 0.01: # 1% chance for a flower (if not a tree or grass)
                                tiles[y_local][x_local] = Tile(TILE_DEFINITIONS["flower"]["char"], TILE_DEFINITIONS["flower"]["color"], TILE_DEFINITIONS["flower"]["passable"], TILE_DEFINITIONS["flower"]["name"], TILE_DEFINITIONS["flower"].get("properties", {}))
                            # Animal Spawning
                            for animal_type, animal_def in ANIMAL_DEFINITIONS.items():
                                if chunk.biome in animal_def["spawn_biomes"] and random.random() < animal_def["spawn_chance"]:
                                    animal_x_world = chunk_coord_x * CHUNK_SIZE + x_local
                                    animal_y_world = chunk_coord_y * CHUNK_SIZE + y_local
                                    if not (abs(animal_x_world - self.player.x) < 10 and abs(animal_y_world - self.player.y) < 10):
                                        new_animal = Animal(animal_x_world, animal_y_world, name=animal_def["name"], animal_type=animal_type)
                                        new_animal.char = ord(animal_def["char"])
                                        new_animal.color = animal_def["color"]
                                        new_animal.max_hp = animal_def["max_hp"]
                                        new_animal.hp = new_animal.max_hp
                                        new_animal.behavior = animal_def.get("behavior")
                                        new_animal.is_hostile_to_player = animal_def["hostile"]
                                        new_animal.base_attack_name = animal_def["base_attack_name"]
                                        new_animal.base_attack_damage_dice = animal_def["base_attack_damage_dice"]
                                        new_animal.combat_behavior = animal_def["combat_behavior"]
                                        new_animal.gender = random.choice(["male", "female"])
                                        if "prey" in animal_def:
                                            new_animal.speed = 2
                                        self.npcs.append(new_animal)
        chunk.tiles = tiles
        chunk.is_generated = True

    def _generate_village_layout(self, chunk: Chunk, chunk_coord_x: int, chunk_coord_y: int):
        tiles = [[Tile(TILE_DEFINITIONS["plains"]["char"], TILE_DEFINITIONS["plains"]["color"], TILE_DEFINITIONS["plains"]["passable"], TILE_DEFINITIONS["plains"]["name"]) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

        # Add a pond to the village
        if random.random() < 0.5:
            pond_center_x = random.randint(5, CHUNK_SIZE - 6)
            pond_center_y = random.randint(5, CHUNK_SIZE - 6)
            pond_radius = random.randint(3, 5)
            for y in range(CHUNK_SIZE):
                for x in range(CHUNK_SIZE):
                    if (x - pond_center_x)**2 + (y - pond_center_y)**2 < pond_radius**2:
                        tiles[y][x] = Tile(TILE_DEFINITIONS["water"]["char"], TILE_DEFINITIONS["water"]["color"], TILE_DEFINITIONS["water"]["passable"], TILE_DEFINITIONS["water"]["name"])

        llm_prompt = LLM_PROMPTS["village_lore"].format(biome=chunk.biome)
        llm_response = self._call_ollama(llm_prompt)
        try:
            lore_data = json.loads(llm_response)
            chunk.village.lore = lore_data.get("village_lore", "The mists of time have obscured this village's history.")
        except json.JSONDecodeError:
            chunk.village.lore = "The mists of time have obscured this village's history."

        chunk_global_start_x = chunk_coord_x * CHUNK_SIZE
        chunk_global_start_y = chunk_coord_y * CHUNK_SIZE

        # Generate a more structured road network
        # Main road down the middle
        road_y = CHUNK_SIZE // 2
        for x in range(CHUNK_SIZE):
            tiles[road_y][x] = Tile(TILE_DEFINITIONS["road"]["char"], TILE_DEFINITIONS["road"]["color"], TILE_DEFINITIONS["road"]["passable"], TILE_DEFINITIONS["road"]["name"])

        # Cross road
        road_x = CHUNK_SIZE // 2
        for y in range(CHUNK_SIZE):
            tiles[y][road_x] = Tile(TILE_DEFINITIONS["road"]["char"], TILE_DEFINITIONS["road"]["color"], TILE_DEFINITIONS["road"]["passable"], TILE_DEFINITIONS["road"]["name"])

        # Place well at the center intersection
        well_local_x, well_local_y = road_x, road_y # These are local to chunk grid
        tiles[well_local_y][well_local_x] = Tile(TILE_DEFINITIONS["well"]["char"], TILE_DEFINITIONS["well"]["color"], TILE_DEFINITIONS["well"]["passable"], TILE_DEFINITIONS["well"]["name"])

        # Store global coordinates of the well
        global_well_x = chunk_global_start_x + well_local_x
        global_well_y = chunk_global_start_y + well_local_y
        if "well" not in chunk.village.interaction_points:
            chunk.village.interaction_points["well"] = []
        chunk.village.interaction_points["well"].append((global_well_x, global_well_y))
        # self.add_message_to_chat_log(f"Village well registered at G({global_well_x},{global_well_y})")


        # Generate Capital Hall
        capital_hall_w, capital_hall_h = 9, 7
        capital_hall_x = road_x - capital_hall_w - 2
        capital_hall_y = road_y - capital_hall_h // 2
        capital_hall = Building(capital_hall_x, capital_hall_y, capital_hall_w, capital_hall_h,
                                building_type="capital_hall", category="civic",
                                global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        capital_hall.max_workers = 3 # Town official and helpers
        chunk.village.add_building(capital_hall)
        self.buildings_by_id[capital_hall.id] = capital_hall
        self._draw_building(tiles, capital_hall, "capital_hall_wall")

        # Generate Jail
        jail_w, jail_h = 7, 5
        jail_x = road_x + 2
        jail_y = road_y - jail_h // 2
        jail = Building(jail_x, jail_y, jail_w, jail_h,
                        building_type="jail", category="civic",
                        global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        jail.max_workers = 2 # Guards
        chunk.village.add_building(jail)
        self.buildings_by_id[jail.id] = jail
        self._draw_building(tiles, jail, "jail_bars")

        # Generate Sheriff's Office
        sheriff_office_w, sheriff_office_h = 7, 5
        sheriff_office_x = road_x + 2
        sheriff_office_y = jail_y + jail_h + 2
        sheriff_office = Building(sheriff_office_x, sheriff_office_y, sheriff_office_w, sheriff_office_h,
                                  building_type="sheriff_office", category="civic_workplace",
                                  global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        sheriff_office.max_workers = 2 # Sheriff and deputy
        chunk.village.add_building(sheriff_office)
        self.buildings_by_id[sheriff_office.id] = sheriff_office
        self._draw_building(tiles, sheriff_office, "sheriff_office_wall")

        # Generate General Store
        store_w, store_h = 8, 6
        store_x = road_x - store_w - 2 # To the left of the main road, below capital hall if space
        store_y = capital_hall_y + capital_hall_h + 2
        # Basic placement, ensure it's within bounds (0 to CHUNK_SIZE - size)
        store_x = max(1, min(store_x, CHUNK_SIZE - store_w - 1))
        store_y = max(1, min(store_y, CHUNK_SIZE - store_h - 1))

        general_store = Building(store_x, store_y, store_w, store_h,
                                 building_type="general_store", category="commercial_workplace", # Workplace for merchant
                                 global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        general_store.max_workers = 2 # Merchant and assistant
        chunk.village.add_building(general_store)
        self.buildings_by_id[general_store.id] = general_store
        self._draw_building(tiles, general_store, "wood_wall")

        # Generate Tavern
        tavern_w, tavern_h = 9, 7
        tavern_x, tavern_y = 0, 0

        attempts = 0
        while attempts < 100:
            tavern_x = random.randint(1, CHUNK_SIZE - tavern_w - 1)
            tavern_y = random.randint(1, CHUNK_SIZE - tavern_h - 1)
            overlap = False
            for i in range(tavern_h):
                for j in range(tavern_w):
                    if tiles[tavern_y + i][tavern_x + j].name == "road":
                        overlap = True
                        break
                if overlap:
                    break
            for existing_building in chunk.village.buildings:
                if not (tavern_x + tavern_w < existing_building.x or tavern_x > existing_building.x + existing_building.width or
                        tavern_y + tavern_h < existing_building.y or tavern_y > existing_building.y + existing_building.height):
                    overlap = True
                    break
            if not overlap:
                break
            attempts += 1

        if attempts < 100:
            tavern = Building(tavern_x, tavern_y, tavern_w, tavern_h,
                                building_type="tavern", category="commercial_workplace",
                                global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
            tavern.max_workers = 3 # Keeper, Cook, maybe helper
            chunk.village.add_building(tavern)
            self.buildings_by_id[tavern.id] = tavern
            self._draw_building(tiles, tavern, "wood_wall")

        # Generate Lumber Mill (example producer workplace)
        lumber_mill_w, lumber_mill_h = 7, 7
        # Try to place it somewhat out of the way, e.g., near an edge
        lumber_mill_x = 1
        lumber_mill_y = CHUNK_SIZE - lumber_mill_h - 1
        # Basic check to avoid overlap with roads (very simple, could be improved)
        if tiles[lumber_mill_y][lumber_mill_x].name == "road" or tiles[lumber_mill_y+lumber_mill_h-1][lumber_mill_x+lumber_mill_w-1].name == "road":
            lumber_mill_x = CHUNK_SIZE - lumber_mill_w -1 # Try other side

        lumber_mill = Building(lumber_mill_x, lumber_mill_y, lumber_mill_w, lumber_mill_h,
                               building_type="lumber_mill", category="industrial_workplace",
                               global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        lumber_mill.max_workers = 4 # Foreman and woodcutters
        chunk.village.add_building(lumber_mill)
        self.buildings_by_id[lumber_mill.id] = lumber_mill
        self._draw_building(tiles, lumber_mill, "wood_wall")

        # Define work zones for the lumber mill after it's drawn
        # These coordinates are GLOBAL world coordinates
        # Chopping area is conceptual (nearby trees), so we mark it as existing but don't define specific tiles here.
        lumber_mill.work_zone_tiles["chopping_area"] = [] # Placeholder, logic will find trees

        # Log pile area: a 2x2 area inside or next to the mill.
        # Example: Place it near the bottom-left of the building interior (adjusting for walls)
        # Building.x and .y are local to chunk. Building.global_origin_x/y are world coords.
        log_pile_coords_global = []
        # Try to place it 1 tile in from the left wall, 1 tile up from the bottom wall.
        # Ensure it's within the building's actual floor space.
        # (building.width - 2) and (building.height - 2) give inner dimensions.
        # We need to place it relative to building.global_origin_x and building.global_origin_y
        if lumber_mill.width > 3 and lumber_mill.height > 3: # Ensure mill is large enough
            # Relative local coords for the start of the 2x2 log pile area
            local_pile_start_x = 1
            local_pile_start_y = lumber_mill.height - 3 # 1 up from bottom floor, then 1 more for 2x2

            for i in range(2): # y_offset
                for j in range(2): # x_offset
                    gx = lumber_mill.global_origin_x + local_pile_start_x + j
                    gy = lumber_mill.global_origin_y + local_pile_start_y + i
                    log_pile_coords_global.append((gx, gy))
            lumber_mill.work_zone_tiles["log_pile_area"] = log_pile_coords_global
            # self.add_message_to_chat_log(f"Lumber Mill {lumber_mill.id[:4]}: Log Pile at {log_pile_coords_global}")


        # Splitting area: another 2x2 area, perhaps near the log pile or another side.
        # Example: Place it near the bottom-right.
        splitting_area_coords_global = []
        if lumber_mill.width > 5 and lumber_mill.height > 3: # Need more width to avoid overlap if simple placement
            local_split_start_x = lumber_mill.width - 3
            local_split_start_y = lumber_mill.height - 3

            for i in range(2): # y_offset
                for j in range(2): # x_offset
                    gx = lumber_mill.global_origin_x + local_split_start_x + j
                    gy = lumber_mill.global_origin_y + local_split_start_y + i
                    splitting_area_coords_global.append((gx, gy))
            lumber_mill.work_zone_tiles["splitting_area"] = splitting_area_coords_global
            # self.add_message_to_chat_log(f"Lumber Mill {lumber_mill.id[:4]}: Splitting Area at {splitting_area_coords_global}")
        elif "log_pile_area" in lumber_mill.work_zone_tiles: # Fallback if not wide enough, use same as log pile
            lumber_mill.work_zone_tiles["splitting_area"] = lumber_mill.work_zone_tiles["log_pile_area"]
            # self.add_message_to_chat_log(f"Lumber Mill {lumber_mill.id[:4]}: Splitting Area (fallback) at {lumber_mill.work_zone_tiles['splitting_area']}")
        else: # If no log pile area either, mark as empty
            lumber_mill.work_zone_tiles["splitting_area"] = []

        # Generate Carpenter Shop
        carpenter_w, carpenter_h = 7, 6
        carpenter_x = road_x + 2
        carpenter_y = sheriff_office_y + sheriff_office_h + 2
        carpenter_x = max(1, min(carpenter_x, CHUNK_SIZE - carpenter_w - 1))
        carpenter_y = max(1, min(carpenter_y, CHUNK_SIZE - carpenter_h - 1))
        carpenter_shop = Building(carpenter_x, carpenter_y, carpenter_w, carpenter_h,
                                building_type="carpenter_shop", category="industrial_workplace",
                                global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        carpenter_shop.max_workers = 2
        chunk.village.add_building(carpenter_shop)
        self.buildings_by_id[carpenter_shop.id] = carpenter_shop
        self._draw_building(tiles, carpenter_shop, "wood_wall")

        # Generate Windmill
        windmill_w, windmill_h = 7, 7
        windmill_x = CHUNK_SIZE - windmill_w - 1
        windmill_y = CHUNK_SIZE - windmill_h - 1
        windmill = Building(windmill_x, windmill_y, windmill_w, windmill_h,
                            building_type="mill", category="industrial_workplace",
                            global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        windmill.max_workers = 2 # Miller and apprentice
        chunk.village.add_building(windmill)
        self.buildings_by_id[windmill.id] = windmill
        self._draw_building(tiles, windmill, "wood_wall")

        grinding_stone_coords_global = []
        if windmill.width > 2 and windmill.height > 2:
            local_stone_x = windmill.width // 2
            local_stone_y = windmill.height // 2
            gx = windmill.global_origin_x + local_stone_x
            gy = windmill.global_origin_y + local_stone_y
            grinding_stone_coords_global.append((gx, gy))
        windmill.work_zone_tiles["grinding_stone"] = grinding_stone_coords_global

        # Generate Bakery
        bakery_w, bakery_h = 7, 6
        bakery_x = 1
        bakery_y = 1
        bakery = Building(bakery_x, bakery_y, bakery_w, bakery_h,
                          building_type="bakery", category="commercial_workplace",
                          global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        bakery.max_workers = 2 # Baker and apprentice
        chunk.village.add_building(bakery)
        self.buildings_by_id[bakery.id] = bakery
        self._draw_building(tiles, bakery, "wood_wall")

        oven_coords_global = []
        if bakery.width > 2 and bakery.height > 2:
            local_oven_x = bakery.width // 2
            local_oven_y = 1
            gx = bakery.global_origin_x + local_oven_x
            gy = bakery.global_origin_y + local_oven_y
            oven_coords_global.append((gx, gy))
        bakery.work_zone_tiles["oven"] = oven_coords_global

        # Generate Mine
        mine_w, mine_h = 8, 6
        mine_x = 1
        mine_y = 1
        mine = Building(mine_x, mine_y, mine_w, mine_h,
                        building_type="mine", category="industrial_workplace",
                        global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        mine.max_workers = 5 # Mines need many workers
        chunk.village.add_building(mine)
        self.buildings_by_id[mine.id] = mine
        self._draw_building(tiles, mine, "stone_wall")

        # Define work zones for the Mine
        mine_face_coords_global = []
        if mine.width > 2 and mine.height > 2:
            # Example: Mine face is the back wall
            for i in range(1, mine.width - 1):
                gx = mine.global_origin_x + i
                gy = mine.global_origin_y + 1
                mine_face_coords_global.append((gx, gy))
        mine.work_zone_tiles["mine_face"] = mine_face_coords_global

        storage_area_coords_global = []
        if mine.width > 2 and mine.height > 2:
            # Example: Storage area is near the entrance
            for i in range(1, mine.width - 1):
                gx = mine.global_origin_x + i
                gy = mine.global_origin_y + mine.height - 2
                storage_area_coords_global.append((gx, gy))
        mine.work_zone_tiles["storage_area"] = storage_area_coords_global

        # Generate Blacksmith Shop
        blacksmith_w, blacksmith_h = 7, 6
        blacksmith_x = road_x + 2
        blacksmith_y = road_y + 2
        blacksmith_shop = Building(blacksmith_x, blacksmith_y, blacksmith_w, blacksmith_h,
                                   building_type="blacksmith_shop", category="industrial_workplace",
                                   global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        blacksmith_shop.max_workers = 2
        chunk.village.add_building(blacksmith_shop)
        self.buildings_by_id[blacksmith_shop.id] = blacksmith_shop
        self._draw_building(tiles, blacksmith_shop, "stone_wall")

        # Define work zones for the Blacksmith Shop
        forge_coords_global = []
        if blacksmith_shop.width > 2 and blacksmith_shop.height > 2:
            local_forge_x = 1
            local_forge_y = 1
            gx = blacksmith_shop.global_origin_x + local_forge_x
            gy = blacksmith_shop.global_origin_y + local_forge_y
            forge_coords_global.append((gx, gy))
        blacksmith_shop.work_zone_tiles["forge"] = forge_coords_global

        anvil_coords_global = []
        if blacksmith_shop.width > 2 and blacksmith_shop.height > 2:
            local_anvil_x = blacksmith_shop.width - 2
            local_anvil_y = blacksmith_shop.height - 2
            gx = blacksmith_shop.global_origin_x + local_anvil_x
            gy = blacksmith_shop.global_origin_y + local_anvil_y
            anvil_coords_global.append((gx, gy))
        blacksmith_shop.work_zone_tiles["anvil"] = anvil_coords_global

        # Generate Farm (example agricultural workplace)
        if random.random() < 0.7: # Chance to generate a farm
            farm_w, farm_h = 8, 6 # Farmhouse size
            # Try to place it somewhat out of the way, similar to lumber mill
            farm_x = CHUNK_SIZE - farm_w - 1
            farm_y = 1
            # Basic check to avoid overlap with roads (very simple)
            if tiles[farm_y][farm_x].name == "road" or tiles[farm_y+farm_h-1][farm_x+farm_w-1].name == "road":
                farm_x = 1 # Try other side
                farm_y = CHUNK_SIZE - farm_h - 5 # Move it down a bit too to vary from lumber mill

            farm_building = Building(farm_x, farm_y, farm_w, farm_h,
                                   building_type="farm", category="agricultural_workplace",
                                   global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
            farm_building.max_workers = 3 # Farmers and farmhands
            chunk.village.add_building(farm_building)
            self.buildings_by_id[farm_building.id] = farm_building
            self._draw_building(tiles, farm_building, "wood_wall") # Farmhouse uses wood wall

            # Define "field_patch" zone for the farm
            field_patch_coords_global = []
            field_width = 5  # e.g., 5x5 field
            field_height = 5
            # Place field to the south of the farmhouse, with a 1-tile gap
            field_start_local_x = farm_building.x + (farm_building.width // 2) - (field_width // 2) # Centered with farmhouse
            field_start_local_y = farm_building.y + farm_building.height + 1 # 1 tile below farmhouse

            # Ensure field patch is within chunk boundaries
            field_start_local_x = max(0, min(field_start_local_x, CHUNK_SIZE - field_width))
            field_start_local_y = max(0, min(field_start_local_y, CHUNK_SIZE - field_height))

            for r_y in range(field_height):
                for r_x in range(field_width):
                    # Check if tile is within overall chunk bounds before adding
                    # Also, for now, we assume these tiles are plains and will be tilled.
                    # A more robust version would check tiles[field_start_local_y + r_y][field_start_local_x + r_x]
                    # to ensure it's a suitable type before adding to field_patch.
                    if 0 <= field_start_local_x + r_x < CHUNK_SIZE and \
                       0 <= field_start_local_y + r_y < CHUNK_SIZE:

                        # Ensure the field tiles are initially plains (or similar farmable land)
                        # For now, we just define the zone. The farmer will till plains tiles within it.
                        # The actual tile objects at these coords are already set (e.g. to plains by default chunk gen)
                        # We are just collecting their global coordinates.
                        gx = chunk_global_start_x + field_start_local_x + r_x
                        gy = chunk_global_start_y + field_start_local_y + r_y
                        field_patch_coords_global.append((gx, gy))

            farm_building.work_zone_tiles["field_patch"] = field_patch_coords_global
            # self.add_message_to_chat_log(f"Farm {farm_building.id[:4]}: Field Patch at {field_patch_coords_global}")

            # Pre-populate farm with some seeds for the farmer to use
            if "wheat_seeds" in ITEM_DEFINITIONS:
                 farm_building.building_inventory["wheat_seeds"] = random.randint(5, 15)


        # Generate Fishing Hut
        if any(tiles[y][x].name == "water" for x in range(CHUNK_SIZE) for y in range(CHUNK_SIZE)):
            hut_w, hut_h = 5, 5
            for _ in range(100): # Attempts to place hut
                hut_x = random.randint(1, CHUNK_SIZE - hut_w - 1)
                hut_y = random.randint(1, CHUNK_SIZE - hut_h - 1)

                # Check for proximity to water
                is_near_water = False
                for i in range(-1, hut_h + 1):
                    for j in range(-1, hut_w + 1):
                        check_x, check_y = hut_x + j, hut_y + i
                        if 0 <= check_x < CHUNK_SIZE and 0 <= check_y < CHUNK_SIZE:
                            if tiles[check_y][check_x].name == "water":
                                is_near_water = True
                                break
                    if is_near_water:
                        break

                if is_near_water:
                    fishing_hut = Building(hut_x, hut_y, hut_w, hut_h, building_type="fishing_hut", category="industrial_workplace", global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
                    fishing_hut.max_workers = 2
                    chunk.village.add_building(fishing_hut)
                    self.buildings_by_id[fishing_hut.id] = fishing_hut
                    self._draw_building(tiles, fishing_hut, "wood_wall")

                    # Designate a fishing spot
                    for i in range(-2, hut_h + 2):
                        for j in range(-2, hut_w + 2):
                            spot_x, spot_y = hut_x + j, hut_y + i
                            if 0 <= spot_x < CHUNK_SIZE and 0 <= spot_y < CHUNK_SIZE:
                                if tiles[spot_y][spot_x].name == "water":
                                    if "fishing_spot" not in chunk.village.interaction_points:
                                        chunk.village.interaction_points["fishing_spot"] = []
                                    chunk.village.interaction_points["fishing_spot"].append((chunk_global_start_x + spot_x, chunk_global_start_y + spot_y))
                                    break
                        if "fishing_spot" in chunk.village.interaction_points:
                            break
                    break

        # Generate a few regular houses
        num_houses = random.randint(3, 5)
        for _ in range(num_houses):
            w, h = random.randint(5, 9), random.randint(5, 9)
            attempts = 0
            while attempts < 100:
                bx = random.randint(1, CHUNK_SIZE - w - 1)
                by = random.randint(1, CHUNK_SIZE - h - 1)
                overlap = False
                for i in range(h):
                    for j in range(w):
                        if tiles[by + i][bx + j].char == TILE_DEFINITIONS["road"]["char"]:
                            overlap = True; break
                    if overlap: break
                for existing_building in chunk.village.buildings:
                    if not (bx + w < existing_building.x or bx > existing_building.x + existing_building.width or
                            by + h < existing_building.y or by > existing_building.y + existing_building.height):
                        overlap = True; break
                if not overlap: break
                attempts += 1
            if attempts == 100: continue

            house = Building(bx, by, w, h, building_type="house", category="residential",
                             global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
            chunk.village.add_building(house)
            self.buildings_by_id[house.id] = house
            self._draw_building(tiles, house, "wood_wall")

        # Generate Library
        library_w, library_h = 8, 6
        library_x = road_x - library_w - 2
        library_y = road_y + 2
        library_x = max(1, min(library_x, CHUNK_SIZE - library_w - 1))
        library_y = max(1, min(library_y, CHUNK_SIZE - library_h - 1))
        library = Building(library_x, library_y, library_w, library_h,
                                building_type="library", category="civic_workplace",
                                global_chunk_x_start=chunk_global_start_x, global_chunk_y_start=chunk_global_start_y)
        library.max_workers = 2
        chunk.village.add_building(library)
        self.buildings_by_id[library.id] = library
        self._draw_building(tiles, library, "stone_wall")

        self._populate_village_npcs(chunk, chunk.village, chunk_coord_x, chunk_coord_y)
        self._initialize_economy(chunk.village)
        return tiles

    def _generate_ruin_layout(self, chunk: Chunk, chunk_coord_x: int, chunk_coord_y: int):
        """Generates a ruined structure within a chunk."""
        tiles = [[Tile(TILE_DEFINITIONS["plains"]["char"], TILE_DEFINITIONS["plains"]["color"], TILE_DEFINITIONS["plains"]["passable"], TILE_DEFINITIONS["plains"]["name"]) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

        wall_tile = TILE_DEFINITIONS["cracked_stone_wall"]
        floor_tile = TILE_DEFINITIONS["mossy_cobblestone"]
        rubble_decor = DECORATION_ITEM_DEFINITIONS["rubble"]

        # Simple rectangular ruin
        ruin_w = random.randint(8, 12)
        ruin_h = random.randint(8, 12)
        ruin_x = (CHUNK_SIZE - ruin_w) // 2
        ruin_y = (CHUNK_SIZE - ruin_h) // 2

        for y in range(ruin_h):
            for x in range(ruin_w):
                is_border = x == 0 or x == ruin_w - 1 or y == 0 or y == ruin_h - 1

                # Introduce gaps in the walls
                if is_border and random.random() > 0.3: # 30% chance of a gap
                    tiles[ruin_y + y][ruin_x + x] = Tile(wall_tile["char"], wall_tile["color"], wall_tile["passable"], wall_tile["name"], wall_tile["properties"])
                elif not is_border:
                    tiles[ruin_y + y][ruin_x + x] = Tile(floor_tile["char"], floor_tile["color"], floor_tile["passable"], floor_tile["name"])

        # Scatter rubble inside
        for _ in range(random.randint(5, 15)):
            rx = random.randint(1, ruin_w - 2)
            ry = random.randint(1, ruin_h - 2)
            tiles[ruin_y + ry][ruin_x + rx] = Tile(rubble_decor["char"], rubble_decor["color"], rubble_decor["passable"], rubble_decor["name"], rubble_decor["properties"])

        return tiles

    def _draw_building(self, tiles, building, wall_tile_key):
        for i in range(building.height):
            for j in range(building.width):
                is_border = i == 0 or i == building.height - 1 or j == 0 or j == building.width - 1
                is_window = (i == 1 and j == 0) or (i == 1 and j == building.width - 1) or \
                            (i == building.height - 2 and j == 0) or (i == building.height - 2 and j == building.width - 1)

                if is_border:
                    tiles[building.y + i][building.x + j] = Tile(TILE_DEFINITIONS[wall_tile_key]["char"], TILE_DEFINITIONS[wall_tile_key]["color"], TILE_DEFINITIONS[wall_tile_key]["passable"], TILE_DEFINITIONS[wall_tile_key]["name"])
                elif is_window and building.building_type == "house": # Only houses have windows for now
                    tiles[building.y + i][building.x + j] = Tile(TILE_DEFINITIONS["window"]["char"], TILE_DEFINITIONS["window"]["color"], TILE_DEFINITIONS["window"]["passable"], TILE_DEFINITIONS["window"]["name"])
                else:
                    tiles[building.y + i][building.x + j] = Tile(TILE_DEFINITIONS["wood_floor"]["char"], TILE_DEFINITIONS["wood_floor"]["color"], TILE_DEFINITIONS["wood_floor"]["passable"], TILE_DEFINITIONS["wood_floor"]["name"])

        # Place door for houses and capital hall
        if building.building_type in ["house", "capital_hall", "sheriff_office", "jail"]:
            door_x = building.x + building.width // 2
            door_y = building.y + building.height - 1 # Bottom wall

            door_def = DECORATION_ITEM_DEFINITIONS["wooden_door_closed"] # Default to closed door
            tiles[door_y][door_x] = Tile(
                char=door_def["char"],
                color=door_def["color"],
                passable=door_def["passable"],
                name=door_def["name"],
                properties=door_def["properties"] # Store door properties on the tile
            )

    def get_tile_at(self, x, y):
        if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
            return None
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE

        if not (0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height):
            return None

        chunk = self.chunks[chunk_y][chunk_x]
        if not chunk.is_generated:
            self._generate_chunk_detail(chunk, chunk_x, chunk_y) # Pass chunk_x, chunk_y
        return chunk.tiles[local_y][local_x]

    def get_building_at(self, x, y):
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE
        chunk = self.chunks[chunk_y][chunk_x]
        if chunk.poi_type == "village" and chunk.village:
            for building in chunk.village.buildings:
                if building.x <= local_x < building.x + building.width and \
                   building.y <= local_y < building.y + building.height:
                    return building
        return None

    def handle_player_movement(self, dx, dy) -> int:
        if self.player.state.is_jailed:
            self.add_message_to_chat_log("You are in jail and cannot move freely.")
            return 1 # Default action cost

        if self.player.state.is_sitting:
            self.player_attempt_stand_up()
            return 1 # Standing up costs a turn

        if self.player.state.is_riding:
            riding_animal = next((npc for npc in self.npcs if npc.id == self.player.state.riding_animal_id), None)
            if riding_animal:
                new_x, new_y = riding_animal.x + dx, riding_animal.y + dy
                destination_tile = self.get_tile_at(new_x, new_y)
                if destination_tile and destination_tile.passable:
                    riding_animal.x = new_x
                    riding_animal.y = new_y
                    self.player.x = new_x
                    self.player.y = new_y
                    self._update_player_fov()
                    return int(destination_tile.properties.get("movement_cost", 1))
                else:
                    return 0 # No movement if blocked
            else:
                # Fallback in case the animal ID is somehow invalid
                self.player.state.is_riding = False
                self.player.state.riding_animal_id = None
                return 0

        new_x, new_y = self.player.x + dx, self.player.y + dy
        destination_tile = self.get_tile_at(new_x, new_y)

        if destination_tile and destination_tile.passable:
            self.player.x, self.player.y = new_x, new_y
            self.player.state.last_dx, self.player.state.last_dy = dx, dy # Store last move

            movement_cost = int(destination_tile.properties.get("movement_cost", 1))

            # Check if player entered a building
            building = self.get_building_at(new_x, new_y)
            if building:
                # Player learns about the building upon entering
                building_name = building.building_type.replace('_', ' ')
                if building.id not in self.player.knowledge.known_locations:
                    self.player.knowledge.known_locations[building.id] = (building.global_center_x, building.global_center_y)
                    self.add_message_to_chat_log(f"You discover the {building_name}.")

                if not building.interior_decorated:
                    # Get the chunk the building is in to pass to decoration method
                    current_chunk_x = new_x // CHUNK_SIZE
                    current_chunk_y = new_y // CHUNK_SIZE
                    if 0 <= current_chunk_x < self.chunk_width and 0 <= current_chunk_y < self.chunk_height:
                        chunk_of_building = self.chunks[current_chunk_y][current_chunk_x]
                        self.decorate_building_interior(building, chunk_of_building)
                    else:
                        # This should ideally not happen if get_building_at found a building
                        self.add_message_to_chat_log("Error: Could not find chunk for building decoration.")

            self._update_player_fov() # Player moved, so update FOV

            # Clear sound events after player move (and subsequent NPC updates for that turn)
            # This means sounds last for one full game tick cycle.
            self.sound_events.clear()


            # Check for pass-through yields (e.g., from tall grass)
            if hasattr(destination_tile, 'properties') and "yields_on_pass_through" in destination_tile.properties:
                yield_data = destination_tile.properties["yields_on_pass_through"]
                if random.random() < yield_data.get("chance", 0):
                    item_key = yield_data["item_key"]
                    quantity_range = yield_data["quantity"]
                    quantity = random.randint(quantity_range[0], quantity_range[1]) if isinstance(quantity_range, list) else quantity_range

                    self.player.add_item(item_key, quantity)
                    item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                    self.add_message_to_chat_log(f"You found {quantity} {item_name} in the tall grass.")

                    # Replace the tall grass with plains
                    chunk_x, chunk_y = new_x // CHUNK_SIZE, new_y // CHUNK_SIZE
                    local_x, local_y = new_x % CHUNK_SIZE, new_y % CHUNK_SIZE
                    plains_def = TILE_DEFINITIONS["plains"]
                    self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
                        plains_def["char"], plains_def["color"], plains_def["passable"], plains_def["name"], plains_def.get("properties", {})
                    )


            return movement_cost
        return 0 # No movement if tile is not passable

    def emit_sound(self, origin_x: int, origin_y: int, sound_type: str, volume: int, source_entity_id: int | None = None):
        """Emits a sound event that NPCs might react to."""
        self.sound_events.append({
            "x": origin_x, "y": origin_y,
            "type": sound_type, "volume": volume,
            "source_id": source_entity_id # Optional: ID of player/NPC that made the sound
        })
        # self.add_message_to_chat_log(f"Debug: Sound '{sound_type}' emitted at ({origin_x},{origin_y}) vol {volume}")

    def update(self):
        """Main update function for the world, called once per game tick."""
        self.game_time += 1
        self._update_season()
        self._update_weather()
        self._update_light_level_and_fov()
        self._update_player_fov() # Only update player FOV here
        self._update_player_temperature()
        self._apply_temperature_effects(self.player)
        self._update_player_wetness()
        self._update_player_hunger_thirst()
        self._update_npc_schedules()
        self._update_npc_movement()
        self._update_world_environment()
        self._update_economy()
        self._update_npc_ages()
        self._update_npc_careers()
        self._update_abstract_simulation()
        self._process_npc_witness_events()
        self._process_npc_gossip_reaction()
        self._trigger_event_driven_conversation()
        self._handle_npc_speech()
        self._handle_npc_conversations()
        self._update_entity_titles()
        self._update_npc_reputations()
        self._handle_reputation_based_reactions()

    def _trigger_event_driven_conversation(self):
        """Checks if any NPC should start a conversation with the player about a witnessed event."""
        if self.game_state != "PLAYING":
            return

        for npc in self.village_npcs + self.npcs:
            if npc.physical.is_dead or npc.combat.is_hostile_to_player or self.chat_ui_active:
                continue

            # Check if player is visible and close
            if npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.x, self.player.y]:
                if abs(npc.x - self.player.x) + abs(npc.y - self.player.y) <= 3:
                    # Find an event the NPC knows about but hasn't discussed with the player yet
                    undiscussed_events = [e for e_id, e in npc.knowledge.known_events.items() if e_id not in npc.knowledge.discussed_event_ids]
                    if undiscussed_events:
                        event_to_discuss = random.choice(undiscussed_events)

                        # Gather context for the prompt
                        subject = self.get_entity_by_id(event_to_discuss.subject_id)
                        target = self.get_entity_by_id(event_to_discuss.target_id) if event_to_discuss.target_id else None

                        subject_name = getattr(subject, 'name', 'Someone')
                        target_name = getattr(target, 'name', 'someone')

                        prompt = LLM_PROMPTS["npc_event_conversation_starter"].format(
                            npc_name=npc.name,
                            npc_personality=npc.social.personality,
                            relationship_score=npc.relationships.get(self.player.id, 50),
                            event_type=event_to_discuss.type,
                            event_summary=event_to_discuss.description.format(subject=subject_name, target=target_name),
                            subject_name=subject_name,
                            target_name=target_name,
                            relationship_with_subject=npc.relationships.get(event_to_discuss.subject_id, 50),
                            relationship_with_target=npc.relationships.get(event_to_discuss.target_id, 50)
                        )

                        starter_dialogue = self._call_ollama(prompt)
                        if starter_dialogue:
                            self.add_message_to_chat_log(f"{npc.name} approaches you.")
                            self.start_npc_dialogue(npc) # This clears history and sets up the UI state
                            self.chat_ui_history.append((npc.name, starter_dialogue)) # Add the event-driven line
                            self.game_state = "DIALOGUE"
                            self.chat_ui_target_npc = npc
                            self.chat_ui_active = True
                            self.needs_text_input = True
                            npc.knowledge.discussed_event_ids.add(event_to_discuss.id)
                            break # Only one NPC starts a conversation per tick

    def _handle_reputation_based_reactions(self):
        """Makes NPCs react to famous or infamous characters they see."""
        if self.game_time % 10 != 0:  # Check every 10 ticks for performance
            return

        for npc in self.village_npcs + self.npcs:
            # Skip NPCs who are dead, already reacting, in combat, or creatures
            if npc.physical.is_dead or npc.schedule.current_task in ["fleeing_from_player", "greeting_player"] or npc.combat.is_hostile_to_player or npc.economic.profession == "Creature":
                continue

            if npc.id in self.npc_fov_maps:
                fov_map = self.npc_fov_maps[npc.id]
                # Check if the player is visible to the NPC
                if 0 <= self.player.x < WORLD_WIDTH and 0 <= self.player.y < WORLD_HEIGHT and fov_map[self.player.x, self.player.y]:

                    # Reaction to Infamy
                    if self.player.social.infamy >= 50:
                        # Guards and Sheriffs don't flee, they might become hostile (handled elsewhere)
                        if npc.economic.profession in ["Sheriff", "Guard"]:
                            continue

                        # Flee if personality is cowardly or neutral, and not already fleeing
                        if npc.social.personality in ["cowardly", "neutral", "commoner"] and npc.current_task != "fleeing_from_player":
                            npc.current_task = "fleeing_from_player"
                            self.add_message_to_chat_log(f"{npc.name} sees {self.player.social.title or 'an infamous figure'} and flees in terror!")
                            npc.schedule.current_path = [] # Force path recalculation

                    # Reaction to Fame
                    elif self.player.social.fame >= 50:
                         # Only friendly or neutral NPCs will greet
                        if npc.social.personality in ["friendly", "gregarious", "neutral", "commoner"] and npc.current_task != "greeting_player":
                            npc.current_task = "greeting_player"
                            self.add_message_to_chat_log(f"{npc.name} recognizes you and approaches to greet {self.player.social.title or 'a famous hero'}.")
                            npc.schedule.current_path = [] # Force path recalculation

    def get_entity_by_id(self, entity_id: int):
        """Finds an entity (player or NPC) by its ID."""
        if entity_id == self.player.id:
            return self.player
        for npc in self.village_npcs + self.npcs:
            if npc.id == entity_id:
                return npc
        return None

    def _update_npc_reputations(self):
        """Periodically scans the event log for significant NPC actions and awards fame/infamy."""
        if self.game_time % 100 != 0:  # Check every 100 ticks
            return

        for npc in self.village_npcs + self.npcs:
            # Check for heroic kills
            heroic_kills = [e for e in self.global_events if e.subject_id == npc.id and e.type == "entity_death" and e.target_id and isinstance(self.get_entity_by_id(e.target_id), DireWolf)]
            for kill in heroic_kills:
                npc.fame += 20
                self.add_message_to_chat_log(f"{npc.name} gains fame for killing a dire wolf!")

            # Check for murders
            murders = [e for e in self.global_events if e.subject_id == npc.id and e.type == "entity_death" and e.target_id and isinstance(self.get_entity_by_id(e.target_id), NPC)]
            for murder in murders:
                npc.infamy += 20
                self.add_message_to_chat_log(f"{npc.name} gains infamy for murder!")

    def _update_entity_titles(self):
        """Periodically checks and updates titles for all entities based on fame/infamy."""
        if self.game_time % 100 != 0:  # Check every 100 ticks
            return

        entities_to_check = [self.player] + self.village_npcs + self.npcs
        for entity in entities_to_check:
            if not entity.title and (entity.fame >= 50 or entity.infamy >= 50):
                recent_events = [e for e in self.global_events if e.subject_id == entity.id and e.type in ["quest_complete", "crime_witnessed", "entity_death"]]
                actions_summary = "\n".join([e.description for e in recent_events[-5:]]) or "No specific deeds of note."

                prompt = LLM_PROMPTS["player_title_generation"].format(
                    player_fame=entity.fame,
                    player_infamy=entity.infamy,
                    player_actions_summary=actions_summary
                )
                response_str = self._call_ollama(prompt)
                if response_str:
                    try:
                        response_json = json.loads(response_str)
                        new_title = response_json.get("title")
                        if new_title:
                            entity.title = new_title
                            if isinstance(entity, Player):
                                self.add_message_to_chat_log(f"You are now known as {new_title}.")
                            else:
                                self.add_message_to_chat_log(f"{entity.name} is now known as {new_title}.")
                    except json.JSONDecodeError:
                        pass

    def _update_npc_ages(self):
        """Increments the age of all NPCs once per game day."""
        if self.game_time > 0 and self.game_time % DAY_LENGTH_TICKS == 0:
            for npc in self.village_npcs + self.npcs:
                npc.age += 1

    def _evaluate_job_suitability(self, npc: NPC, job_building: Building) -> int:
        """Calculates a suitability score for an NPC and a potential job building."""
        score = random.randint(0, 20) # Base randomness

        # Personality fit
        b_type = job_building.building_type
        personality = npc.social.personality.lower()

        if "brave" in personality or "aggressive" in personality:
            if b_type in ["sheriff_office", "jail"]: score += 20
            elif b_type in ["mine", "lumber_mill"]: score += 10
        elif "smart" in personality or "studious" in personality:
            if b_type in ["library", "capital_hall"]: score += 20
            elif b_type in ["general_store"]: score += 10
        elif "greedy" in personality or "merchant" in personality:
            if b_type in ["general_store", "tavern"]: score += 20
        elif "nature" in personality or "outdoors" in personality:
            if b_type in ["farm", "fishing_hut", "lumber_mill"]: score += 20

        # Physical Stats fit (implied by combat stats)
        if hasattr(npc, 'combat') and npc.combat.max_hp > 25: # Strong/Tough
            if b_type in ["mine", "lumber_mill", "blacksmith_shop", "sheriff_office"]: score += 15

        return score

    def _update_npc_careers(self):
        """
        Simulates a job market where NPCs can quit unhappy jobs and find new ones.
        Run once per day.
        """
        # Logic runs if it's exactly the start of a day (after day 0)
        # Or if force-called in tests where game_time is set manually to a multiple.
        # print(f"DEBUG: _update_npc_careers called at game_time {self.game_time}. DAY_LENGTH_TICKS={DAY_LENGTH_TICKS}")
        if self.game_time == 0 or self.game_time % DAY_LENGTH_TICKS != 0:
             # print("DEBUG: Skipping career update (wrong time).")
             return

        # --- Job Satisfaction Update & Quitting ---
        # Iterate over a copy to allow modification of lists if needed (though we modify npc attributes)
        for npc in list(self.village_npcs):
            # print(f"DEBUG: Processing {npc.name}. Profession: {npc.economic.profession}, Satisfaction: {npc.economic.job_satisfaction}")
            if npc.physical.is_dead:
                continue

            if npc.economic.profession.lower() != "unemployed":
                # Factors affecting satisfaction
                satisfaction_change = 0

                # 1. Hunger/Thirst penalty
                if npc.physical.hunger > 50: satisfaction_change -= 5
                if npc.physical.thirst > 50: satisfaction_change -= 5

                # 2. Wealth impact
                if npc.economic.money < 10:
                    satisfaction_change -= 2 # Stress of poverty
                elif npc.economic.money > 200:
                    satisfaction_change += 1 # Financial security

                # 3. Random fluctuation (good day/bad day)
                satisfaction_change += random.randint(-5, 5)

                npc.economic.job_satisfaction = max(0, min(100, npc.economic.job_satisfaction + satisfaction_change))

                # print(f"DEBUG: {npc.name} new satisfaction: {npc.economic.job_satisfaction} (change: {satisfaction_change})")

                # Firing Logic (Performance check)
                if npc.economic.work_performance < 20 and random.random() < 0.1: # 10% chance to be fired if performance is very low
                    old_profession = npc.economic.profession
                    npc.economic.profession = "Unemployed"
                    npc.economic.job_satisfaction = 30 # Fired creates unhappiness
                    npc.economic.days_unemployed = 0
                    npc.economic.work_performance = 50 # Reset for next job

                    if npc.schedule.work_building_id:
                        # Just clear the schedule ID. 'occupants' tracks physical presence,
                        # so we don't remove them from the building list here (they might still be standing there).
                        npc.schedule.work_building_id = None

                    self.add_message_to_chat_log(f"{npc.name} was fired from their job as a {old_profession} for poor performance.")

                    # Log firing event
                    self.log_event(
                        event_type="npc_fired",
                        description=f"{{subject}} was fired from their job as {old_profession}.",
                        subject_id=npc.id,
                        location=(npc.x, npc.y)
                    )

                # Quitting Logic
                elif npc.economic.job_satisfaction < 10:
                    # NPC Quits
                    old_profession = npc.economic.profession
                    npc.economic.profession = "Unemployed"
                    npc.economic.job_satisfaction = 50 # Reset for "new life"
                    npc.economic.days_unemployed = 0
                    npc.economic.work_performance = 50

                    if npc.schedule.work_building_id:
                        # Just clear the schedule ID. 'occupants' tracks physical presence.
                        npc.schedule.work_building_id = None

                    self.add_message_to_chat_log(f"{npc.name} has quit their job as a {old_profession} due to low satisfaction.")

                    # Log quitting event
                    self.log_event(
                        event_type="npc_quit_job",
                        description=f"{{subject}} quit their job as {old_profession}.",
                        subject_id=npc.id,
                        location=(npc.x, npc.y)
                    )

            else: # Is Unemployed
                npc.economic.days_unemployed += 1
                # Satisfaction drops while unemployed
                npc.economic.job_satisfaction = max(0, npc.economic.job_satisfaction - 2)

        # --- Hiring Logic ---
        unemployed_npcs = [n for n in self.village_npcs if n.economic.profession.lower() == "unemployed" and not n.physical.is_dead]
        random.shuffle(unemployed_npcs) # Randomize who gets first pick

        for npc in unemployed_npcs:
            village = self._get_village_for_npc(npc)
            if not village: continue

            # Find workplaces with vacancies
            potential_jobs = []
            for building in village.buildings:
                if "workplace" in building.category:
                    # Count actual employees based on their assigned work building ID
                    current_workers_count = sum(1 for villager in self.village_npcs if villager.schedule.work_building_id == building.id and not villager.physical.is_dead)

                    if current_workers_count < building.max_workers:
                        potential_jobs.append(building)

            if potential_jobs:
                # Score jobs based on suitability
                best_job = None
                best_score = -1

                for job_building in potential_jobs:
                    score = self._evaluate_job_suitability(npc, job_building)
                    if score > best_score:
                        best_score = score
                        best_job = job_building

                new_workplace = best_job if best_job else random.choice(potential_jobs)
                self._assign_job(npc, new_workplace)

            # --- Emigration Logic ---
            # If unemployed for too long, leave the village
            elif npc.economic.days_unemployed > 7 and npc.economic.money < 50: # Unemployed for a week and poor
                npc.schedule.current_task = "leaving_village"
                # Set target to edge of map
                edge_x, edge_y = self._find_nearest_map_edge(npc)

                npc.schedule.current_path = self.calculate_path(npc.x, npc.y, edge_x, edge_y)
                npc.schedule.current_destination_coords = (edge_x, edge_y)

                self.add_message_to_chat_log(f"{npc.name} has decided to leave the village in search of better opportunities.")
                self.log_event(event_type="npc_emigrated", description=f"{{subject}} left the village.", subject_id=npc.id, location=(npc.x, npc.y))

        # --- Job Hopping (for Employed NPCs) ---
        # Check if employed NPCs want to switch jobs
        for npc in list(self.village_npcs):
            if npc.physical.is_dead or npc.economic.profession.lower() == "unemployed": continue

            # Only consider switching if somewhat dissatisfied
            if npc.economic.job_satisfaction < 60:
                village = self._get_village_for_npc(npc)
                if not village: continue

                current_work_building = self.buildings_by_id.get(npc.schedule.work_building_id)
                if not current_work_building: continue

                current_job_score = self._evaluate_job_suitability(npc, current_work_building)

                # Look for better vacancies
                potential_jobs = []
                for building in village.buildings:
                    if "workplace" in building.category and building.id != npc.schedule.work_building_id:
                        current_workers_count = sum(1 for villager in self.village_npcs if villager.schedule.work_building_id == building.id and not villager.physical.is_dead)
                        if current_workers_count < building.max_workers:
                            potential_jobs.append(building)

                if potential_jobs:
                    best_new_job = None
                    best_new_score = -1

                    for job_building in potential_jobs:
                        score = self._evaluate_job_suitability(npc, job_building)
                        if score > best_new_score:
                            best_new_score = score
                            best_new_job = job_building

                    # Switch if significantly better (20% better + switching friction)
                    if best_new_job and best_new_score > current_job_score * 1.2 + 5:
                        old_profession = npc.economic.profession
                        self._assign_job(npc, best_new_job)
                        self.add_message_to_chat_log(f"{npc.name} left their job as {old_profession} to become a {npc.economic.profession}.")


        # --- Immigration Logic ---
        # Check overall vacancies in villages and spawn new migrants
        # We'll do this per village found in chunks
        processed_villages = set()
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if chunk.village and chunk.village not in processed_villages:
                    village = chunk.village
                    processed_villages.add(village)

                    total_vacancies = 0
                    for building in village.buildings:
                        if "workplace" in building.category:
                            current_workers = sum(1 for v in self.village_npcs if v.schedule.work_building_id == building.id and not v.physical.is_dead)
                            total_vacancies += max(0, building.max_workers - current_workers)

                    # If there are significant vacancies, chance to spawn an immigrant
                    if total_vacancies >= 2 and random.random() < 0.2: # 20% chance if 2+ jobs open
                        # Spawn a new NPC
                        # We use _populate_village_npcs logic but for just one person
                        # Place them at town square or random edge
                        spawn_x = x_chunk * CHUNK_SIZE + CHUNK_SIZE // 2
                        spawn_y = y_chunk * CHUNK_SIZE + CHUNK_SIZE // 2
                        if "town_square_center" in village.interaction_points:
                            spawn_x, spawn_y = village.interaction_points["town_square_center"]

                        # Create a dummy chunk object to reuse population logic or just manually create
                        # Reusing _populate_village_npcs is hard because it does a batch.
                        # Let's create manually using similar logic.
                        self._spawn_migrant(village, spawn_x, spawn_y)

    def _assign_job(self, npc: NPC, work_building: Building):
        """Assigns a job to an NPC at a specific building."""
        npc.schedule.work_building_id = work_building.id

        # Determine profession name based on building type
        new_profession = "Worker" # Default
        if work_building.building_type == "sheriff_office":
            has_sheriff = any(o.economic.profession == "Sheriff" and o.schedule.work_building_id == work_building.id for o in self.village_npcs if o.id != npc.id)
            new_profession = "Deputy" if has_sheriff else "Sheriff"
        elif work_building.building_type == "general_store": new_profession = "Merchant"
        elif work_building.building_type == "tavern": new_profession = "Tavern Keeper"
        elif work_building.building_type == "lumber_mill":
            has_foreman = any(o.economic.profession == "Lumber Mill Foreman" and o.schedule.work_building_id == work_building.id for o in self.village_npcs if o.id != npc.id)
            new_profession = "Woodcutter" if has_foreman else "Lumber Mill Foreman"
        elif work_building.building_type == "farm": new_profession = "Farmer"
        elif work_building.building_type == "mine": new_profession = "Miner"
        elif work_building.building_type == "carpenter_shop": new_profession = "Carpenter"
        elif work_building.building_type == "mill": new_profession = "Miller"
        elif work_building.building_type == "bakery": new_profession = "Baker"
        elif work_building.building_type == "fishing_hut": new_profession = "Fisherman"
        elif work_building.building_type == "library": new_profession = "Scribe"
        elif work_building.building_type == "capital_hall": new_profession = "Town Official"
        elif work_building.building_type == "jail": new_profession = "Guard"
        elif work_building.building_type == "blacksmith_shop": new_profession = "Blacksmith"

        npc.economic.profession = new_profession
        npc.economic.job_satisfaction = 70
        npc.economic.days_unemployed = 0
        npc.economic.work_performance = 50 # Reset performance

        self.add_message_to_chat_log(f"{npc.name} has been hired as a {new_profession}.")

        self.log_event(
            event_type="npc_hired",
            description=f"{{subject}} started a new job as a {new_profession}.",
            subject_id=npc.id,
            location=(work_building.global_center_x, work_building.global_center_y)
        )

    def _spawn_migrant(self, village: Village, x: int, y: int):
        """Spawns a new migrant NPC into the village."""
        prompt = LLM_PROMPTS["npc_personality"].format(
            player_criminal_points=0,
            player_hero_points=0,
            name_hint="a newcomer",
            personality_hint="hopeful, looking for work",
            family_ties_hint="none",
            attitude_to_player_hint="neutral"
        )
        llm_response = self._call_ollama(prompt)
        try:
            npc_data = json.loads(llm_response)
            npc = NPC(
                x=x, y=y,
                name=npc_data.get("name", "Migrant"),
                dialogue=npc_data.get("dialogue", ["Hello, I'm looking for work."]),
                personality=npc_data.get("personality", "commoner"),
                player_id=None
            )
            npc.economic.profession = "Unemployed"
            npc.economic.money = random.randint(10, 50) # Modest starting funds

            # Try to find a home
            vacant_homes = [b for b in village.buildings if b.category == "residential" and not b.residents]
            if vacant_homes:
                home = random.choice(vacant_homes)
                npc.schedule.home_building_id = home.id
                home.residents.append(npc)
                npc.knowledge.known_locations["my home"] = (home.global_center_x, home.global_center_y)

            self.village_npcs.append(npc)
            self.add_message_to_chat_log(f"A migrant named {npc.name} has arrived in the village looking for work.")

        except json.JSONDecodeError:
            pass

    def _update_abstract_simulation(self):
        """
        Runs a lightweight simulation for off-screen villages to simulate high-level events
        like births, deaths, and economic production/consumption, creating a living history.
        """
        # This should not run on every single tick. Let's run it once per day.
        if self.game_time % DAY_LENGTH_TICKS != 0:
            return

        player_chunk_x = self.player.x // CHUNK_SIZE
        player_chunk_y = self.player.y // CHUNK_SIZE

        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if not chunk.village:
                    continue

                # Calculate distance to player
                dist = max(abs(x_chunk - player_chunk_x), abs(y_chunk - player_chunk_y))

                if dist > ABSTRACT_SIMULATION_DISTANCE_CHUNKS:
                    village = chunk.village
                    village_npcs = [npc for npc in self.village_npcs if self._get_village_for_npc(npc) == village]
                    if not village_npcs:
                        continue

                    # --- Economic Simulation ---
                    # 1. Production
                    for npc in village_npcs:
                        profession_data = get_profession_data(npc.economic.profession)
                        if not profession_data:
                            continue

                        # Simplified production logic
                        # Hardcode for Farmer since their production is tile-based
                        if npc.economic.profession == "Farmer":
                            village.supply["wheat"] = village.supply.get("wheat", 0) + 5 # Produces 5 wheat per day

                        # General production from sub-tasks
                        if profession_data and "default_sub_task_sequence" in profession_data:
                            for sub_task_id in profession_data["default_sub_task_sequence"]:
                                sub_task_data = get_sub_task_data(npc.economic.profession, sub_task_id)
                                if not sub_task_data: continue

                                # Consume resources
                                consumes = sub_task_data.get("consumes_item_from_workplace", {})
                                can_produce = True
                                for item_key, qty in consumes.items():
                                    if village.supply.get(item_key, 0) < qty:
                                        can_produce = False
                                        # Production failed, increase demand for the missing resource
                                        village.demand[item_key] = village.demand.get(item_key, 0) + qty
                                        break # Stop processing this sub-task

                                if can_produce:
                                    # Consume the items
                                    for item_key, qty in consumes.items():
                                        village.supply[item_key] -= qty
                                        if village.supply[item_key] <= 0:
                                            del village.supply[item_key]

                                    # Produce the items
                                    produces = sub_task_data.get("produces_item_at_workplace", {})
                                    for prod_item_key, prod_qty in produces.items():
                                        village.supply[prod_item_key] = village.supply.get(prod_item_key, 0) + prod_qty


                    # 2. Consumption (basic needs)
                    num_villagers = len(village_npcs)
                    # Everyone needs food
                    food_needed = num_villagers * 1 # 1 food item per person per day
                    food_supply = village.supply.get("bread", 0) # Assume bread is the primary food
                    consumed_food = min(food_needed, food_supply)

                    if "bread" in village.supply:
                        village.supply["bread"] = food_supply - consumed_food
                        if village.supply["bread"] <= 0:
                            del village.supply["bread"]

                    # If there's a shortfall, demand for food increases
                    food_shortfall = food_needed - consumed_food
                    if food_shortfall > 0:
                        village.demand["bread"] = village.demand.get("bread", 0) + food_shortfall

                    # --- Birth Simulation ---
                    # Find potential couples (for simplicity, any two adults living together)
                    potential_parents = [npc for npc in village_npcs if 18 < npc.age < 50]
                    if len(potential_parents) >= 2 and random.random() < 0.05: # 5% chance of a birth event per day
                        parent1 = random.choice(potential_parents)
                        parent2 = random.choice(potential_parents)
                        if parent1.id != parent2.id:
                            # For now, we don't create a new NPC object as it would be complex to place and manage.
                            # We just log the historical event.
                            self.log_event(
                                event_type="npc_birth",
                                description=f"A child was born to {parent1.name} and {parent2.name}.",
                                subject_id=parent1.id,
                                target_id=parent2.id,
                                location=(x_chunk * CHUNK_SIZE, y_chunk * CHUNK_SIZE)
                            )

                    # --- Death Simulation (Old Age) ---
                    elderly_npcs = [npc for npc in village_npcs if npc.age > 70]
                    for elder in elderly_npcs:
                        # Chance of dying increases with age
                        if random.random() < (elder.age - 70) / 100.0:
                            self.log_event(
                                event_type="entity_death",
                                description=f"{elder.name} died of old age.",
                                subject_id=elder.id,
                                location=(x_chunk * CHUNK_SIZE, y_chunk * CHUNK_SIZE)
                            )
                            # In a full abstract sim, we would remove the NPC from the world here.
                            # For now, we just log it. A more complex system would be needed to truly remove them.
                            # self.handle_npc_death(elder) # This could be problematic if the NPC is referenced elsewhere.

    def _process_npc_witness_events(self):
        """
        Periodically checks for global events and adds them to the knowledge
        of NPCs who could have witnessed them.
        """
        # Only process this periodically for performance
        if self.game_time % 10 != 0:
            return

        # Check events that have happened in the last 10 ticks
        recent_events = [event for event in self.global_events if self.game_time - event.timestamp <= 10]

        if not recent_events:
            return

        potential_witnesses = self.village_npcs + self.npcs
        for event in recent_events:
            if not event.location:
                continue

            event_x, event_y = event.location

            for npc in potential_witnesses:
                if npc.physical.is_dead or isinstance(npc, Animal) or (hasattr(event, 'subject_id') and event.subject_id == npc.id) or event.id in npc.knowledge.known_events:
                        continue

                # Check if NPC can see the event's location
                if npc.id in self.npc_fov_maps:
                    fov_map = self.npc_fov_maps[npc.id]
                    if 0 <= event_x < WORLD_WIDTH and 0 <= event_y < WORLD_HEIGHT:
                        if fov_map[event_y, event_x]:
                            # NPC witnessed the event. Add to their knowledge.
                            npc.knowledge.known_events[event.id] = event

    def _process_npc_gossip_reaction(self):
        """
        Periodically processes an NPC's known events to see if they react.
        """
        for npc in self.village_npcs + self.npcs:
            if isinstance(npc, Animal):
                continue

            if npc.physical.is_dead or not npc.knowledge.known_events:
                continue

            # Limit reaction checks to prevent spam/performance issues
            if random.random() > 0.01: # 1% chance per tick to process gossip
                continue

            # Select a random event from known events to react to
            event_to_process = random.choice(list(npc.known_events.values()))

            # Avoid reacting to very old news repeatedly
            time_since_event = time.time() - event_to_process.timestamp
            if time_since_event > (DAY_LENGTH_TICKS * 2): # Older than 2 days
                if random.random() > 0.05: # Very small chance to react to old news
                    continue

            # Prevent reacting to one's own actions
            if event_to_process.subject_id == npc.id:
                continue

            # Prevent reacting to the same event multiple times in a short period
            if event_to_process.id in npc.reacted_to_event_ids:
                continue

            # Get names for the prompt
            subject_entity = next((n for n in self.village_npcs + self.npcs if n.id == event_to_process.subject_id), self.player if event_to_process.subject_id == self.player.id else None)
            target_entity = next((n for n in self.village_npcs + self.npcs if n.id == event_to_process.target_id), self.player if event_to_process.target_id == self.player.id else None) if event_to_process.target_id else None

            subject_name = getattr(subject_entity, 'name', 'Someone') if subject_entity else 'Someone'
            target_name = getattr(target_entity, 'name', 'someone') if target_entity else 'someone'

            # Frame the event for the LLM
            event_summary = event_to_process.description.format(subject=subject_name, target=target_name)

            prompt = LLM_PROMPTS["npc_gossip_reaction"].format(
                npc_name=npc.name,
                npc_personality=npc.social.personality,
                npc_attitude_to_subject=npc.social.relationships.get(event_to_process.subject_id, 50), # Use relationship score
                npc_attitude_to_target=npc.social.relationships.get(event_to_process.target_id, 50) if event_to_process.target_id else 50,
                event_summary=event_summary,
                event_type=event_to_process.type
            )

            response_str = self._call_ollama(prompt)
            if not response_str:
                continue

            try:
                response_json = json.loads(response_str)
                action = response_json.get("action")
                dialogue = response_json.get("internal_thought_dialogue")
                relationship_change_subject = response_json.get("relationship_change_subject", 0)
                relationship_change_target = response_json.get("relationship_change_target", 0)

                # Log the internal thought if player is very close
                if dialogue and abs(npc.x - self.player.x) + abs(npc.y - self.player.y) <= 2:
                    self.add_message_to_chat_log(f"({npc.name} seems to be pondering something: '{dialogue}')")

                # Mark as reacted
                npc.reacted_to_event_ids.add(event_to_process.id)

                # Apply relationship changes
                if relationship_change_subject != 0 and subject_entity:
                    npc.social.relationships[subject_entity.id] = npc.social.relationships.get(subject_entity.id, 50) + relationship_change_subject
                    # self.add_message_to_chat_log(f"Debug: {npc.name}'s opinion of {subject_name} changed by {relationship_change_subject}.")

                if relationship_change_target != 0 and target_entity:
                    npc.social.relationships[target_entity.id] = npc.social.relationships.get(target_entity.id, 50) + relationship_change_target
                    # self.add_message_to_chat_log(f"Debug: {npc.name}'s opinion of {target_name} changed by {relationship_change_target}.")

                if action == "form_grudge" and subject_entity:
                    npc.add_grudge(subject_entity.id, f"Heard they were involved in: {event_summary}")
                    self.add_message_to_chat_log(f"Debug: {npc.name} now holds a grudge against {subject_name}.")
                elif action == "mourn_death" and subject_entity:
                    # Find the home of the deceased
                    if subject_entity.home_building_id:
                        home_building = self.buildings_by_id.get(subject_entity.home_building_id)
                        if home_building:
                            npc.current_task = "mourning"
                            npc.task_target_coords = (home_building.global_center_x, home_building.global_center_y)
                            npc.current_path = []
                            npc.task_timer = random.randint(100, 200) # Mourn for a while
                elif action == "investigate_crime_scene" and event_to_process.location:
                    npc.current_task = "investigating"
                    npc.task_target_coords = event_to_process.location
                    npc.current_path = []
                    npc.task_timer = random.randint(50, 100) # Investigate for a bit

            except json.JSONDecodeError:
                # self.add_message_to_chat_log(f"Debug: Failed to parse gossip reaction for {npc.name}: {response_str}")
                pass

    def _get_village_at_coords(self, x: int, y: int) -> Village | None:
        """Gets the village object at a given world coordinate, if one exists."""
        chunk_x = x // CHUNK_SIZE
        chunk_y = y // CHUNK_SIZE
        if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
            chunk = self.chunks[chunk_y][chunk_x]
            if chunk and chunk.village:
                return chunk.village
        return None

    def _get_witnesses_to_action(self, action_x: int, action_y: int, action_type: str) -> list[NPC]:
        """
        Finds NPCs who witness a criminal act.
        A witness must have line of sight to the action.
        """
        witnesses = []
        # Combine all NPCs who could be witnesses
        potential_witnesses = self.village_npcs + self.npcs

        for npc in potential_witnesses:
            if npc.is_dead:
                continue

            # Check if NPC can see the tile where the action occurred
            can_see_action = False
            if npc.id in self.npc_fov_maps:
                fov_map = self.npc_fov_maps[npc.id]
                if 0 <= action_x < WORLD_WIDTH and 0 <= action_y < WORLD_HEIGHT:
                    if fov_map[action_x, action_y]:
                        can_see_action = True

            if can_see_action:
                # Simple logic for now: if they can see it, they are a witness.
                # Future: Could add personality checks (e.g., some ignore theft, some are brave/cowardly)
                witnesses.append(npc)

        return witnesses

    def _handle_witness_reaction(self, witness: NPC, crime_type: str, criminal: Player or NPC, victim: NPC | None = None):
        """Determines how an NPC reacts to witnessing a crime using an LLM prompt."""
        if witness.is_hostile_to_player or witness.current_task in ["fleeing_from_player", "going_to_report_crime", "combat_action_flee_from_player"]:
            return

        victim_name = "N/A"
        witness_attitude_to_victim = "N/A"
        if victim:
            victim_name = victim.name
            if witness.economic.profession == victim.economic.profession and witness.economic.profession not in ["Unemployed", "Farmer"]:
                 witness_attitude_to_victim = "friendly"
            else:
                 witness_attitude_to_victim = "neutral"

        # Grant Infamy for witnessed crimes
        criminal.social.infamy += 5
        if isinstance(criminal, Player):
            self.add_message_to_chat_log("Your infamy has increased by 5.")
        else:
            self.add_message_to_chat_log(f"{criminal.name}'s infamy has increased by 5.")

        # Log the crime event itself
        self.log_event(
            event_type="crime_witnessed",
            description=f"{{subject}} was witnessed by {witness.name} committing the crime of {crime_type}.",
            subject_id=criminal.id,
            target_id=victim.id if victim else None,
            location=(witness.x, witness.y) # Location is where the witness was
        )

        prompt = LLM_PROMPTS["npc_witness_reaction"].format(
            witness_name=witness.name,
            witness_personality=witness.social.personality,
            witness_profession=witness.economic.profession,
            witness_attitude_to_criminal=witness.attitude_to_player,
            witness_attitude_to_victim=witness_attitude_to_victim,
            crime_type=crime_type,
            criminal_name=criminal.char, # Using '@' for player for now
            victim_name=victim_name
        )

        response_str = self._call_ollama(prompt)
        if not response_str:
            self.add_message_to_chat_log(f"{witness.name} seems confused by what they saw. (LLM Error)")
            return

        try:
            response_json = json.loads(response_str)
            reaction = response_json.get("reaction")
            dialogue = response_json.get("dialogue", f"{witness.name} gasps!")
            grudge_reason = response_json.get("grudge_reason")

            self.add_message_to_chat_log(dialogue) # Show the witness's verbal reaction

            if grudge_reason:
                witness.add_grudge(criminal.id, grudge_reason)
                # Make this message conditional on the criminal being the player for clarity
                if isinstance(criminal, Player):
                    self.add_message_to_chat_log(f"({witness.name} now holds a grudge against you: {grudge_reason})")

            if reaction == "become_hostile":
                witness.is_hostile_to_player = True
            elif reaction == "report_crime":
                sheriff_office = self._find_nearest_building_of_type(witness, "sheriff_office")
                if sheriff_office:
                    witness.current_task = "going_to_report_crime"
                    witness.task_target_coords = (sheriff_office.global_center_x, sheriff_office.global_center_y)
                    witness.current_path = [] # Clear path for new destination
                else:
                    self.add_message_to_chat_log(f"{witness.name} wants to report the crime but doesn't know where the sheriff is.")
            elif reaction == "flee":
                witness.current_task = "combat_action_flee_from_player"
                witness.current_path = [] # Force path recalculation
            elif reaction == "admonish":
                # The grudge already lowered the relationship, so this is just a verbal action.
                pass
            elif reaction == "ignore":
                # Do nothing.
                pass

        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"{witness.name} seems unsure how to react. (LLM Format Error: {response_str})")

    def _update_economy(self):
        """Periodically updates the supply and demand of all villages."""
        for y_chunk in range(self.chunk_height):
            for x_chunk in range(self.chunk_width):
                chunk = self.chunks[y_chunk][x_chunk]
                if chunk.village:
                    village = chunk.village
                    # Decay demand over time
                    for item_key in list(village.demand.keys()):
                        village.demand[item_key] *= 0.99
                        if village.demand[item_key] < 1:
                            del village.demand[item_key]

                    # Recalculate supply from scratch
                    village.supply = {}
                    for building in village.buildings:
                        for item_key, quantity in building.building_inventory.items():
                            village.supply[item_key] = village.supply.get(item_key, 0) + quantity

    def get_dynamic_price(self, item_key: str, village: Village) -> int:
        """Calculates the dynamic price of an item based on village supply and demand."""
        base_price = ITEM_DEFINITIONS.get(item_key, {}).get("value", 0)
        if not village:
            return base_price

        supply = village.supply.get(item_key, 1)  # Avoid division by zero
        demand = village.demand.get(item_key, 1)

        # Simple formula: price = base_price * (demand / supply)
        # Add clamping to prevent extreme prices
        price_modifier = max(0.2, min(5.0, demand / supply))

        # Apply reputation modifier
        fame_discount = (self.player.social.fame / 1000) # 0.1% discount per fame point
        infamy_penalty = (self.player.social.infamy / 500) # 0.2% penalty per infamy point
        reputation_modifier = 1.0 - fame_discount + infamy_penalty
        price_modifier *= reputation_modifier

        dynamic_price = int(base_price * price_modifier)

        return max(1, dynamic_price) # Ensure price is at least 1

    def _is_player_near_workstation(self, required_workstation: str) -> bool:
        """Checks if the player is adjacent to a required workstation."""
        if not required_workstation:
            return True # No workstation required

        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                tile = self.get_tile_at(self.player.x + dx, self.player.y + dy)
                if tile and hasattr(tile, 'properties') and tile.properties.get("workstation_type") == required_workstation:
                    return True
        return False

    def craft_item(self, item_key: str):
        """Crafts an item if the player has the required resources and provides feedback on failure."""
        if item_key not in ITEM_DEFINITIONS:
            self.add_message_to_chat_log(f"You don't know how to craft '{item_key}'.")
            return

        item_def = ITEM_DEFINITIONS[item_key]
        recipe = item_def.get("crafting_recipe", {})
        if not recipe:
            self.add_message_to_chat_log(f"There is no recipe for '{item_def['name']}'.")
            return

        # Check for ingredients first
        for resource_key, required_qty in recipe.items():
            if not self.player.has_item(resource_key, required_qty):
                resource_name = ITEM_DEFINITIONS.get(resource_key, {}).get("name", resource_key)
                self.add_message_to_chat_log(f"You don't have enough {resource_name}. (Need {required_qty})")
                return

        # Check for workstation
        required_workstation = item_def.get("required_workstation")
        if required_workstation and not self._is_player_near_workstation(required_workstation):
            self.add_message_to_chat_log(f"You need to be near a {required_workstation} to craft this.")
            return

        # All checks passed, proceed to consume resources and craft
        for resource_key, required_qty in recipe.items():
            if not self.player.remove_item(resource_key, required_qty):
                self.add_message_to_chat_log(f"Error consuming {resource_key} for crafting. Aborted.")
                return

        # Add crafted item
        self.player.add_item(item_key, 1)
        self.add_message_to_chat_log(f"You crafted a {ITEM_DEFINITIONS[item_key]['name']}!")


    def use_item(self, item_key: str):
        """Uses an item from the player's inventory."""
        item_def = ITEM_DEFINITIONS.get(item_key)
        if not item_def:
            self.add_message_to_chat_log(f"You don't know how to use '{item_key}'.")
            return

        # Handle equipping armor
        if "armor" in item_def.get("item_type_tags", []):
            self.player.equip_armor(item_key)
            return

        # Check if trying to use (extinguish) an active light source by "using" its lit state key
        if self.player.equipment.equipped_light_item_key == item_key and item_def.get("properties", {}).get("emits_light"):
            # This means player is trying to "use" their currently lit torch, so extinguish it.
            extinguish_becomes_key = item_def.get("properties", {}).get("on_extinguish_becomes")
            if extinguish_becomes_key:
                self.player.economic.inventory[extinguish_becomes_key] = self.player.economic.inventory.get(extinguish_becomes_key, 0) + 1

            self.add_message_to_chat_log(f"You extinguish your {self.player.equipment.equipped_light_item_key}.")
            self.player.equipment.equipped_light_item_key = None
            self.player.equipment.current_personal_light_radius = 0
            self.player.equipment.light_source_active_until_tick = -1
            self._update_player_fov()
            return

        # Standard item usage from inventory
        if self.player.economic.inventory.get(item_key, 0) <= 0:
            self.add_message_to_chat_log(f"You don't have any {item_def.get('name', item_key)} to use.")
            return

        on_use_effect = item_def.get("on_use_effect")

        if on_use_effect == "light_torch":
            if self.player.equipment.equipped_light_item_key: # Already has a light source active
                self.add_message_to_chat_log(f"You already have a {self.player.equipment.equipped_light_item_key} lit.")
                return

            # Consume the unlit_torch
            self.player.economic.inventory[item_key] -= 1
            if self.player.economic.inventory[item_key] <= 0:
                del self.player.economic.inventory[item_key]

            # Activate "torch_lit" state
            lit_torch_def = ITEM_DEFINITIONS.get("torch_lit", {})
            self.player.equipment.equipped_light_item_key = "torch_lit" # Use the key for the lit definition
            self.player.equipment.current_personal_light_radius = lit_torch_def.get("properties", {}).get("light_radius", 0)
            duration = lit_torch_def.get("properties", {}).get("duration_ticks", -1)
            if duration > 0:
                self.player.equipment.light_source_active_until_tick = self.game_time + duration
            else:
                self.player.equipment.light_source_active_until_tick = -1 # Infinite or not applicable

            self.add_message_to_chat_log(f"You light the {item_def.get('name', item_key)}. It casts a warm glow.")
            self._update_player_fov()
            return

        # Existing healing logic (or other on_use dictionary based effects)
        on_use_dict = item_def.get("on_use")
        if on_use_dict:
            heal_amount = on_use_dict.get("heal_amount")
            if heal_amount:
                if self.player.combat.hp >= self.player.combat.max_hp:
                    self.add_message_to_chat_log("You are already at full health!")
                else:
                    self.player.combat.hp = min(self.player.combat.max_hp, self.player.combat.hp + heal_amount)
                    self.player.economic.inventory[item_key] -= 1
                    if self.player.economic.inventory[item_key] <= 0: del self.player.economic.inventory[item_key]
                    self.add_message_to_chat_log(f"You used a {item_def['name']} and healed {heal_amount} HP.")
                    consumed = True

            reduces_hunger_amount = on_use_dict.get("reduces_hunger")
            if reduces_hunger_amount:
                if self.player.physical.hunger > 0 :
                    self.player.physical.hunger = max(0, self.player.physical.hunger - reduces_hunger_amount)
                    self.add_message_to_chat_log(f"You eat the {item_def['name']}. You feel less hungry.")
                    if not consumed: # Consume item if not already consumed by healing
                        self.player.economic.inventory[item_key] -= 1
                        if self.player.economic.inventory[item_key] <= 0: del self.player.economic.inventory[item_key]
                    consumed = True
                    self._update_player_hunger_thirst(initial_setup=True) # Update status messages immediately
                else:
                    self.add_message_to_chat_log(f"You are not hungry enough to eat the {item_def['name']}.")


            reduces_thirst_amount = on_use_dict.get("reduces_thirst")
            if reduces_thirst_amount:
                if self.player.physical.thirst > 0:
                    self.player.physical.thirst = max(0, self.player.physical.thirst - reduces_thirst_amount)
                    self.add_message_to_chat_log(f"You drink the {item_def.get('name', item_key)}. You feel less thirsty.")
                    if not consumed: # Consume item if not already consumed
                        self.player.economic.inventory[item_key] -= 1
                        if self.player.economic.inventory[item_key] <= 0: del self.player.economic.inventory[item_key]
                    consumed = True
                    self._update_player_hunger_thirst(initial_setup=True) # Update status messages immediately
                else:
                    self.add_message_to_chat_log(f"You are not thirsty enough for the {item_def.get('name', item_key)}.")

            if consumed:
                return # Action taken

        # Fallback if no specific use effect handled
        self.add_message_to_chat_log(f"You can't figure out how to use the {item_def.get('name', item_key)} right now.")

    def player_can_craft(self, item_key: str) -> bool:
        """Checks if the player has the resources and is near the required workstation to craft an item."""
        if item_key not in ITEM_DEFINITIONS:
            return False

        item_def = ITEM_DEFINITIONS[item_key]
        recipe = item_def.get("crafting_recipe", {})
        if not recipe:
            return False

        # Check for ingredients
        for resource_key, required_qty in recipe.items():
            if not self.player.has_item(resource_key, required_qty):
                return False

        # Check for workstation
        required_workstation = item_def.get("required_workstation")
        if required_workstation and not self._is_player_near_workstation(required_workstation):
            return False

        return True

    def drop_item_on_map(self, item_key: str, quantity: int, x: int, y: int):
        """Drops an item or stack of items onto the map at specified coordinates."""
        if quantity <= 0:
            return

        if (x, y) not in self.items_on_map:
            self.items_on_map[(x, y)] = []

        # Check if item of same key already exists at location to stack
        item_found_for_stacking = False
        for item_on_tile in self.items_on_map[(x, y)]:
            if item_on_tile["item_key"] == item_key:
                item_def = ITEM_DEFINITIONS.get(item_key, {})
                if item_def.get("stackable", False):
                    item_on_tile["quantity"] += quantity
                    item_found_for_stacking = True
                    break

        if not item_found_for_stacking:
            self.items_on_map[(x, y)].append({"item_key": item_key, "quantity": quantity})

        # self.add_message_to_chat_log(f"Dropped {quantity} {ITEM_DEFINITIONS.get(item_key,{}).get('name',item_key)} at ({x},{y}).") # Optional debug

    def remove_item_from_map(self, item_key: str, quantity: int, x: int, y: int) -> bool:
        """Removes a specified quantity of an item from the map at coordinates. Returns True if successful."""
        if quantity <= 0: return False
        if (x, y) in self.items_on_map:
            items_at_loc = self.items_on_map[(x, y)]
            for i, item_on_tile in enumerate(items_at_loc):
                if item_on_tile["item_key"] == item_key:
                    if item_on_tile["quantity"] >= quantity:
                        item_on_tile["quantity"] -= quantity
                        if item_on_tile["quantity"] <= 0: items_at_loc.pop(i)
                        if not items_at_loc: del self.items_on_map[(x,y)]
                        return True
                    return False
            return False
        return False

    def complete_quest(self, quest_id: str, quest_giver_npc: NPC):
        """Handles player attempting to complete a quest."""
        if quest_id not in self.player.knowledge.active_quests:
            self.add_message_to_chat_log("Error: Quest not found or not active.")
            if self.chat_ui_active and self.chat_ui_target_npc == quest_giver_npc:
                self.chat_ui_history.append((quest_giver_npc.name, "Are you sure we had an arrangement like that?"))
            return

        active_quest_data = self.player.knowledge.active_quests[quest_id]
        is_static_quest = quest_id in QUEST_DEFINITIONS

        # --- Check Completion Conditions ---
        is_complete = False
        if active_quest_data["type"] == "fetch":
            if self.player.has_item(active_quest_data["item_to_fetch_key"], active_quest_data["item_fetch_count"]):
                is_complete = True
        elif active_quest_data["type"] == "kill":
            if active_quest_data["progress"] >= active_quest_data["target_count"]:
                is_complete = True

        # --- Handle Dialogue and Rewards ---
        if is_complete:
            # Consume items for fetch quests
            if active_quest_data["type"] == "fetch":
                self.player.remove_item(active_quest_data["item_to_fetch_key"], active_quest_data["item_fetch_count"])

            log_message = f"Quest '{active_quest_data['title']}' completed."
            completion_dialogue = "Thank you so much! You're a lifesaver."

            if is_static_quest:
                quest_def = QUEST_DEFINITIONS.get(quest_id, {})
                reward_money = quest_def.get("reward_money", 0)
                if reward_money > 0:
                    self.player.economic.money += reward_money

                reward_items = quest_def.get("reward_items", {})
                for item_key, quantity in reward_items.items():
                    self.player.add_item(item_key, quantity)

                self.player.social.fame += 10 # Standard fame for static quests
                log_message = quest_def.get("completion_message_log", log_message)
                completion_dialogue = quest_def.get("dialogue_complete_report", completion_dialogue)

                self.log_event(
                    event_type="quest_complete",
                    description=f"{{subject}} completed the quest: {active_quest_data['title']}",
                    subject_id=self.player.id,
                    location=(self.player.x, self.player.y)
                )
            else: # Dynamic quest
                reward_money = 25
                self.player.economic.money += reward_money
                self.add_message_to_chat_log(f"You received {reward_money} money.")

                quest_giver_npc.physical.hunger = 0
                quest_giver_npc.physical.thirst = 0
                quest_giver_npc.social.relationships[self.player.id] = quest_giver_npc.social.relationships.get(self.player.id, 50) + 15


            self.add_message_to_chat_log(log_message)

            # Update quest status
            del self.player.knowledge.active_quests[quest_id]
            self.player.knowledge.completed_quests.append(quest_id)

            # Dialogue
            if self.chat_ui_active:
                self.chat_ui_history.append((quest_giver_npc.name, completion_dialogue))
        else:
            # Dialogue for incomplete quest
            if self.chat_ui_active:
                if active_quest_data["type"] == "fetch":
                    item_name = active_quest_data['item_to_fetch_key'].replace('_', ' ')
                    self.chat_ui_history.append((quest_giver_npc.name, f"It looks like you still don't have the {active_quest_data['item_fetch_count']} {item_name} I need."))
                elif active_quest_data["type"] == "kill":
                    quest_def = QUEST_DEFINITIONS.get(quest_id, {})
                    remaining = active_quest_data["target_count"] - active_quest_data["progress"]
                    incomplete_dialogue = quest_def.get("dialogue_incomplete_report", f"You still need to defeat {remaining} more.").format(remaining_count=remaining)
                    self.chat_ui_history.append((quest_giver_npc.name, incomplete_dialogue))
    def player_attempt_fish(self, water_x: int, water_y: int):
        """Handles the player's attempt to fish."""
        if not self.player.has_item("fishing_rod"):
            self.add_message_to_chat_log("You need a fishing rod to fish.")
            return

        target_tile = self.get_tile_at(water_x, water_y)
        if not (target_tile and target_tile.name in ["Water", "Deep Water"]):
            self.add_message_to_chat_log("You can't fish there.")
            return

        self.add_message_to_chat_log("You cast your line into the water...")

        if random.random() < 0.3: # 30% chance to catch a fish
            fish_types = ["fish", "salmon", "trout"]
            fish_caught = random.choice(fish_types)
            self.player.add_item(f"raw_{fish_caught}")
            self.add_message_to_chat_log(f"You caught a {fish_caught}!")
        else:
            self.add_message_to_chat_log("You didn't catch anything.")

    def npc_attempt_fish(self, npc, water_x, water_y):
        """Handles an NPC's attempt to fish."""
        target_tile = self.get_tile_at(water_x, water_y)
        if not (target_tile and target_tile.name in ["Water", "Deep Water"]):
            return

        if random.random() < 0.2: # 20% chance for NPC to catch a fish
            fish_types = ["fish", "salmon", "trout"]
            fish_caught = random.choice(fish_types)
            work_building = self.buildings_by_id.get(npc.work_building_id)
            if work_building:
                work_building.building_inventory[f"raw_{fish_caught}"] = work_building.building_inventory.get(f"raw_{fish_caught}", 0) + 1
                self.add_message_to_chat_log(f"{npc.name} caught a {fish_caught}!")

    def player_attempt_till_soil(self, target_x: int, target_y: int):
        """Handles the player's attempt to till soil."""
        hoe_indices = self.player.get_item_instance_indices("stone_hoe")
        if not hoe_indices:
            self.add_message_to_chat_log("You need a hoe to till the soil.")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and target_tile.name == "Plains"):
            self.add_message_to_chat_log("You can only till plains.")
            return

        self.add_message_to_chat_log("You till the soil.")
        tilled_soil_def = TILE_DEFINITIONS["tilled_soil"]
        self._change_map_tile((target_x, target_y), tilled_soil_def)

        # Handle tool durability
        hoe_instance = self.player.get_item_by_index(hoe_indices[0])
        if hoe_instance and "durability" in hoe_instance:
            hoe_instance["durability"] -= 1
            if hoe_instance["durability"] <= 0:
                self.player.remove_item("stone_hoe", 1, specific_instance_index=hoe_indices[0])
                self.add_message_to_chat_log("Your stone hoe broke!")
            else:
                self.add_message_to_chat_log(f"Your stone hoe shows some wear (Durability: {hoe_instance['durability']}/{hoe_instance['max_durability']}).")

    def player_attempt_plant_seeds(self, target_x: int, target_y: int):
        """Handles the player's attempt to plant seeds."""
        if not self.player.has_item("wheat_seeds"):
            self.add_message_to_chat_log("You don't have any seeds to plant.")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and target_tile.name == "Tilled Soil"):
            self.add_message_to_chat_log("You can only plant seeds on tilled soil.")
            return

        self.player.remove_item("wheat_seeds", 1)
        self.add_message_to_chat_log("You plant the seeds.")
        wheat_plant_def = TILE_DEFINITIONS["wheat_plant_growing"]
        self._change_map_tile((target_x, target_y), wheat_plant_def)

    def player_attempt_harvest(self, target_x: int, target_y: int):
        """Handles the player's attempt to harvest a crop."""
        target_tile = self.get_tile_at(target_x, target_y)
        if not (target_tile and hasattr(target_tile, 'properties') and target_tile.properties.get("is_harvestable")):
            self.add_message_to_chat_log("There is nothing to harvest here.")
            return

        self.add_message_to_chat_log("You begin to harvest the crop...")

        if random.random() < 0.8: # 80% chance to successfully harvest
            harvest_yield = target_tile.properties.get("harvest_yield_item_key")
            if harvest_yield:
                self.player.add_item(harvest_yield, 1)
                self.add_message_to_chat_log(f"You harvested one {harvest_yield}.")
                becomes_on_harvest = target_tile.properties.get("becomes_on_harvest_key")
                if becomes_on_harvest and becomes_on_harvest in TILE_DEFINITIONS:
                    revert_tile_def = TILE_DEFINITIONS[becomes_on_harvest]
                    self._change_map_tile((target_x, target_y), revert_tile_def)
                else:
                    # Fallback: turn it back to tilled_soil if key is missing
                    self._change_map_tile((target_x, target_y), TILE_DEFINITIONS["tilled_soil"])
            else:
                 self.add_message_to_chat_log("The crop is not ready to be harvested or yields nothing.")

        else:
            self.add_message_to_chat_log("You failed to harvest the crop.")

    def player_attempt_build(self, recipe_key: str, x: int, y: int):
        """Handles the player's attempt to build a structure or furniture."""
        if recipe_key not in CONSTRUCTION_RECIPES:
            self.add_message_to_chat_log("Unknown construction recipe.")
            return

        recipe = CONSTRUCTION_RECIPES[recipe_key]
        materials = recipe.get("materials", {})

        # Check resources
        for item_key, count in materials.items():
            if not self.player.has_item(item_key, count):
                item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                self.add_message_to_chat_log(f"You need {count} {item_name} to build this.")
                return

        # Validate location
        target_tile = self.get_tile_at(x, y)
        if not target_tile:
            return # Off map

        # Basic checks: prevent building on water or deep water unless it's a bridge (future)
        if target_tile.name in ["Water", "Deep Water"]:
             self.add_message_to_chat_log("You cannot build on water.")
             return

        # Check collision with entities (Player, NPCs, Animals)
        # We don't want to build a wall on top of someone
        for entity in [self.player] + self.npcs + self.village_npcs:
            if entity.x == x and entity.y == y:
                 self.add_message_to_chat_log("You cannot build here; someone is in the way.")
                 return

        # Prevent building on top of existing structures or blocking items if not allowed
        # For tiles (walls/floors), we generally replace the existing tile.
        # For decorations (furniture), we check if passability is required or if it overlaps.

        build_source = recipe.get("source", "decoration")
        tile_def_key = recipe.get("tile_def_key")

        if build_source == "tile":
            new_tile_def = TILE_DEFINITIONS.get(tile_def_key)
        else:
            new_tile_def = DECORATION_ITEM_DEFINITIONS.get(tile_def_key)

        if not new_tile_def:
            self.add_message_to_chat_log("Error: Construction definition not found.")
            return

        # Consume resources
        for item_key, count in materials.items():
            self.player.remove_item(item_key, count)

        # Perform the build
        self._change_map_tile((x, y), new_tile_def)
        self.add_message_to_chat_log(f"You built a {recipe['name']}.")