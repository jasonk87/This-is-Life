# engine.py
import math
import random
import numpy as np
import tcod.noise
import requests # Import requests
import time # Import time for NPC speech timing
from entities.base import NPC
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
)
from data.tiles import TILE_DEFINITIONS, COLORS # For TILE_DEFINITIONS
from tile_types import Tile # For Tile class
from entities.tree import Tree # For isinstance check
from data.items import ITEM_DEFINITIONS # For checking yielded resources
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.prompts import LLM_PROMPTS, OLLAMA_ENDPOINT

import json # Import json for parsing LLM responses
import uuid # For unique building IDs

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
                noise_map[y, x] = self.noise[x * NOISE_SCALE, y * NOISE_SCALE]
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
        if biome == "plains" and random.random() < POI_DENSITY:
            return "village"
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

        # Store global origin of the building (top-left tile)
        self.global_origin_x = global_chunk_x_start + x
        self.global_origin_y = global_chunk_y_start + y

        # Global coordinates of the building's center
        self.global_center_x = self.global_origin_x + width // 2
        self.global_center_y = self.global_origin_y + height // 2

class Village:
    def __init__(self):
        self.buildings = []
        self.lore = "No lore generated yet."
        self.interaction_points = {} # E.g., {"well": [(x1,y1), (x2,y2)], "town_square_center": (x,y)}

    def add_building(self, building: Building):
        self.buildings.append(building)

class Chunk:
    def __init__(self, biome, poi_type=None):
        self.biome = biome
        self.poi_type = poi_type
        self.tiles = None
        self.is_generated = False
        self.village = None # To store Village object if POI is a village



class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.char = ord('@')
        self.color = COLORS["player_fg"]
        self.inventory = {}
        self.max_hp = 30
        self.hp = self.max_hp
        self.reputation = {
            REP_CRIMINAL: INITIAL_CRIMINAL_POINTS,
            REP_HERO: INITIAL_HERO_POINTS,
        }
        self.last_dx = 0 # For facing direction
        self.last_dy = -1 # Default facing up

        # Interaction states
        self.is_sitting = False
        self.is_sleeping = False # Will be more of an instantaneous action for now
        self.original_char = self.char
        self.sitting_on_object_at = None
        self.social_skill = 5
        self.money = 100
        self.active_contracts = {}
        self.pending_contract_offer = None
        self.lockpicking_skill = 3 # Conceptual skill, scale 1-10, default slightly below average

    def take_damage(self, amount: int):
        self.hp -= amount
        if self.hp < 0:
            self.hp = 0

    def adjust_reputation(self, rep_type: str, amount: int):
        """Adjusts the player's reputation of a specific type."""
        if rep_type in self.reputation:
            self.reputation[rep_type] += amount
            # Could add clamping here if REP_MIN/MAX_VALUE were used
            # self.reputation[rep_type] = max(REP_MIN_VALUE, min(self.reputation[rep_type], REP_MAX_VALUE))
            print(f"Player reputation updated: {rep_type} changed by {amount} to {self.reputation[rep_type]}") # For now, print to console
        else:
            print(f"Warning: Tried to adjust unknown reputation type '{rep_type}'")


class World:
    """World class now uses a generator for a more complex map."""
    def __init__(self):
        self.chat_log = [] # Stores chat messages
        self.chunk_width = WORLD_WIDTH // CHUNK_SIZE
        self.chunk_height = WORLD_HEIGHT // CHUNK_SIZE
        self.player = Player(WORLD_WIDTH // 2, WORLD_HEIGHT // 2)
        self.generator = WorldGenerator(self.chunk_width, self.chunk_height)
        self.chunks = self._initialize_chunks()
        self.npcs = []
        self._find_starting_position()
        self.village_npcs = []
        self.buildings_by_id = {}
        self.mouse_x = 0
        self.mouse_y = 0
        self.game_state = "PLAYING"
        self.game_time = 0
        self.last_talked_to_npc = None # Store the NPC targeted by 'T'alk (may be superseded by menu target)

        # Interaction Menu State
        self.interaction_menu_active = False
        self.interaction_menu_options = []
        self.interaction_menu_selected_index = 0
        self.interaction_menu_target_npc = None
        self.interaction_menu_x = 0
        self.interaction_menu_y = 0

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
        Calculates a path from (start_x, start_y) to (end_x, end_y) using A*.
        Returns a list of (x, y) tuples, or an empty list if no path is found.
        The path includes the start point and end point.
        """
        # Ensure start and end are within bounds and passable (optional check, A* might handle it)
        start_tile = self.get_tile_at(start_x, start_y)
        end_tile = self.get_tile_at(end_x, end_y)

        if not (start_tile and start_tile.passable):
            # self.add_message_to_chat_log(f"Pathfinding: Start tile {start_x},{start_y} is not passable.")
            return []
        if not (end_tile and end_tile.passable):
            # self.add_message_to_chat_log(f"Pathfinding: End tile {end_x},{end_y} is not passable.")
            # Allow pathfinding to an impassable tile, character will stop before it.
            pass


        # Initialize AStar with the world dimensions and cost callback
        # The tcod.path.CustomGraph is not strictly needed if using the simple cost callback with AStar directly
        # for a grid, but it's good practice if more complex graph structures arise.
        # For now, we can directly use the AStar with `cost` and `diagonal` parameters.

        # Create a numpy array for pathfinding compatible with tcod.path functions
        # Cost array: 0 for wall, 1 for floor.
        cost = np.ones((WORLD_HEIGHT, WORLD_WIDTH), dtype=np.int8)
        for y in range(WORLD_HEIGHT):
            for x in range(WORLD_WIDTH):
                tile = self.get_tile_at(x,y) # This will generate chunk if not generated.
                if not tile or not tile.passable:
                    cost[y,x] = 0 # Mark as wall/impassable for pathfinder

        astar = tcod.path.AStar(cost=cost, diagonal=1.41) # Allow diagonal movement with cost sqrt(2)

        try:
            path_indices = astar.get_path(start_x, start_y, end_x, end_y)
            # Convert list of [y,x] numpy arrays to list of (x,y) tuples
            path_coords = [(int(p[1]), int(p[0])) for p in path_indices]
            return path_coords
        except IndexError: # tcod can raise this if start/end are identical or other issues
            # self.add_message_to_chat_log(f"Pathfinding error or no path from ({start_x},{start_y}) to ({end_x},{end_y})")
            return []

    def _update_npc_movement(self):
        """Updates the position of NPCs based on their current path."""
        for npc in self.village_npcs: # Later might include self.npcs if they also use this system
            if npc.current_path:
                if not npc.current_destination_coords: # Should not happen if path exists
                    npc.current_path = []
                    continue

                # Path includes the starting point, so if len > 1, there's a next step.
                # If len == 1, it means current_path[0] is the destination itself.
                if len(npc.current_path) > 1:
                    next_x, next_y = npc.current_path[1]

                    next_tile = self.get_tile_at(next_x, next_y)

                    # Check for closed door in path
                    if next_tile and next_tile.properties.get("is_door") and not next_tile.properties.get("is_open"):
                        if self.npc_toggle_door(npc, next_x, next_y):
                            # Door opened successfully. NPC waits a turn (door opening takes their action).
                            # Path remains, they will attempt to move through next turn.
                            # self.add_message_to_chat_log(f"{npc.name} opened a door, will move next turn.")
                            # To make them move immediately, we would not return here, but then pathfinding
                            # might need to be aware of the new passability instantly.
                            # Simpler for now: opening door costs a turn of movement.
                            return # End this NPC's movement update for this turn
                        else:
                            # Failed to open door, path is blocked. Clear path.
                            # self.add_message_to_chat_log(f"{npc.name}'s path blocked by a stuck door at ({next_x},{next_y}). Path cleared.")
                            npc.current_path = []
                            npc.current_destination_coords = None
                            npc.current_task = "idle_confused" # Or try to repath later
                            return

                    # If not a closed door, or door was opened, proceed with movement if tile is passable
                    if next_tile and next_tile.passable:
                        npc.x = next_x
                        npc.y = next_y
                        npc.current_path.pop(0)
                    elif not next_tile or not next_tile.passable:
                        # Path is blocked by something else (not a door they can open)
                        # self.add_message_to_chat_log(f"{npc.name}'s path blocked at ({next_x},{next_y}). Path cleared.")
                        npc.current_path = []
                        npc.current_destination_coords = None
                        npc.current_task = "idle_confused"
                        return
                    # If next_tile was None (out of bounds), this case is also handled by the above.

                                            # Effectively making current_path[1] the new current_path[0]

                    # If only the destination remains in the path after moving
                    if len(npc.current_path) == 1 and (npc.x, npc.y) == npc.current_destination_coords:
                        # self.add_message_to_chat_log(f"{npc.name} reached destination {npc.current_destination_coords} for task {npc.current_task}")
                        npc.current_path = []
                        npc.current_destination_coords = None
                        # Task update will be handled by the scheduler when it sees destination is reached.
                        if npc.current_task == "going to work":
                            npc.current_task = "at work"
                        elif npc.current_task == "going home" or npc.current_task == "going home to sleep" or npc.current_task == "going to bed":
                            npc.current_task = "at home" # Scheduler will handle transition to sleeping if appropriate
                        elif npc.current_task == "fetching water":
                            npc.current_task = "at the well"
                            # NPC will stay "at the well" until scheduler gives a new task (e.g. "going home")
                        else:
                            npc.current_task = "idle"

                elif len(npc.current_path) == 1 and (npc.x, npc.y) == npc.current_path[0] and (npc.x, npc.y) == npc.current_destination_coords :
                    npc.current_path = []
                    npc.current_destination_coords = None
                    # Similar logic for task update on immediate arrival
                    if npc.current_task == "going to work":
                        npc.current_task = "at work"
                    elif npc.current_task == "going home" or npc.current_task == "going home to sleep" or npc.current_task == "going to bed":
                        npc.current_task = "at home"
                    elif npc.current_task == "fetching water":
                        npc.current_task = "at the well"
                    else:
                        npc.current_task = "idle"

                # Safety break if path somehow doesn't lead to destination
                if not npc.current_path and (npc.x, npc.y) != npc.current_destination_coords and npc.current_destination_coords is not None:
                    # self.add_message_to_chat_log(f"Warning: {npc.name} path ended but not at destination {npc.current_destination_coords}. At {(npc.x, npc.y)}")
                    npc.current_destination_coords = None # Clear destination to avoid re-pathing to same failed spot immediately
                    npc.current_task = "idle_confused" # Or some error state

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

    def _update_npc_schedules(self):
        """Periodically updates NPC tasks based on game time and current state."""

        # Using config values now
        # Process NPCs that are due for a schedule update
        for npc in self.village_npcs:
            if self.game_time - npc.game_time_last_updated < NPC_SCHEDULE_UPDATE_INTERVAL:
                continue

            npc.game_time_last_updated = self.game_time

            if npc.current_task in ["idle", "at home", "at work", "idle_confused", "wandering"] and not npc.current_path:
                current_time_in_day = self.game_time % DAY_LENGTH_TICKS
                time_of_day_str = self._get_time_of_day_str(self.game_time, DAY_LENGTH_TICKS)

                new_task_label = None
                llm_chosen_goal = None # e.g. "Go to work"
                destination_coords = None

                # --- Determine NPC's location status ---
                is_at_home = False
                if npc.home_building_id:
                    home_coords = self._get_building_global_center_coords(npc.home_building_id)
                    if home_coords and (npc.x, npc.y) == home_coords:
                        is_at_home = True

                is_at_work = False
                job_type = "Unemployed"
                if npc.work_building_id:
                    work_building = self.buildings_by_id.get(npc.work_building_id)
                    if work_building:
                        job_type = work_building.building_type # Or a more specific job role if defined
                        work_coords = (work_building.global_center_x, work_building.global_center_y)
                        if work_coords and (npc.x, npc.y) == work_coords:
                            is_at_work = True

                # --- LLM-driven Goal Selection ---
                if USE_LLM_FOR_SCHEDULES:
                    prompt = LLM_PROMPTS["npc_daily_goal"].format(
                        npc_name=npc.name,
                        npc_personality=npc.personality,
                        npc_current_task=npc.current_task,
                        is_at_home=is_at_home,
                        is_at_work=is_at_work,
                        has_job=bool(npc.work_building_id),
                        job_type=job_type,
                        time_of_day_str=time_of_day_str
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
                    if llm_chosen_goal == "Go to work" and npc.work_building_id and not is_at_work:
                        dest_coords_temp = self._get_building_global_center_coords(npc.work_building_id)
                        if dest_coords_temp:
                            new_task_label = "going to work"
                            destination_coords = dest_coords_temp
                    elif llm_chosen_goal == "Go home" and npc.home_building_id and not is_at_home:
                        dest_coords_temp = self._get_building_global_center_coords(npc.home_building_id)
                        if dest_coords_temp:
                            new_task_label = "going home"
                            destination_coords = dest_coords_temp
                    elif llm_chosen_goal == "Wander the village":
                        # Pick a random passable point in the current chunk or nearby for simplicity
                        # This needs a robust implementation: find current chunk, pick random point
                        # For now, let's make them stay put if they choose to wander.
                        npc.current_task = "wandering" # No movement, just state change
                        # self.add_message_to_chat_log(f"{npc.name} is now wandering (staying put).")
                    elif llm_chosen_goal == "Stay put":
                        npc.current_task = "idle" if npc.current_task not in ["at home", "at work"] else npc.current_task
                        # self.add_message_to_chat_log(f"{npc.name} is staying put.")
                    # Add other goals like Socialize, Seek food later

                # --- Rule-based Goal Selection (Fallback or if USE_LLM_FOR_SCHEDULES is False) ---
                else:
                    work_start_tick = DAY_LENGTH_TICKS * WORK_START_TIME_RATIO
                    work_end_tick = DAY_LENGTH_TICKS * WORK_END_TIME_RATIO
                    # Define "night" for sleeping (e.g., last 20% of day or first 10%)
                    sleep_start_tick = DAY_LENGTH_TICKS * 0.85
                    sleep_end_tick = DAY_LENGTH_TICKS * 0.15 # Next day
                    is_night_time = current_time_in_day >= sleep_start_tick or current_time_in_day < sleep_end_tick

                    # Priority: Go to work during work hours
                    if work_start_tick <= current_time_in_day < work_end_tick:
                        if npc.work_building_id and not is_at_work and npc.current_task != "going to work":
                            work_building_obj = self.buildings_by_id.get(npc.work_building_id)
                            # Future: Check for specific workstation in work_building_obj.interaction_points
                            # For now, path to building center for work.
                            dest_coords_temp = self._get_building_global_center_coords(npc.work_building_id)
                            if dest_coords_temp:
                                new_task_label = "going to work"
                                destination_coords = dest_coords_temp
                                if hasattr(npc, 'original_char_before_sleep'): npc.char = npc.original_char_before_sleep
                        elif npc.work_building_id and is_at_work:
                             npc.current_task = f"Working ({npc.profession})" if npc.profession != "Unemployed" else "At Work (Idle)"
                             if hasattr(npc, 'original_char_before_sleep'): npc.char = npc.original_char_before_sleep

                    # Else, if it's night and they have a home
                    elif is_night_time and npc.home_building_id and npc.current_task not in ["sleeping", "going home to sleep"]:
                        home_building_obj = self.buildings_by_id.get(npc.home_building_id)
                        if home_building_obj:
                            sleep_spot_coords = home_building_obj.interaction_points.get("sleep_spot")
                            if is_at_home: # Already at home
                                if sleep_spot_coords and (npc.x, npc.y) == sleep_spot_coords: # At the bed
                                    npc.current_task = "sleeping"
                                    npc.original_char_before_sleep = npc.char
                                    npc.char = ord('z')
                                elif sleep_spot_coords and (npc.x, npc.y) != sleep_spot_coords: # At home, but not at bed
                                    new_task_label = "going to bed"
                                    destination_coords = sleep_spot_coords
                                elif not sleep_spot_coords and self._building_contains_item_with_interaction(home_building_obj, "sleep"):
                                    # Fallback if sleep_spot not recorded but bed exists (should not happen if decoration works)
                                    # For now, just mark as sleeping if at home center and bed exists broadly.
                                    npc.current_task = "sleeping"
                                    npc.original_char_before_sleep = npc.char
                                    npc.char = ord('z')
                                # else: npc stays "at home" if no bed / no specific sleep spot
                            else: # Not at home, but it's night -> go to bed if possible, else home center
                                if sleep_spot_coords:
                                    new_task_label = "going home to sleep" # Specific task
                                    destination_coords = sleep_spot_coords
                                else: # No specific bed location, just go to building center
                                    dest_coords_temp = self._get_building_global_center_coords(npc.home_building_id)
                                    if dest_coords_temp:
                                        new_task_label = "going home"
                                        destination_coords = dest_coords_temp

                    # Else (daytime, not work hours, or already finished work), go home (to building center) if not there
                    elif npc.home_building_id and not is_at_home and npc.current_task not in ["going home", "going home to sleep", "sleeping"]:
                        dest_coords_temp = self._get_building_global_center_coords(npc.home_building_id)
                        if dest_coords_temp:
                            new_task_label = "going home"
                            destination_coords = dest_coords_temp

                    # Wake up logic: If sleeping and it's no longer night
                    if npc.current_task == "sleeping" and not is_night_time:
                        npc.current_task = "at home" # Or "idle"
                        if hasattr(npc, 'original_char_before_sleep') and npc.char == ord('z'): # only restore if actually 'z'
                             npc.char = npc.original_char_before_sleep
                        # self.add_message_to_chat_log(f"{npc.name} woke up.")

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
                                    if npc.home_building_id and self.buildings_by_id.get(npc.home_building_id) in chk.village.buildings:
                                        npc_village = chk.village
                                        break
                            if npc_village: break

                        if npc_village and "well" in npc_village.interaction_points and npc_village.interaction_points["well"]:
                            well_coords = random.choice(npc_village.interaction_points["well"]) # Pick one if multiple wells
                            if (npc.x, npc.y) != well_coords:
                                new_task_label = "fetching water"
                                destination_coords = well_coords
                            else:
                                npc.current_task = "at the well" # Already there

                # --- Assign Path if new task and destination found ---
                if new_task_label and destination_coords:
                    # Ensure destination is pathable (or path to nearest passable)
                    # For now, assume center of building is generally inside and thus pathable floor.
                    # Or path to door if we define doors explicitly as entry points.

                    # Check if NPC is already at the destination
                    if (npc.x, npc.y) == destination_coords:
                        if new_task_label == "going to work":
                            npc.current_task = f"Working ({npc.profession})" if npc.profession != "Unemployed" else "At Work (Idle)"
                        elif new_task_label == "going home":
                            npc.current_task = "at home" # Will check for bed next cycle if night
                        else:
                            npc.current_task = "idle"
                    else:
                        path = self.calculate_path(npc.x, npc.y, destination_coords[0], destination_coords[1])
                        if path:
                            npc.current_path = path
                            npc.current_destination_coords = destination_coords
                            npc.current_task = new_task
                            # self.add_message_to_chat_log(f"{npc.name} starting path for task: {new_task} to {destination_coords}. Path length: {len(path)}")
                        else:
                            # self.add_message_to_chat_log(f"Could not find path for {npc.name} for task {new_task} to {destination_coords}")
                            npc.current_task = "idle_confused" # Cannot find path

            # After all task decisions and path assignments:
            if npc.current_task == "at work":
                self._handle_npc_production(npc)

            if npc.current_task != "sleeping" and hasattr(npc, 'original_char_before_sleep') and npc.char == ord('z'):
                if hasattr(npc, 'original_char_before_sleep'): # Ensure it exists before trying to access
                    npc.char = npc.original_char_before_sleep

            npc.game_time_last_updated = self.game_time

    def complete_contract_delivery(self, contract_id: str, turn_in_npc: NPC):
        """Handles player attempting to turn in a contract delivery."""
        if contract_id not in self.player.active_contracts:
            self.add_message_to_chat_log("Error: Contract not found or already completed.")
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                 self.chat_ui_history.append((turn_in_npc.name, "Hmm, I don't recall that arrangement."))
            return

        contract = self.player.active_contracts[contract_id]
        # Ensure this is the correct NPC to turn into, using npc_id stored in contract
        if contract.get("turn_in_npc_id") != turn_in_npc.id: # Check against NPC's actual ID
            self.add_message_to_chat_log("This is not the right person for this delivery.")
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                 self.chat_ui_history.append((turn_in_npc.name, "Are you sure you have that for me?"))
            return

        item_key = contract["item_key"]
        qty_needed = contract["quantity_needed"]
        player_has_qty = self.player.inventory.get(item_key, 0)

        if player_has_qty >= qty_needed:
            self.player.inventory[item_key] = player_has_qty - qty_needed
            if self.player.inventory[item_key] <= 0:
                del self.player.inventory[item_key]

            self.player.money += contract["reward"]
            completion_msg = f"Delivery complete! You gave {qty_needed} {item_key}(s) and received {contract['reward']} money."
            self.add_message_to_chat_log(completion_msg) # Log to main game log

            # Add to chat UI history if chat is active with this NPC
            if self.chat_ui_active and self.chat_ui_target_npc == turn_in_npc:
                self.chat_ui_history.append(("System", completion_msg))
                self.chat_ui_history.append((turn_in_npc.name, f"Excellent work! Here's your {contract['reward']} coins."))
                if len(self.chat_ui_history) > self.chat_ui_max_history:
                    self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]
                self.chat_ui_scroll_offset = 0


            del self.player.active_contracts[contract_id]

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


    def _handle_npc_production(self, npc: NPC):
        """Handles abstract resource production for an NPC at their workplace."""
        # Check if current task is "at work" OR starts with "Working ("
        if not npc.work_building_id or not (npc.current_task == "at work" or npc.current_task.startswith("Working (")):
            return

        work_building = self.buildings_by_id.get(npc.work_building_id)
        if not work_building:
            return

        # Production logic based on profession - simple chance per ~100 ticks
        # This runs every NPC_SCHEDULE_UPDATE_INTERVAL if they are "at work".
        # To make it less frequent, add another modulo check or a dedicated timer.
        # For now, let's assume this is called when NPC is at work.
        # We'll add a random chance to produce to simulate time passing / work being done.

        produced_item_key = None
        produced_quantity = 0
        production_chance = 0.1 # 10% chance each time this is checked while "at work"

        if npc.profession == "Woodcutter" or work_building.building_type == "lumber_mill": # Assuming a lumber_mill type
            if random.random() < production_chance:
                produced_item_key = "log"
                produced_quantity = random.randint(1, 3)
        elif npc.profession == "Farmer" or work_building.building_type == "farm": # Assuming a farm type
             if random.random() < production_chance:
                produced_item_key = "wheat"
                produced_quantity = random.randint(2, 5)
        elif npc.profession == "Miner" or work_building.building_type == "mine": # Assuming a mine type
             if random.random() < production_chance:
                produced_item_key = "iron_ore" # Could also be stone_chunk
                produced_quantity = random.randint(1, 2)

        if produced_item_key and produced_quantity > 0:
            current_qty = work_building.building_inventory.get(produced_item_key, 0)
            work_building.building_inventory[produced_item_key] = current_qty + produced_quantity
            # self.add_message_to_chat_log(
            #     f"{npc.name} ({npc.profession}) produced {produced_quantity} {ITEM_DEFINITIONS[produced_item_key]['name']} "
            #     f"at {work_building.building_type}."
            # ) # This can be very spammy, enable for debug


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

    def player_attempt_chop_tree(self, tree_x: int, tree_y: int):
        """Handles the player's attempt to chop a tree at the given world coordinates."""
        # Check if player has an axe
        # For now, let's assume "axe_stone" is the only axe type.
        # A more robust system would check for any item with property "tool_type": "axe".
        if "axe_stone" not in self.player.inventory or self.player.inventory["axe_stone"] <= 0:
            self.add_message_to_chat_log("You need an axe to chop trees.")
            return

        target_tile = self.get_tile_at(tree_x, tree_y)

        if isinstance(target_tile, Tree) and target_tile.is_choppable:
            yielded_resources = target_tile.chop() # This method also changes the tree's appearance/state

            if yielded_resources:
                self.add_message_to_chat_log(f"You chopped the {target_tile.original_name}!")
                for resource_key, quantity in yielded_resources.items():
                    if resource_key in ITEM_DEFINITIONS: # Only add defined items
                        current_qty = self.player.inventory.get(resource_key, 0)
                        self.player.inventory[resource_key] = current_qty + quantity
                        self.add_message_to_chat_log(f"  + {quantity} {ITEM_DEFINITIONS[resource_key]['name']}")
                    else:
                        self.add_message_to_chat_log(f"  (Received undefined resource: {resource_key} x{quantity})")

                # The tile itself (Tree object) has changed its char/color.
                # No need to replace it in the self.chunks[...].tiles array if it's the same object.
                # If chop() returned a new Stump Tile object, we would need to update the map:
                # chunk_x, chunk_y = tree_x // CHUNK_SIZE, tree_y // CHUNK_SIZE
                # local_x, local_y = tree_x % CHUNK_SIZE, tree_y % CHUNK_SIZE
                # self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = new_stump_tile
            else:
                self.add_message_to_chat_log("Nothing was yielded from the tree.") # Should not happen if is_choppable was true
        elif isinstance(target_tile, Tree) and not target_tile.is_choppable:
            self.add_message_to_chat_log(f"This {target_tile.name} has already been chopped.")
        else:
            self.add_message_to_chat_log("There's nothing to chop there.")


    def add_message_to_chat_log(self, message: str):
        self.chat_log.append(message)
        # Keep chat log to a reasonable size
        if len(self.chat_log) > 100:
            self.chat_log.pop(0)

    def player_attempt_sit(self, target_x: int, target_y: int):
        """Handles the player's attempt to sit on an object."""
        if self.player.is_sitting:
            # If already sitting and trying to interact with the same spot, stand up.
            if self.player.sitting_on_object_at == (target_x, target_y):
                self.player_attempt_stand_up()
            else:
                self.add_message_to_chat_log("You are already sitting. Stand up first ('E' or move).")
            return

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and hasattr(target_tile, 'properties'):
            interaction_hint = target_tile.properties.get("interaction_hint")
            if interaction_hint == "sit":
                self.player.is_sitting = True
                self.player.char = ord('s') # Example sitting character
                self.player.sitting_on_object_at = (target_x, target_y)
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
        if self.player.is_sitting:
            self.player.is_sitting = False
            self.player.char = self.player.original_char
            self.add_message_to_chat_log("You stand up.")
            self.player.sitting_on_object_at = None
        # No message if not sitting, or handled by caller

    def player_attempt_sleep(self, target_x: int, target_y: int):
        """Handles the player's attempt to sleep in a bed."""
        if self.player.is_sitting:
            self.add_message_to_chat_log("You should stand up before trying to sleep.")
            return False

        target_tile = self.get_tile_at(target_x, target_y)
        if target_tile and hasattr(target_tile, 'properties'):
            interaction_hint = target_tile.properties.get("interaction_hint")
            if interaction_hint == "sleep":
                self.add_message_to_chat_log(f"You lie down on the {target_tile.name} to rest.")
                self.player.is_sleeping = True # Brief state change

                # --- Advance Game Time (Simplified) ---
                # For a more complex simulation, this would involve a loop calling NPC updates.
                # For now, a simple jump. NPCs will "catch up" on their next schedule check.
                time_to_advance = DAY_LENGTH_TICKS // 3 # Sleep for 1/3 of a day (e.g., 8 hours)
                self.game_time += time_to_advance
                self.add_message_to_chat_log(f"Several hours pass...")

                # Optional: Player benefits
                heal_amount = self.player.max_hp // 4 # Heal 25% of max HP
                self.player.hp = min(self.player.max_hp, self.player.hp + heal_amount)
                if heal_amount > 0:
                     self.add_message_to_chat_log(f"You feel somewhat rested and heal for {heal_amount} HP.")
                else:
                    self.add_message_to_chat_log("You feel somewhat rested.")

                self.player.is_sleeping = False # Player wakes up
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

        player_rep = self.player.reputation
        prompt = LLM_PROMPTS["npc_persuasion_check"].format(
            npc_name=npc_target.name,
            npc_personality=npc_target.personality,
            npc_attitude=npc_target.attitude_to_player,
            player_social_skill=self.player.social_skill,
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
            error_msg = f"{npc_target.name} gives a non-committal grunt. (LLM response format error)"
            self.chat_ui_history.append(("System", error_msg))
            # self.add_message_to_chat_log(f"LLM Raw: {response_str}") # Log raw for debugging if needed

    def player_attempt_attack(self, target_npc: NPC):
        if not target_npc:
            self.add_message_to_chat_log("No target selected for attack.")
            return

        if target_npc.is_dead:
            self.add_message_to_chat_log(f"{target_npc.name} is already defeated.")
            return

        player_weapon_name = "Fists"
        if self.player.inventory.get("axe_stone", 0) > 0:
            player_weapon_name = ITEM_DEFINITIONS["axe_stone"]["name"]

        player_melee_skill = getattr(self.player, 'melee_skill', 5)

        prompt = LLM_PROMPTS["adjudicate_player_attack"].format(
            player_weapon_name=player_weapon_name,
            player_melee_skill=player_melee_skill,
            npc_name=target_npc.name,
            npc_toughness=target_npc.toughness
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

            if hit and damage_dealt > 0:
                target_npc.take_damage(damage_dealt, self)
                if target_npc.is_dead:
                    self.handle_npc_death(target_npc)
            elif hit and damage_dealt <= 0: # A hit that does no damage
                self.add_message_to_chat_log(f"Your attack hits but glances off {target_npc.name} harmlessly!")

            # Ensure NPC becomes hostile if attacked and not already dead/hostile
            # (take_damage also sets hostility, this is a fallback if no damage but was a hostile act)
            if not target_npc.is_hostile_to_player and not target_npc.is_dead:
                 target_npc.is_hostile_to_player = True
                 self.add_message_to_chat_log(f"{target_npc.name} becomes hostile!")

        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"The outcome of your attack is unclear. (LLM Format Error: {response_str})")
            if not target_npc.is_hostile_to_player and not target_npc.is_dead: # Still make hostile on error
                target_npc.is_hostile_to_player = True; self.add_message_to_chat_log(f"{target_npc.name} is angered by your confusing actions!")
        except ValueError: # For int(damage_dealt)
            self.add_message_to_chat_log(f"The LLM provided an invalid damage amount: {response_json.get('damage_dealt') if 'response_json' in locals() else 'Unknown'}")
            if not target_npc.is_hostile_to_player and not target_npc.is_dead:
                target_npc.is_hostile_to_player = True; self.add_message_to_chat_log(f"{target_npc.name} is angered by your confusing actions!")

    def handle_npc_death(self, dead_npc: NPC):
        self.add_message_to_chat_log(f"{dead_npc.name} has died!")

        npc_chunk_x, npc_chunk_y = dead_npc.x // CHUNK_SIZE, dead_npc.y // CHUNK_SIZE
        npc_local_x, npc_local_y = dead_npc.x % CHUNK_SIZE, dead_npc.y % CHUNK_SIZE

        corpse_placed_on_map = False
        if 0 <= npc_chunk_x < self.chunk_width and 0 <= npc_chunk_y < self.chunk_height:
            chunk = self.chunks[npc_chunk_y][npc_chunk_x]
            if chunk and chunk.tiles:
                corpse_def = DECORATION_ITEM_DEFINITIONS.get("corpse_humanoid")
                if corpse_def:
                    chunk.tiles[npc_local_y][npc_local_x] = Tile(
                        char=corpse_def["char"], color=corpse_def["color"],
                        passable=corpse_def["passable"], name=corpse_def["name"],
                        properties=corpse_def.get("properties", {})
                    )
                    corpse_placed_on_map = True

        if not corpse_placed_on_map: self.add_message_to_chat_log(f"(Could not place corpse for {dead_npc.name} on map)")

        self.village_npcs = [npc for npc in self.village_npcs if npc.id != dead_npc.id]
        self.npcs = [npc for npc in self.npcs if npc.id != dead_npc.id]

        for building_obj in self.buildings_by_id.values():
            building_obj.residents = [res for res in building_obj.residents if res.id != dead_npc.id]
            building_obj.occupants = [occ for occ in building_obj.occupants if occ.id != dead_npc.id]

        # Clear NPC from UI states if they were targeted
        if self.interaction_menu_target_npc == dead_npc: self.interaction_menu_target_npc, self.interaction_menu_active = None, False
        if self.chat_ui_target_npc == dead_npc: self.chat_ui_target_npc, self.chat_ui_active = None, False # Main loop should handle context.stop_text_input()
        if self.trade_ui_npc_target == dead_npc: self.trade_ui_npc_target, self.trade_ui_active = None, False
        if self.last_talked_to_npc == dead_npc: self.last_talked_to_npc = None


    def player_attempt_pick_lock(self, target_x: int, target_y: int) -> bool:
        """Handles player's attempt to pick a lock."""
        if self.player.inventory.get("lockpick", 0) <= 0:
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
            player_lockpicking_skill=self.player.lockpicking_skill,
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
                self.player.inventory["lockpick"] -= 1
                self.add_message_to_chat_log("Your lockpick broke!")
                if self.player.inventory["lockpick"] <= 0:
                    del self.player.inventory["lockpick"]
                    self.add_message_to_chat_log("That was your last lockpick.")

            if success:
                target_tile.properties["is_locked"] = False
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

        # Player inventory snapshot: (item_key, quantity, price_to_sell_at)
        for item_key, quantity in self.player.inventory.items():
            item_def = ITEM_DEFINITIONS.get(item_key)
            if item_def:
                # Simple pricing: sell at base value (or slightly less)
                price = item_def.get("value", 0)
                self.trade_ui_player_inventory_snapshot.append((item_key, quantity, price))

        # Merchant inventory snapshot: (item_key, quantity, price_to_buy_at)
        # Merchant inventory is likely in their work building
        merchant_inventory_source = {}
        merchant_building = self.buildings_by_id.get(self.trade_ui_npc_target.work_building_id)
        if merchant_building and merchant_building.building_type == "general_store":
            merchant_inventory_source = merchant_building.building_inventory
        else: # Fallback to NPC's personal inventory if no store or not a store
            merchant_inventory_source = self.trade_ui_npc_target.npc_inventory

        for item_key, quantity in merchant_inventory_source.items():
            if item_key == "money": continue # Don't list merchant's money as a sellable item
            item_def = ITEM_DEFINITIONS.get(item_key)
            if item_def:
                # Simple pricing: buy at base value (or slightly more)
                price = item_def.get("value", 0)
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

        # Determine merchant's actual inventory (store or personal)
        merchant_true_inventory = {}
        if merchant_building and merchant_building.building_type == "general_store":
            merchant_true_inventory = merchant_building.building_inventory
        else:
            merchant_true_inventory = merchant_npc.npc_inventory

        merchant_money = merchant_true_inventory.get("money", 0)

        if self.trade_ui_player_selling: # Player is selling
            if not self.trade_ui_player_inventory_snapshot: return
            item_key, quantity, price = self.trade_ui_player_inventory_snapshot[self.trade_ui_player_item_index]

            if self.player.inventory.get(item_key, 0) > 0:
                if merchant_money >= price:
                    # Player sells 1 unit of the item
                    self.player.inventory[item_key] -= 1
                    if self.player.inventory[item_key] <= 0:
                        del self.player.inventory[item_key]
                    self.player.money += price

                    merchant_true_inventory[item_key] = merchant_true_inventory.get(item_key, 0) + 1
                    merchant_true_inventory["money"] = merchant_money - price
                    self.add_message_to_chat_log(f"You sold 1 {ITEM_DEFINITIONS[item_key]['name']} for {price} money.")
                else:
                    self.add_message_to_chat_log(f"{merchant_npc.name} doesn't have enough money to buy that.")
            else:
                self.add_message_to_chat_log("Error: You don't have that item to sell (inventory mismatch).")

        else: # Player is buying (viewing merchant's items)
            if not self.trade_ui_merchant_inventory_snapshot: return
            item_key, quantity, price = self.trade_ui_merchant_inventory_snapshot[self.trade_ui_merchant_item_index]

            if merchant_true_inventory.get(item_key, 0) > 0:
                if self.player.money >= price:
                    # Player buys 1 unit
                    merchant_true_inventory[item_key] -= 1
                    if merchant_true_inventory[item_key] <= 0:
                        del merchant_true_inventory[item_key]
                    merchant_true_inventory["money"] = merchant_money + price # Merchant gains money

                    self.player.inventory[item_key] = self.player.inventory.get(item_key, 0) + 1
                    self.player.money -= price
                    self.add_message_to_chat_log(f"You bought 1 {ITEM_DEFINITIONS[item_key]['name']} for {price} money.")
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

        player_rep = self.player.reputation
        prompt = LLM_PROMPTS["npc_conversation_greeting"].format(
            npc_name=npc_target.name,
            npc_personality=npc_target.personality,
            npc_attitude=npc_target.attitude_to_player,
            player_criminal_points=player_rep.get(REP_CRIMINAL, 0),
            player_hero_points=player_rep.get(REP_HERO, 0)
        )
        greeting = self._call_ollama(prompt)
        if not greeting:
            greeting = f"Hello. (LLM failed to provide greeting)"

        self.chat_ui_history.append((npc_target.name, greeting.strip()))

        if len(self.chat_ui_history) > self.chat_ui_max_history:
            self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]

    def continue_npc_dialogue(self, npc_target: NPC, player_input_text: str):
        """Continues dialogue with an NPC based on player input and history."""
        if not npc_target:
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

        player_rep = self.player.reputation
        prompt = LLM_PROMPTS["npc_conversation_continue"].format(
            npc_name=npc_target.name,
            npc_personality=npc_target.personality,
            npc_attitude=npc_target.attitude_to_player,
            player_criminal_points=player_rep.get(REP_CRIMINAL, 0),
            player_hero_points=player_rep.get(REP_HERO, 0),
            conversation_history=history_str,
            player_input=player_input_text
        )

        npc_response = self._call_ollama(prompt)
        if not npc_response:
            npc_response = "... (LLM failed to respond)"

        self.chat_ui_history.append((npc_target.name, npc_response.strip()))

        # After NPC response, check if this NPC should offer a job
        if npc_target.profession == "Lumber Mill Foreman" and f"lumber_delivery_{npc_target.id}" not in self.player.active_contracts:
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
                npc_profession=npc_target.profession,
                npc_personality=npc_target.personality,
                npc_attitude=npc_target.attitude_to_player,
                player_criminal_points=self.player.reputation.get(REP_CRIMINAL,0),
                player_hero_points=self.player.reputation.get(REP_HERO,0),
                quantity_needed=quantity_needed,
                item_name_plural=item_name_plural,
                reward_amount=reward_amount
            )
            job_offer_dialogue = self._call_ollama(offer_prompt)
            if not job_offer_dialogue:
                job_offer_dialogue = f"I might have some work for you... if you're interested. Need {quantity_needed} {item_name_plural} for {reward_amount} coins."

            self.chat_ui_history.append((npc_target.name, job_offer_dialogue.strip()))
            # Store pending offer to be accepted on player's next input if affirmative
            self.player.pending_contract_offer = {
                "contract_id": contract_id, "npc_id": npc_target.id,
                "item_key": item_needed, "quantity_needed": quantity_needed,
                "reward": reward_amount, "npc_offerer_id": npc_target.id # Keep track of who offered
            }
            self.chat_ui_history.append(("System", "The Foreman has offered you a job. Type 'yes' or 'accept' to take it."))


        if len(self.chat_ui_history) > self.chat_ui_max_history:
            self.chat_ui_history = self.chat_ui_history[-self.chat_ui_max_history:]


    def _call_ollama(self, prompt: str) -> str:
        """Makes a request to the Ollama API and returns the response."""
        try:
            response = requests.post(
                OLLAMA_ENDPOINT + "/api/generate",
                json={
                    "model": "llama3.2:latest",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30 # 30 second timeout
            )
            response.raise_for_status() # Raise an exception for HTTP errors
            full_response = response.json()["response"]
            # Attempt to extract JSON from markdown code block
            json_start = full_response.find("```json")
            if json_start != -1:
                json_end = full_response.find("```", json_start + len("```json"))
                if json_end != -1:
                    json_str = full_response[json_start + len("```json"):json_end].strip()
                    try:
                        json.loads(json_str) # Validate JSON
                        return json_str
                    except json.JSONDecodeError:
                        pass # Fall through to try parsing full response

            # If no markdown block or invalid JSON in block, try parsing full response
            try:
                json.loads(full_response) # Validate JSON
                return full_response
            except json.JSONDecodeError:
                return "" # Return empty string if not valid JSON
        except requests.exceptions.RequestException as e:
            print(f"Error communicating with Ollama: {e}")
            return ""

    

    def _populate_npcs(self):
        # Generate NPCs using LLM
        num_npcs = random.randint(1, 3) # Example: 1 to 3 NPCs per world
        for _ in range(num_npcs):
            prompt = LLM_PROMPTS["npc_personality"]
            llm_response = self._call_ollama(prompt)
            try:
                npc_data = json.loads(llm_response)
                # Place NPC near player for now, will improve placement later
                npc_x = self.player.x + random.randint(-5, 5)
                npc_y = self.player.y + random.randint(-5, 5)
                self.npcs.append(NPC(
                    x=npc_x,
                    y=npc_y,
                    name=npc_data.get("name", "NPC"),
                    dialogue=npc_data.get("dialogue", ["Hello!"]),
                    personality=npc_data.get("personality", "normal"),
                    family_ties=npc_data.get("family_ties", "none"),
                    attitude_to_player=npc_data.get("attitude_to_player", "indifferent")
                ))
                self.add_message_to_chat_log(f"Generated NPC: {npc_data.get("name", "NPC")}")
            except json.JSONDecodeError as e:
                self.add_message_to_chat_log(f"Error parsing LLM response for NPC: {e}")
                self.add_message_to_chat_log(f"LLM Response: {llm_response}")

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
            # Fetch player reputation to pass to the prompt
            player_rep = self.player.reputation
            prompt = LLM_PROMPTS["npc_personality"].format(
                player_criminal_points=player_rep.get(REP_CRIMINAL, 0),
                player_hero_points=player_rep.get(REP_HERO, 0),
                # Potentially add name_hint, personality_hint etc. if we want more specific NPC roles
                name_hint="", personality_hint="", family_ties_hint="", attitude_to_player_hint=""
            )
            llm_response = self._call_ollama(prompt)
            try:
                npc_data = json.loads(llm_response)

                # Assign home
                if not available_homes:
                    # self.add_message_to_chat_log("Warning: No available homes for new NPC.")
                    # Create NPC without a home, or handle differently
                    home_building = None
                else:
                    home_building = available_homes.pop(0)
                    # Place NPC at the global center of their home building
                    npc_x = home_building.global_center_x
                    npc_y = home_building.global_center_y

                    # Ensure NPC is within world bounds (still good practice)
                    npc_x = max(0, min(WORLD_WIDTH - 1, npc_x))
                    npc_y = max(0, min(WORLD_HEIGHT - 1, npc_y))
                else:
                    self.add_message_to_chat_log(f"Skipping NPC generation for {npc_data.get('name', 'Unknown')} due to no available home.")
                    continue # Skip this NPC if no home can be assigned

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
                    attitude_to_player=npc_data.get("attitude_to_player", "neutral")
                )

                # Assign wealth (randomly for now)
                npc.wealth_level = random.choice(["poor", "average", "wealthy"])

                # Assign profession based on work building
                if work_building:
                    npc.work_building_id = work_building.id
                    work_building.occupants.append(npc) # Store NPC object for now
                    # Simple profession mapping
                    if work_building.building_type == "sheriff_office":
                        npc.profession = "Sheriff"
                    elif work_building.building_type == "capital_hall":
                        npc.profession = "Town Official"
                    elif work_building.building_type == "general_store" or \
                         "shop" in work_building.building_type or \
                         "market" in work_building.building_type:
                        npc.profession = "Merchant"
                    elif work_building.building_type == "lumber_mill":
                        # Could have multiple roles at a lumber mill, e.g. Foreman and Woodcutter
                        # For now, let's make the first NPC assigned to a lumber_mill the "Foreman" (quest giver)
                        # and subsequent ones "Woodcutter" (producer). This is a simple heuristic.
                        is_foreman_assigned_to_mill = any(
                            other_npc.profession == "Lumber Mill Foreman" and other_npc.work_building_id == work_building.id
                            for other_npc in self.village_npcs + self.npcs # Check all existing npcs
                        )
                        if not is_foreman_assigned_to_mill:
                            npc.profession = "Lumber Mill Foreman"
                        else:
                            npc.profession = "Woodcutter"
                    elif work_building.building_type == "farm": # Assuming farm type from production step
                         npc.profession = "Farmer"
                    elif work_building.building_type == "mine": # Assuming mine type
                         npc.profession = "Miner"
                    else:
                        npc.profession = work_building.building_type.replace("_", " ").title()
                else:
                    npc.profession = "Unemployed"

                # If NPC is a Merchant and assigned to a general store, pre-populate store inventory
                if npc.profession == "Merchant" and work_building and work_building.building_type == "general_store":
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

                self.village_npcs.append(npc)
                self.add_message_to_chat_log(
                    f"Generated Villager: {npc.name} (Wealth: {npc.wealth_level}, Prof: {npc.profession}). "
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
        player_rep = self.player.reputation # Get player rep once
        for npc in self.npcs + self.village_npcs:
            if current_time - npc.last_speech_time > random.randint(10, 30):
                # Ambient speech might be general, or react to player if nearby and reputation is notable
                prompt = (
                    f"NPC {npc.name} (Personality: {npc.personality}, Attitude to Player: {npc.attitude_to_player}, Family: {npc.family_ties}) "
                    f"is going about their day. The player's reputation is: "
                    f"Criminal Points: {player_rep.get(REP_CRIMINAL, 0)}, Hero Points: {player_rep.get(REP_HERO, 0)}. "
                    f"Generate a short, in-character ambient thought or statement from {npc.name}. "
                    f"It could be about their current (unspecified) activity, the village, a general thought, "
                    f"or a comment related to the player if their reputation is particularly high or low and the player is assumed to be generally known or nearby. "
                    f"Keep it concise."
                )
                llm_dialogue = self._call_ollama(prompt)
                if llm_dialogue:
                    self.add_message_to_chat_log(f"{npc.name}: {llm_dialogue}")
                    npc.last_speech_time = current_time

    def decorate_building_interior(self, building: Building, chunk: Chunk): # Added chunk to access village lore
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
                    f"Personality: {resident_npc.personality}, "
                    f"Wealth: {resident_npc.wealth_level}, "
                    f"Profession: {resident_npc.profession}."
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
            decoration_data = json.loads(llm_response)
            for item in decoration_data.get("decorations", []):
                item_type = item.get("type")
                item_x = item.get("x")
                item_y = item.get("y")

                if item_type and item_x is not None and item_y is not None:
                    # Ensure item is within building bounds
                    if 0 <= item_x < building.width and 0 <= item_y < building.height:
                        global_x = (building.x // CHUNK_SIZE * CHUNK_SIZE) + building.x + item_x
                        global_y = (building.y // CHUNK_SIZE * CHUNK_SIZE) + building.y + item_y

                        # Get the tile definition for the decoration item
                        decoration_tile_def = DECORATION_ITEM_DEFINITIONS.get(item_type)
                        if decoration_tile_def:
                            # Apply the decoration to the tile
                            # global_x, global_y are the world coordinates of the item.
                            # building.x, building.y are the building's origin, local to its chunk.
                            # item_x, item_y are the item's origin, local to the building.
                            
                            # The tile we want to change is in `chunk.tiles`
                            # Its local-to-chunk coordinates are:
                            tile_in_chunk_x = building.x + item_x
                            tile_in_chunk_y = building.y + item_y

                            # Ensure these are valid chunk tile coordinates
                            if 0 <= tile_in_chunk_x < CHUNK_SIZE and 0 <= tile_in_chunk_y < CHUNK_SIZE:
                                chunk.tiles[tile_in_chunk_y][tile_in_chunk_x] = Tile(
                                    char=decoration_tile_def["char"],
                                    color=decoration_tile_def["color"],
                                    passable=decoration_tile_def["passable"],
                                    name=decoration_tile_def.get("name", item_type),
                                    properties=decoration_tile_def.get("properties", {})
                                )
                                # print(f"Placed {item_type} at G({global_x},{global_y}), local_to_chunk({tile_in_chunk_x},{tile_in_chunk_y})")

                                # Store interaction points using their GLOBAL world coordinates
                                interaction_hint = decoration_tile_def.get("properties", {}).get("interaction_hint")
                                if interaction_hint == "sleep": # This is for beds
                                    if "sleep_spot" not in building.interaction_points: # Store first one found
                                        building.interaction_points["sleep_spot"] = (global_x, global_y)
                                        # self.add_message_to_chat_log(f"Bed ('sleep_spot') recorded for building {building.id[:6]} at G({global_x},{global_y})")
                                # Add other interaction points like "cook_spot", "craft_spot" here later
                            else:
                                print(f"Error: Calculated tile coords ({tile_in_chunk_x},{tile_in_chunk_y}) for item '{item_type}' are out of chunk bounds.")
                        else:
                            print(f"Unknown decoration item type: {item_type}")
                    else:
                        print(f"Decoration item {item_type} out of bounds for building at ({building.x}, {building.y})")
        except json.JSONDecodeError as e:
            print(f"Error parsing LLM response for interior decoration: {e}")
            print(f"LLM Response: {llm_response}")

        building.interior_decorated = True

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
            player_rep = self.player.reputation
            prompt = (
                f"The player (Criminal Points: {player_rep.get(REP_CRIMINAL, 0)}, Hero Points: {player_rep.get(REP_HERO, 0)}) "
                f"approaches {closest_npc.name}. "
                f"{closest_npc.name} is {closest_npc.personality}, their family ties are '{closest_npc.family_ties}', "
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
        """Finds a suitable starting tile for the player, searching from the center."""
        center_x, center_y = self.player.x, self.player.y
        if self.get_tile_at(center_x, center_y) and self.get_tile_at(center_x, center_y).passable:
            return

        # First, try to find a plains tile
        for r in range(1, max(WORLD_WIDTH, WORLD_HEIGHT) // 2):
            for x_offset in range(-r, r + 1):
                for y_sign in [-1, 1]:
                    tx, ty = center_x + x_offset, center_y + (r * y_sign)
                    chunk_x, chunk_y = tx // CHUNK_SIZE, ty // CHUNK_SIZE
                    if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
                        chunk = self.chunks[chunk_y][chunk_x]
                        if chunk.biome == "plains":
                            tile = self.get_tile_at(tx, ty)
                            if tile and tile.passable:
                                self.player.x, self.player.y = tx, ty
                                return
            for y_offset in range(-r + 1, r):
                for x_sign in [-1, 1]:
                    tx, ty = center_x + (r * x_sign), center_y + y_offset
                    chunk_x, chunk_y = tx // CHUNK_SIZE, ty // CHUNK_SIZE
                    if 0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height:
                        chunk = self.chunks[chunk_y][chunk_x]
                        if chunk.biome == "plains":
                            tile = self.get_tile_at(tx, ty)
                            if tile and tile.passable:
                                self.player.x, self.player.y = tx, ty
                                return

        # If no plains tile found, search for any passable tile
        for r in range(1, max(WORLD_WIDTH, WORLD_HEIGHT) // 2):
            # Check top and bottom rows of the expanding search box
            for x_offset in range(-r, r + 1):
                for y_sign in [-1, 1]:
                    tx, ty = center_x + x_offset, center_y + (r * y_sign)
                    tile = self.get_tile_at(tx, ty)
                    if tile and tile.passable:
                        self.player.x, self.player.y = tx, ty
                        return
            # Check left and right columns
            for y_offset in range(-r + 1, r):
                for x_sign in [-1, 1]:
                    tx, ty = center_x + (r * x_sign), center_y + y_offset
                    tile = self.get_tile_at(tx, ty)
                    if tile and tile.passable:
                        self.player.x, self.player.y = tx, ty
                        return
        print("Warning: No passable starting tile found. Player may be stuck.")

    def _generate_chunk_detail(self, chunk: Chunk, chunk_coord_x: int, chunk_coord_y: int):
        """Generates the detailed tiles for a chunk based on its biome and POI."""
        if chunk.is_generated: return

        if chunk.poi_type == "village":
            chunk.village = Village()
            # Generate village lore
            prompt = LLM_PROMPTS["village_lore"]
            lore_response = self._call_ollama(prompt)
            if lore_response:
                chunk.village.lore = lore_response.strip()
                # self.add_message_to_chat_log(f"Village Lore for {chunk_coord_x},{chunk_coord_y}: {chunk.village.lore[:50]}...") # Log snippet
            else:
                chunk.village.lore = "The mists of time have obscured this village's history." # Fallback
            
            tiles = self._generate_village_layout(chunk, chunk_coord_x, chunk_coord_y)
        else:
            # Generate the base biome tiles
            biome_def = TILE_DEFINITIONS[chunk.biome]
            tiles = [[Tile(biome_def["char"], biome_def["color"], biome_def["passable"], biome_def["name"], properties={}) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

            # If the biome is plains, add some detail
            if chunk.biome == "plains":
                for y_local in range(CHUNK_SIZE):
                    for x_local in range(CHUNK_SIZE):
                        # Add patches of tall grass
                        if random.random() < 0.15: # 15% chance
                            tiles[y_local][x_local] = Tile(TILE_DEFINITIONS["tall_grass"]["char"], TILE_DEFINITIONS["tall_grass"]["color"], TILE_DEFINITIONS["tall_grass"]["passable"], TILE_DEFINITIONS["tall_grass"]["name"])
                        # Add sparse flowers
                        elif random.random() < 0.01: # 1% chance
                            tiles[y_local][x_local] = Tile(TILE_DEFINITIONS["flower"]["char"], TILE_DEFINITIONS["flower"]["color"], TILE_DEFINITIONS["flower"]["passable"], TILE_DEFINITIONS["flower"]["name"])
        chunk.tiles = tiles
        chunk.is_generated = True

    def _generate_trees(self, tiles): # This function seems unused after recent changes, consider removing or integrating.
        for y_local in range(CHUNK_SIZE):
            for x_local in range(CHUNK_SIZE):
                if random.random() < 0.02: # 2% chance for a tree
                    tree_type = random.choice(["oak", "apple", "pear"])
                    # Tree classes like OakTree are not fully defined in provided snippets, assuming they exist or are simple.
                    # For now, this part might not function as expected without full Tree entity definitions.
                    # Placeholder:
                    # tiles[y_local][x_local] = Tile(TILE_DEFINITIONS["tree"]["char"], ...) # Assuming a generic tree tile
                    pass # Pass for now as Tree entities are not the focus

    def _generate_village_layout(self, chunk: Chunk, chunk_coord_x: int, chunk_coord_y: int):
        tiles = [[Tile(TILE_DEFINITIONS["plains"]["char"], TILE_DEFINITIONS["plains"]["color"], TILE_DEFINITIONS["plains"]["passable"], TILE_DEFINITIONS["plains"]["name"]) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

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
        chunk.village.add_building(general_store)
        self.buildings_by_id[general_store.id] = general_store
        self._draw_building(tiles, general_store, "wood_wall")

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
        chunk.village.add_building(lumber_mill)
        self.buildings_by_id[lumber_mill.id] = lumber_mill
        self._draw_building(tiles, lumber_mill, "wood_wall") # Using wood_wall for now


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

        self._populate_village_npcs(chunk, chunk.village, chunk_coord_x, chunk_coord_y)
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

    def handle_player_movement(self, dx, dy):
        if self.player.is_sitting:
            self.player_attempt_stand_up()
            # self.add_message_to_chat_log("You stand up to move.") # Optional message
            return # Prevent movement in the same turn as standing up from a move key

        new_x, new_y = self.player.x + dx, self.player.y + dy
        destination_tile = self.get_tile_at(new_x, new_y)

        if destination_tile and destination_tile.passable:
            self.player.x, self.player.y = new_x, new_y
            self.player.last_dx, self.player.last_dy = dx, dy # Store last move

            # Check if player entered a building
            building = self.get_building_at(new_x, new_y)
            if building and not building.interior_decorated:
                # Get the chunk the building is in to pass to decoration method
                current_chunk_x = new_x // CHUNK_SIZE
                current_chunk_y = new_y // CHUNK_SIZE
                if 0 <= current_chunk_x < self.chunk_width and 0 <= current_chunk_y < self.chunk_height:
                    chunk_of_building = self.chunks[current_chunk_y][current_chunk_x]
                    self.decorate_building_interior(building, chunk_of_building)
                else:
                    # This should ideally not happen if get_building_at found a building
                    self.add_message_to_chat_log("Error: Could not find chunk for building decoration.")


            # Check if the player moved onto a flower
            if destination_tile.char == ord('*'):
                # Add a flower to the player's inventory
                current_flowers = self.player.inventory.get("flower", 0)
                self.player.inventory["flower"] = current_flowers + 1
                
                print(f"You picked a flower! You now have {self.player.inventory['flower']} flowers.")
                
                # Replace the flower tile with a plains tile
                chunk_x, chunk_y = new_x // CHUNK_SIZE, new_y // CHUNK_SIZE
                local_x, local_y = new_x % CHUNK_SIZE, new_y % CHUNK_SIZE
                self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(TILE_DEFINITIONS["plains"]["char"], TILE_DEFINITIONS["plains"]["color"], TILE_DEFINITIONS["plains"]["passable"], TILE_DEFINITIONS["plains"]["name"])

    def craft_item(self, item_key: str):
        """Crafts an item if the player has the required resources."""
        if item_key not in ITEM_DEFINITIONS:
            print(f"You don't know how to craft '{item_key}'.")
            return

        recipe = ITEM_DEFINITIONS[item_key].get("crafting_recipe", {})
        can_craft = True
        for resource, required_qty in recipe.items():
            if self.player.inventory.get(resource, 0) < required_qty:
                print(f"You don't have enough {resource} to craft that. (Need {required_qty})")
                can_craft = False
                break

        if can_craft:
            # Consume resources
            for resource, required_qty in recipe.items():
                self.player.inventory[resource] -= required_qty
                if self.player.inventory[resource] <= 0:
                    del self.player.inventory[resource]

            # Add crafted item
            self.player.inventory[item_key] = self.player.inventory.get(item_key, 0) + 1
            print(f"You crafted a {ITEM_DEFINITIONS[item_key]['name']}!")

    def use_item(self, item_key: str):
        """Uses an item from the player's inventory."""
        if self.player.inventory.get(item_key, 0) > 0:
            item_def = ITEM_DEFINITIONS.get(item_key)
            if not item_def or "on_use" not in item_def:
                print(f"You can't use the {item_key}.")
                return

            # Handle healing
            heal_amount = item_def["on_use"].get("heal_amount")
            if heal_amount:
                if self.player.hp >= self.player.max_hp:
                    print("You are already at full health!")
                else:
                    self.player.hp = min(self.player.max_hp, self.player.hp + heal_amount)
                    self.player.inventory[item_key] -= 1
                    if self.player.inventory[item_key] <= 0:
                        del self.player.inventory[item_key]
                    print(f"You used a {item_def['name']} and healed {heal_amount} HP. Current HP: {self.player.hp}")
            else:
                print(f"You can't use the {item_key} in that way.")
        else:
            print(f"You don't have any {item_def['name']} to use.")