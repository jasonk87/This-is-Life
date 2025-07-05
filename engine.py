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
    # FOV and Light Level Configs
    DAY_LENGTH_TICKS, LIGHT_LEVEL_PERIODS,
    FOV_RADIUS_DAY, FOV_RADIUS_DUSK_DAWN, FOV_RADIUS_NIGHT, FOV_RADIUS_PITCH_BLACK,
    # Auditory Perception Configs
    DEFAULT_HEARING_RADIUS, DEFAULT_SPEECH_VOLUME
)
from data.tiles import TILE_DEFINITIONS, COLORS # For TILE_DEFINITIONS
from tile_types import Tile # For Tile class
from entities.tree import Tree # For isinstance check
from data.items import ITEM_DEFINITIONS # For checking yielded resources
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.prompts import LLM_PROMPTS, OLLAMA_ENDPOINT
from data.professions import PROFESSIONS, get_profession_data, get_sub_task_data # Profession and sub-task data

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
        # Work zones: keys are zone_tags (e.g., "log_pile_area"), values are lists of global (x,y) coordinates
        self.work_zone_tiles: dict[str, list[tuple[int, int]]] = {}

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
        self.id = id(self) # Simple unique ID for player

        # Light Source State
        self.equipped_light_item_key: str | None = None # e.g., "torch_lit"
        self.hearing_radius: int = DEFAULT_HEARING_RADIUS # Auditory perception
        self.light_source_active_until_tick: int = -1   # Game tick for burnout, -1 if no duration/not active
        self.current_personal_light_radius: int = 0     # Actual radius from equipped item

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

        # Items on the ground
        self.items_on_map: dict[tuple[int, int], list[dict]] = {} # Key: (x,y), Value: list of {"item_key": str, "quantity": int}

        # FOV and Light Level state
        self.current_light_level_name = "DAY" # Default
        self.current_fov_radius = FOV_RADIUS_DAY # Default

        # Initialize FOV related maps
        self.player_fov_map = np.full((WORLD_WIDTH, WORLD_HEIGHT), fill_value=False, order="F") # Or use WORLD_HEIGHT, WORLD_WIDTH if row-major
        self.npc_fov_maps: dict[int, np.ndarray] = {}
        self.explored_map = np.full((WORLD_WIDTH, WORLD_HEIGHT), fill_value=False, order="F")

        # Build transparency map - this is expensive on init as it forces all chunks to generate.
        # Consider dynamic updates or pre-generation if performance becomes an issue.
        self.transparency_map = np.full((WORLD_WIDTH, WORLD_HEIGHT), fill_value=True, order="F")
        for x_map in range(WORLD_WIDTH):
            for y_map in range(WORLD_HEIGHT):
                tile = self.get_tile_at(x_map, y_map) # Forces chunk generation
                if tile and tile.blocks_fov:
                    self.transparency_map[x_map, y_map] = False

        self._update_light_level_and_fov() # Initialize based on game time 0
        self.update_fov() # Initial FOV calculation

    def _handle_player_light_source_burnout(self):
        """Checks and handles burnout of player's active light source."""
        if self.player.equipped_light_item_key and \
           self.player.light_source_active_until_tick != -1 and \
           self.game_time >= self.player.light_source_active_until_tick:

            burnt_item_def = ITEM_DEFINITIONS.get(self.player.equipped_light_item_key)
            item_name = burnt_item_def.get("name", "light source") if burnt_item_def else "light source"
            self.add_message_to_chat_log(f"Your {item_name} has burnt out!")

            becomes_item_key = burnt_item_def.get("properties", {}).get("on_burnout_becomes")
            if becomes_item_key:
                self.player.inventory[becomes_item_key] = self.player.inventory.get(becomes_item_key, 0) + 1
                # Could also remove 1 of the original item if it was stackable and not fully consumed by "lighting" it
                # For now, lighting "unlit_torch" consumes it, and burnout creates "burnt_out_torch".

            self.player.equipped_light_item_key = None
            self.player.current_personal_light_radius = 0
            self.player.light_source_active_until_tick = -1
            # No need to call self.update_fov() here, as _update_light_level_and_fov (which calls this)
            # is followed by update_fov() in the main loop.

    def update_fov(self) -> None:
        """
        Updates the player's field of view map and explored tiles.
        Also updates FOV for all NPCs.
        """
        # Player FOV
        base_ambient_fov_radius = self.current_fov_radius
        effective_player_fov_radius = base_ambient_fov_radius

        if self.player.equipped_light_item_key and self.player.current_personal_light_radius > 0:
            # Check for burnout if it has a duration
            is_active = True
            if self.player.light_source_active_until_tick != -1 and \
               self.game_time >= self.player.light_source_active_until_tick:
                is_active = False # Burnt out, specific burnout logic is handled elsewhere
                                  # but for FOV calc, it's not providing light now.

            if is_active:
                effective_player_fov_radius = max(base_ambient_fov_radius, self.player.current_personal_light_radius)

        self.player_fov_map = tcod.map.compute_fov(
            self.transparency_map,
            (self.player.x, self.player.y),
            radius=effective_player_fov_radius, # Use the effective radius
            algorithm=tcod.FOV_SYMMETRIC_SHADOWCAST # A common algorithm
        )
        # Update explored map
        self.explored_map |= self.player_fov_map

        # NPC FOVs
        self.npc_fov_maps.clear() # Clear previous NPC FOV maps
        for npc in self.village_npcs + self.npcs: # Iterate all relevant NPCs
            if npc.is_dead:
                continue
            # NPCs use the same global FOV radius for now, can be customized later
            npc_fov_radius = self.current_fov_radius # Or npc.perception_radius if defined
            self.npc_fov_maps[npc.id] = tcod.map.compute_fov(
                self.transparency_map,
                (npc.x, npc.y),
                radius=npc_fov_radius,
                algorithm=tcod.FOV_SYMMETRIC_SHADOWCAST
            )

            # NPC Item Perception within their FOV
            npc.perceived_item_tiles.clear()
            if npc.id in self.npc_fov_maps: # Should always be true if just computed
                fov_map_for_npc = self.npc_fov_maps[npc.id]
                # Iterate through coordinates that are visible to the NPC
                # np.where returns a tuple of arrays, one for each dimension
                visible_y_coords, visible_x_coords = np.where(fov_map_for_npc)
                for i in range(len(visible_x_coords)):
                    vx, vy = visible_x_coords[i], visible_y_coords[i]
                    if (vx,vy) in self.items_on_map and self.items_on_map[(vx,vy)]:
                        npc.perceived_item_tiles.append((vx,vy))


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
        for y_coord in range(WORLD_HEIGHT):
            for x_coord in range(WORLD_WIDTH):
                tile = self.get_tile_at(x_coord,y_coord)
                if not tile or not tile.passable:
                    cost[y_coord,x_coord] = 0 # Wall (0 means impassable for tcod.path)
                elif tile.is_hazard:
                    hazard_cost_value = 50 # Default high cost for generic hazard
                    if tile.hazard_type == "fire_trap_active":
                        hazard_cost_value = 100 # Fire is very undesirable
                    elif tile.hazard_type == "water_deep":
                        hazard_cost_value = 75 # Deep water also very undesirable
                    # Ensure cost fits within int8 if tcod expects signed, typically positive costs are fine.
                    # tcod path cost array: 0 for wall, >0 for walkable. Higher is more costly.
                    cost[y_coord,x_coord] = np.int8(min(hazard_cost_value, 127)) # Max for signed int8 if needed, else 255 for unsigned. Let's keep it reasonable.
                else:
                    cost[y_coord,x_coord] = 1 # Standard floor cost

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
        """Updates the position of NPCs based on their current path AND handles execution of some combat actions."""
        for npc in self.village_npcs: # Later might include self.npcs if they also use this system
            if npc.is_dead:
                continue

            # --- Handle Combat Action Execution ---
            if npc.current_task == "combat_action_attack_player":
                player = self.player
                distance_x = abs(npc.x - player.x)
                distance_y = abs(npc.y - player.y)
                manhattan_distance = distance_x + distance_y

                if manhattan_distance <= npc.attack_range:
                    self.npc_attempt_attack_player(npc, player)
                    # After attacking, the NPC's turn for movement/further action is done for this tick.
                    # Their AI will decide next action on the next AI tick.
                    # Clear path to prevent residual movement if any was set.
                    npc.current_path = []
                    npc.current_destination_coords = None
                    continue # Move to next NPC
                else:
                    # NPC wants to attack but player is not in range.
                    # The AI decision (_handle_npc_combat_turn) should ideally have set
                    # current_task to "combat_action_move_to_attack_player".
                    # If this state is reached, it's a slight desync. We can force a move task.
                    # self.add_message_to_chat_log(f"{npc.name} wants to attack but player moved out of range. Will try to close in.")
                    npc.current_task = "combat_action_move_to_attack_player"
                    # Pathing for this will be handled below if no current_path exists or needs recalculation.
                    npc.current_path = [] # Clear any old path
                    npc.current_destination_coords = None

            # --- Handle Pathing for Combat Movement Tasks (Move to Attack, Flee) ---
            # These tasks require a path to be calculated if not already present or if target (player) moved.
            # Fleeing: Calculate path away from player if task is flee and no current valid path.
            elif npc.current_task == "combat_action_flee_from_player":
                if not npc.current_path or npc.current_destination_coords is None: # Needs a new flee path
                    player_x, player_y = self.player.x, self.player.y
                    flee_distance = 15 # How far to try and flee

                    # Calculate direction away from player
                    dx = npc.x - player_x
                    dy = npc.y - player_y

                    # Normalize (roughly) and scale for flee distance
                    len_flee_vec = math.sqrt(dx*dx + dy*dy)
                    if len_flee_vec > 0:
                        flee_target_x = npc.x + int( (dx / len_flee_vec) * flee_distance )
                        flee_target_y = npc.y + int( (dy / len_flee_vec) * flee_distance )
                    else: # NPC is on same tile as player, flee randomly
                        flee_target_x = npc.x + random.randint(-flee_distance, flee_distance)
                        flee_target_y = npc.y + random.randint(-flee_distance, flee_distance)

                    # Clamp to world bounds
                    flee_target_x = max(0, min(WORLD_WIDTH - 1, flee_target_x))
                    flee_target_y = max(0, min(WORLD_HEIGHT - 1, flee_target_y))

                    # Check if target is passable, if not, try to find a nearby one (simplified for now)
                    flee_tile = self.get_tile_at(flee_target_x, flee_target_y)
                    if not (flee_tile and flee_tile.passable):
                        # Basic fallback: try a few random nearby spots around the ideal flee target
                        found_alt_flee = False
                        for _ in range(5): # Try 5 alternatives
                            alt_x = flee_target_x + random.randint(-3,3)
                            alt_y = flee_target_y + random.randint(-3,3)
                            alt_x = max(0, min(WORLD_WIDTH - 1, alt_x))
                            alt_y = max(0, min(WORLD_HEIGHT - 1, alt_y))
                            alt_tile = self.get_tile_at(alt_x, alt_y)
                            if alt_tile and alt_tile.passable:
                                flee_target_x, flee_target_y = alt_x, alt_y
                                found_alt_flee = True
                                break
                        if not found_alt_flee:
                            # self.add_message_to_chat_log(f"{npc.name} is cornered and cannot find a good flee path!")
                            npc.current_task = "combat_action_hold_position" # Or fight if aggressive
                            continue # Skip pathing for this turn

                    path = self.calculate_path(npc.x, npc.y, flee_target_x, flee_target_y)
                    if path:
                        npc.current_path = path
                        npc.current_destination_coords = (flee_target_x, flee_target_y)
                        # self.add_message_to_chat_log(f"{npc.name} is fleeing towards ({flee_target_x},{flee_target_y}).")
                    else:
                        # self.add_message_to_chat_log(f"{npc.name} tries to flee but sees no escape path!")
                        npc.current_task = "combat_action_hold_position" # Fallback if no path
                        # No 'continue' here, will fall through to standard path movement if a path was somehow set by other means.

            elif npc.current_task == "combat_action_move_to_attack_player":
                player = self.player
                # Check if a path needs to be (re)calculated
                # Condition: No current path, OR current path destination is not close to player's current position
                # OR current path destination is None (should be covered by no current path)
                needs_new_path = False
                if not npc.current_path or not npc.current_destination_coords:
                    needs_new_path = True
                else:
                    # If player moved too far from current path's target
                    # (This is a simple check; more robust would be if path destination is not adjacent to player)
                    dest_x, dest_y = npc.current_destination_coords
                    # If current path destination is not adjacent to player's current position.
                    # Adjacency check: Manhattan distance of 1 between (dest_x, dest_y) and (player.x, player.y)
                    if abs(dest_x - player.x) + abs(dest_y - player.y) > npc.attack_range : # attack_range is usually 1
                         needs_new_path = True


                if needs_new_path:
                    # Find a tile adjacent to the player to path to.
                    # This will be implemented in _find_attack_position_near_target (next plan step)
                    # For now, placeholder: target player's current position directly.
                    # This will be refined to target an adjacent tile.
                    attack_pos_x, attack_pos_y = self._find_best_adjacent_tile_for_attack(player.x, player.y, npc)

                    if attack_pos_x is not None and attack_pos_y is not None:
                        path = self.calculate_path(npc.x, npc.y, attack_pos_x, attack_pos_y)
                        if path:
                            npc.current_path = path
                            npc.current_destination_coords = (attack_pos_x, attack_pos_y)
                            # self.add_message_to_chat_log(f"{npc.name} is moving to attack, heading towards ({attack_pos_x},{attack_pos_y}) near player.")
                        else:
                            # self.add_message_to_chat_log(f"{npc.name} wants to attack but cannot find a path to player.")
                            # Fallback: if can't path, maybe hold or let AI decide something else next turn
                            npc.current_task = "combat_action_hold_position"
                    else:
                        # self.add_message_to_chat_log(f"{npc.name} cannot find a suitable position to attack the player from.")
                        npc.current_task = "combat_action_hold_position"

            elif npc.current_task == "combat_action_move_to_cover":
                # Path to the cover spot stored in npc.task_target_coords
                if npc.task_target_coords and (not npc.current_path or npc.current_destination_coords != npc.task_target_coords):
                    cover_x, cover_y = npc.task_target_coords
                    # Check if already at the cover spot
                    if npc.x == cover_x and npc.y == cover_y:
                        # self.add_message_to_chat_log(f"{npc.name} reached cover at ({cover_x},{cover_y}).")
                        npc.current_task = "combat_action_hold_position" # Or a specific "in_cover" task
                        npc.current_path = []
                        npc.current_destination_coords = None
                        npc.task_target_coords = None # Clear the target
                    else:
                        path = self.calculate_path(npc.x, npc.y, cover_x, cover_y)
                        if path:
                            npc.current_path = path
                            npc.current_destination_coords = (cover_x, cover_y)
                            # self.add_message_to_chat_log(f"{npc.name} is moving to cover at ({cover_x},{cover_y}). Path length: {len(path)}")
                        else:
                            # self.add_message_to_chat_log(f"{npc.name} couldn't find a path to cover at ({cover_x},{cover_y}). Holding position.")
                            npc.current_task = "combat_action_hold_position"
                            npc.current_path = []
                            npc.current_destination_coords = None
                            npc.task_target_coords = None # Clear target if path fails
                elif not npc.task_target_coords: # Should have been set by AI, but as a fallback:
                    # self.add_message_to_chat_log(f"{npc.name} wants to move to cover but has no specific target. Holding.")
                    npc.current_task = "combat_action_hold_position"

            elif npc.current_task == "task_going_to_pickup_item":
                if npc.task_target_coords and npc.task_target_item_details:
                    target_x, target_y = npc.task_target_coords
                    item_key_to_pickup = npc.task_target_item_details["item_key"]

                    if npc.x == target_x and npc.y == target_y: # Arrived at item location
                        # Attempt to remove item from map
                        if self.remove_item_from_map(item_key_to_pickup, 1, target_x, target_y):
                            # Add to NPC inventory
                            npc.npc_inventory[item_key_to_pickup] = npc.npc_inventory.get(item_key_to_pickup, 0) + 1
                            item_name = ITEM_DEFINITIONS.get(item_key_to_pickup, {}).get("name", item_key_to_pickup)

                            # Log pickup if player can perceive it
                            dist_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y)
                            can_player_see_pickup = (npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.x, self.player.y]) or \
                                                    (self.player_fov_map[npc.x, npc.y]) # If player sees NPC or NPC sees player (simplified)

                            if dist_to_player <= self.player.hearing_radius or can_player_see_pickup:
                                self.add_message_to_chat_log(f"{npc.name} picks up a {item_name}.")

                            # TODO: Trigger equipment decision logic here if item is equippable
                            # For now, just go idle.
                            npc.current_task = "idle"
                        else:
                            # Item might have been picked up by someone else or disappeared
                            # self.add_message_to_chat_log(f"{npc.name} reached for an item at ({target_x},{target_y}), but it was gone.")
                            npc.current_task = "idle" # Or "confused_item_gone"

                        npc.task_target_coords = None
                        npc.task_target_item_details = None
                        npc.current_path = []
                        npc.current_destination_coords = None
                        continue # Action complete for this tick

                    else: # Not at item location, need to path/continue pathing
                        if not npc.current_path or npc.current_destination_coords != (target_x, target_y):
                            path = self.calculate_path(npc.x, npc.y, target_x, target_y)
                            if path:
                                npc.current_path = path
                                npc.current_destination_coords = (target_x, target_y)
                            else:
                                # Cannot path to item, give up for now
                                # self.add_message_to_chat_log(f"{npc.name} can't find a path to the item at ({target_x},{target_y}).")
                                npc.current_task = "idle"
                                npc.task_target_coords = None
                                npc.task_target_item_details = None
                                npc.current_path = []
                                npc.current_destination_coords = None
                                continue # Stop processing this NPC for this tick
                else: # Task was set but target info is missing, error state
                    npc.current_task = "idle_confused"
                    npc.task_target_coords = None
                    npc.task_target_item_details = None
                    npc.current_path = []
                    npc.current_destination_coords = None
                    continue


            # --- Standard Path-Based Movement ---
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
                    if other_npc.id != attacker_npc.id and other_npc.x == adj_x and other_npc.y == adj_y and not other_npc.is_dead:
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
                        if other_npc.id != npc.id and other_npc.x == spot_x and other_npc.y == spot_y and not other_npc.is_dead:
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

    def _update_npc_schedules(self):
        """
        Periodically updates NPC tasks based on game time and current state.
        Also handles routing to combat AI if NPC is hostile.
        """
        for npc in self.village_npcs: # Consider self.npcs as well if they become more dynamic
            if npc.is_dead:
                continue

            if self.game_time - npc.game_time_last_updated < NPC_SCHEDULE_UPDATE_INTERVAL:
                # Even if not due for a full schedule update, hostile NPCs should still get a combat AI tick
                if npc.is_hostile_to_player:
                    # Potentially add a smaller interval check here for combat responsiveness
                    # For now, combat decisions happen on their schedule update tick too.
                    # This could be refined for faster combat reactions.
                    pass # Will be handled below if interval met.
                else:
                    continue # Skip non-hostile NPC if not their update interval

            npc.game_time_last_updated = self.game_time

            if npc.is_hostile_to_player:
                self._handle_npc_combat_turn(npc) # New method for combat decision making
                # After combat turn, NPC might have a new task like "attacking_player" or "fleeing"
                # Pathing/movement for these tasks will be handled by _update_npc_movement

            # Standard scheduling logic if not hostile or if combat AI didn't set a pathing task
            # (e.g., if combat AI decided to "hold_position" or an attack was immediate)
            # We also need to ensure that combat tasks aren't immediately overridden by scheduling.
            # A simple way is to only run scheduling if the NPC is not currently in a combat-related task.
            elif npc.current_task not in ["attacking_player", "moving_to_attack_player", "fleeing_from_player", "holding_position_combat", "combat_action_use_healing_item", "combat_action_move_to_cover"]:

                # --- NPC Item Pickup Decision (New) ---
                # If NPC is idle/wandering and sees items, they might try to pick one up.
                # This decision should happen before regular scheduling if items are perceived.
                made_item_decision = False
                if npc.perceived_item_tiles and npc.current_task in ["idle", "wandering", "at home", "at work"]: # Can decide to pickup even at work/home if item is compelling
                    perceived_items_list = []
                    for item_x, item_y in npc.perceived_item_tiles:
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
                        for key, quant in npc.npc_inventory.items():
                            if count < 5:
                                inventory_summary_parts.append(f"{quant}x {ITEM_DEFINITIONS.get(key, {}).get('name', key)}")
                                count +=1
                            else:
                                inventory_summary_parts.append("...")
                                break
                        inventory_summary = ", ".join(inventory_summary_parts) if inventory_summary_parts else "empty"

                        pickup_prompt = LLM_PROMPTS["npc_item_pickup_decision"].format(
                            npc_name=npc.name,
                            npc_personality=npc.personality,
                            npc_current_task=npc.current_task,
                            npc_inventory_summary=inventory_summary,
                            npc_equipped_weapon_name=ITEM_DEFINITIONS.get(npc.equipped_weapon, {}).get("name", "None") if npc.equipped_weapon else "None",
                            npc_equipped_armor_name=ITEM_DEFINITIONS.get(npc.equipped_armor_body, {}).get("name", "None") if npc.equipped_armor_body else "None",
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
                                if dist_to_player <= self.player.hearing_radius and dist_to_player <= npc.speech_volume and \
                                   (npc.id in self.npc_fov_maps and self.npc_fov_maps[npc.id][self.player.x, self.player.y]): # visible
                                    self.add_message_to_chat_log(f"({reasoning})")


                                if action == "pickup_item":
                                    target_coords_list = pickup_decision.get("target_coords")
                                    item_key_to_pickup = pickup_decision.get("item_key_to_pickup")
                                    if target_coords_list and item_key_to_pickup:
                                        npc.current_task = "task_going_to_pickup_item"
                                        npc.task_target_coords = tuple(target_coords_list)
                                        npc.task_target_item_details = {"item_key": item_key_to_pickup}
                                        npc.current_path = [] # Clear path for new task
                                        made_item_decision = True
                                        # self.add_message_to_chat_log(f"Debug: {npc.name} decided to pick up {item_key_to_pickup} at {target_coords_list}.")
                            except json.JSONDecodeError:
                                # self.add_message_to_chat_log(f"Error decoding item pickup decision for {npc.name}: {pickup_response_str}")
                                pass # Fall through to regular scheduling

                # Original scheduling logic starts here, only if no item pickup decision was made
                if not made_item_decision and npc.current_task in ["idle", "at home", "at work", "idle_confused", "wandering"] and not npc.current_path:
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
                            npc.current_task = new_task_label # Use new_task_label here
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
                            npc.current_task = "idle_confused" # Cannot find path

            # After all task decisions and path assignments:
            # If NPC is at work, handle specific work sub-tasks or general production.
            # This is also where NPCs who have arrived at work ("at work") will start their sub-task logic.
            if npc.current_task == "at work" or npc.current_task.startswith("Working ("): # Check both generic and specific working tasks
                # Attempt to handle detailed sub-tasks first
                if self._handle_npc_work_sub_tasks(npc):
                    pass # Sub-task logic handled it, potentially setting a more specific task display
                else: # Fallback to general production if no sub-tasks defined or applicable for this NPC/profession
                    self._handle_npc_production(npc)

            if npc.current_task != "sleeping" and hasattr(npc, 'original_char_before_sleep') and npc.char == ord('z'):
                if hasattr(npc, 'original_char_before_sleep'): # Ensure it exists before trying to access
                    npc.char = npc.original_char_before_sleep

            npc.game_time_last_updated = self.game_time

    def _find_nearest_tree_for_chopping(self, npc: NPC, work_building: Building, search_radius: int = 15) -> tuple[int, int] | None:
        """
        Finds the nearest choppable tree to the work_building's center for the NPC.
        Returns global (x,y) coordinates or None.
        """
        center_x, center_y = work_building.global_center_x, work_building.global_center_y
        closest_tree_coords = None
        min_dist_sq = float('inf')

        # Iterate in expanding square rings around the building's center
        for r in range(search_radius + 1): # r=0 is the center point itself
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

        return None # No choppable, untargeted tree found within search_radius

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
        else:
            # For other zones, use pre-defined coordinates in work_building.work_zone_tiles
            zone_coords_list = work_building.work_zone_tiles.get(target_zone_tag)
            if zone_coords_list:
                # Pick a random available coordinate from the list for now.
                # Could be smarter (e.g., closest, or one not currently targeted by another NPC).
                return random.choice(zone_coords_list)
            else:
                # self.add_message_to_chat_log(f"Warning: No coordinates defined for work zone '{target_zone_tag}' in building {work_building.id} for {npc.name}.")
                return None

    def _produce_sub_task_output(self, npc: NPC, work_building: Building, sub_task_data: dict):
        """Handles item production or consumption for a completed sub-task."""
        # Item Consumption
        consumes_def = sub_task_data.get("consumes_item_from_workplace")
        if consumes_def:
            for item_key, quantity_needed in consumes_def.items():
                current_qty_in_building = work_building.building_inventory.get(item_key, 0)
                if current_qty_in_building >= quantity_needed:
                    work_building.building_inventory[item_key] = current_qty_in_building - quantity_needed
                    if work_building.building_inventory[item_key] <= 0:
                        del work_building.building_inventory[item_key]
                    # self.add_message_to_chat_log(f"Debug: {npc.name}'s task consumed {quantity_needed} {item_key} from {work_building.building_type}")
                else:
                    # self.add_message_to_chat_log(f"Debug: {npc.name} needed {quantity_needed} {item_key} for task, but {work_building.building_type} only had {current_qty_in_building}.")
                    # TODO: How to handle if inputs are missing? NPC gets stuck? Task fails?
                    # For now, production might still happen if inputs are short, or it might make partial.
                    # Let's assume for now production is blocked if inputs not met.
                    return # Block production if inputs not met

        # Item Production
        produces_def = sub_task_data.get("produces_item_at_workplace")
        if produces_def:
            for item_key, quantity_produced in produces_def.items():
                current_qty = work_building.building_inventory.get(item_key, 0)
                work_building.building_inventory[item_key] = current_qty + quantity_produced

                item_name = ITEM_DEFINITIONS.get(item_key, {}).get("name", item_key)
                # Optional: Log production for player if they can see/hear the NPC
                # dist_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y)
                # if dist_to_player <= 10: # Arbitrary observation distance
                #    self.add_message_to_chat_log(f"{npc.name} finishes working and produces {quantity_produced} {item_name} at the {work_building.building_type}.")


    def _handle_npc_work_sub_tasks(self, npc: NPC) -> bool:
        """
        Manages an NPC's progression through defined work sub-tasks for their profession.
        Returns True if sub-task logic was applied (even if just pathing or waiting),
        False if no sub-tasks are applicable or defined for this NPC's current state/profession.
        """
        if not npc.work_building_id or not npc.profession:
            return False

        profession_data = get_profession_data(npc.profession)
        if not profession_data or not profession_data.get("sub_tasks") or not profession_data.get("default_sub_task_sequence"):
            return False # No sub-tasks defined for this profession

        work_building = self.buildings_by_id.get(npc.work_building_id)
        if not work_building:
            # self.add_message_to_chat_log(f"Error: {npc.name} has work_building_id {npc.work_building_id} but building not found.")
            npc.current_task = "idle_confused"
            return True # Handled this confusion

        sub_task_sequence = profession_data["default_sub_task_sequence"]
        if not sub_task_sequence:
            return False # Empty sequence

        # If current sub-task is done (timer ran out or just finished one)
        if not npc.current_sub_task or (npc.sub_task_target_coords and (npc.x, npc.y) == npc.sub_task_target_coords and npc.sub_task_timer <= 0):

            # If a sub-task was just completed (timer is 0 or less, and was at target)
            if npc.current_sub_task and npc.sub_task_timer <= 0:
                # Handle output/consumption of the completed sub-task
                completed_sub_task_data = get_sub_task_data(npc.profession, npc.current_sub_task)
                if completed_sub_task_data:
                    self._produce_sub_task_output(npc, work_building, completed_sub_task_data)

                # Move to next sub-task in sequence
                npc.current_sub_task_sequence_index = (npc.current_sub_task_sequence_index + 1) % len(sub_task_sequence)

            # Set up the new sub-task
            next_sub_task_id = sub_task_sequence[npc.current_sub_task_sequence_index]
            current_sub_task_data = get_sub_task_data(npc.profession, next_sub_task_id)

            if not current_sub_task_data:
                # self.add_message_to_chat_log(f"Error: Could not find sub_task_data for {next_sub_task_id} in {npc.profession}")
                npc.current_task = "idle_confused"
                return True

            npc.current_sub_task = next_sub_task_id
            npc.sub_task_zone_target = current_sub_task_data.get("target_zone_tag")
            npc.sub_task_target_coords = self._find_target_coords_for_sub_task(npc, work_building, current_sub_task_data)

            if not npc.sub_task_target_coords:
                # self.add_message_to_chat_log(f"{npc.name} could not find a location for sub-task: {npc.current_sub_task}.")
                # NPC might be stuck for this cycle. Clear sub-task to retry finding location next schedule update.
                npc.current_sub_task = None
                npc.sub_task_zone_target = None
                npc.current_task = f"Working ({npc.profession} - stalled)" # Or some other indicator
                return True

            npc.current_path = [] # Clear path for new sub-task target
            npc.sub_task_timer = current_sub_task_data.get("duration_ticks", 10) # Reset timer for the action phase
            # self.add_message_to_chat_log(f"Debug: {npc.name} starting sub-task {npc.current_sub_task}, target {npc.sub_task_target_coords}, zone {npc.sub_task_zone_target}")


        # If NPC has a sub-task and a target location for it
        if npc.current_sub_task and npc.sub_task_target_coords:
            sub_task_disp_name = get_sub_task_data(npc.profession, npc.current_sub_task).get("display_name", npc.current_sub_task)

            if (npc.x, npc.y) != npc.sub_task_target_coords:
                # Path to target if not already there
                if not npc.current_path:
                    path = self.calculate_path(npc.x, npc.y, npc.sub_task_target_coords[0], npc.sub_task_target_coords[1])
                    if path:
                        npc.current_path = path
                        npc.current_destination_coords = npc.sub_task_target_coords # For _update_npc_movement
                        # Update task display for pathing to sub-task action
                        npc.current_task = f"Working ({npc.profession} - {sub_task_disp_name} - Pathing)"
                    else:
                        # self.add_message_to_chat_log(f"{npc.name} cannot find path to {npc.sub_task_target_coords} for {npc.current_sub_task}.")
                        # Clear current sub-task details to retry finding location / path next time
                        npc.current_sub_task = None
                        npc.sub_task_target_coords = None
                        npc.sub_task_zone_target = None
                        npc.current_path = []
                        npc.current_destination_coords = None
                        npc.current_task = f"Working ({npc.profession} - Pathing Failed)"
                else:
                     # Already pathing, ensure task display reflects this. _update_npc_movement handles the move.
                     npc.current_task = f"Working ({npc.profession} - {sub_task_disp_name} - Pathing)"

            else: # NPC is at the sub-task target coordinates
                npc.current_path = [] # Clear path as arrived
                npc.current_destination_coords = None

                # Perform the action (decrement timer)
                npc.sub_task_timer -= 1

                # Update task display for performing action
                action_verb = get_sub_task_data(npc.profession, npc.current_sub_task).get("action_verb", "working on")
                total_duration = get_sub_task_data(npc.profession, npc.current_sub_task).get("duration_ticks", 10)
                progress = max(0, total_duration - npc.sub_task_timer)
                npc.current_task = f"Working ({npc.profession} - {action_verb} {sub_task_disp_name} [{progress}/{total_duration}])"

                if npc.sub_task_timer <= 0:
                    # Action complete, output handled at start of next cycle. Current_sub_task will be cleared.
                    # self.add_message_to_chat_log(f"Debug: {npc.name} finished action for sub-task {npc.current_sub_task}.")
                    # The loop will pick this up at the top of the function next call.
                    pass
            return True # Sub-task logic was processed

        return False # No current sub-task or target to act upon

    def _handle_npc_combat_turn(self, npc: NPC):
        """Handles an NPC's decision-making process during their combat turn."""
        if not npc.is_hostile_to_player or npc.is_dead:
            return

        # Gather context for LLM
        player = self.player
        distance_x = abs(npc.x - player.x)
        distance_y = abs(npc.y - player.y)
        manhattan_distance = distance_x + distance_y # Simple distance metric

        # Check if player is in attack range (Manhattan distance for melee)
        # Determine effective attack range and name based on equipped weapon
        effective_attack_range = npc.attack_range # Default to base
        effective_attack_name = npc.base_attack_name # Default to base

        if npc.equipped_weapon and npc.equipped_weapon in ITEM_DEFINITIONS:
            weapon_def = ITEM_DEFINITIONS[npc.equipped_weapon]
            effective_attack_range = weapon_def.get("properties", {}).get("attack_range", npc.attack_range)
            effective_attack_name = weapon_def.get("name", npc.base_attack_name)

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

        has_healing_item = npc.npc_inventory.get("healing_salve", 0) > 0

        prompt = LLM_PROMPTS["npc_combat_decision"].format(
            npc_name=npc.name,
            npc_personality=npc.personality,
            can_see_player=can_see_player,
            npc_combat_behavior=npc.combat_behavior,
            npc_hp=npc.hp,
            npc_max_hp=npc.max_hp,
            npc_current_task=npc.current_task,
            npc_attack_name=effective_attack_name, # Use effective name
            npc_attack_range=effective_attack_range, # Use effective range
            has_healing_item=has_healing_item,
            player_x=player.x,
            player_y=player.y,
            npc_x=npc.x,
            npc_y=npc.y,
            distance_to_player=manhattan_distance,
            player_in_attack_range=player_in_attack_range,
            player_last_action_desc=player_last_action_desc,
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
                    # self.add_message_to_chat_log(f"({npc.name} decides to attack immediately as player is in range.)")
            elif chosen_action == "flee_from_player":
                npc.current_task = "combat_action_flee_from_player"
            elif chosen_action == "move_to_cover":
                cover_spot_x, cover_spot_y = self._find_best_cover_spot(npc, player.x, player.y)
                if cover_spot_x is not None:
                    npc.current_task = "combat_action_move_to_cover"
                    npc.task_target_coords = (cover_spot_x, cover_spot_y) # Store the specific cover spot
                    # self.add_message_to_chat_log(f"({npc.name} is heading to cover at ({cover_spot_x},{cover_spot_y}))")
                else:
                    # No cover found, default to holding position or another fallback
                    # self.add_message_to_chat_log(f"({npc.name} looked for cover but found none.)")
                    if npc.hp < npc.max_hp * 0.3 and npc.combat_behavior == "cowardly": # If low health and cowardly, flee instead
                        npc.current_task = "combat_action_flee_from_player"
                        # self.add_message_to_chat_log(f"({npc.name} couldn't find cover and decides to flee instead!)")
                    else:
                        npc.current_task = "combat_action_hold_position"
            elif chosen_action == "use_healing_item":
                if npc.npc_inventory.get("healing_salve", 0) > 0:
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

        # Determine weapon details for the attack
        weapon_name = npc.base_attack_name
        weapon_damage_description = npc.base_attack_damage_dice

        if npc.equipped_weapon and npc.equipped_weapon in ITEM_DEFINITIONS:
            weapon_def = ITEM_DEFINITIONS[npc.equipped_weapon]
            weapon_name = weapon_def.get("name", npc.base_attack_name)
            dice = weapon_def.get("properties", {}).get("damage_dice", npc.base_attack_damage_dice)
            bonus = weapon_def.get("properties", {}).get("damage_bonus", 0)
            weapon_damage_description = f"{dice}"
            if bonus > 0:
                weapon_damage_description += f"+{bonus}"
            elif bonus < 0:
                weapon_damage_description += f"{bonus}"


        # Conceptual NPC melee skill
        npc_melee_skill = 5
        if npc.combat_behavior == "aggressive": npc_melee_skill += 2
        if npc.profession in ["Guard", "Sheriff"]: npc_melee_skill += 2
        npc_melee_skill = max(1, min(10, npc_melee_skill))

        # Conceptual player toughness
        player_toughness_desc = "average"
        # TODO: Update player_toughness_desc based on player's equipped armor

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

            if hit and damage_dealt > 0:
                player.take_damage(damage_dealt)
                self.add_message_to_chat_log(f"You take {damage_dealt} damage! Your HP is now {player.hp}/{player.max_hp}.")
                if player.hp <= 0:
                    self.add_message_to_chat_log("You have been defeated!")
                    # Handle player death/game over state here
                    # For now, just a message. Could set a game_state like "GAME_OVER"
                    self.game_state = "PLAYER_DEAD" # Example, handle in main loop
            elif hit and damage_dealt <= 0:
                self.add_message_to_chat_log(f"{npc.name}'s attack hits you but deals no damage.")

            # After an attack, NPC might re-evaluate or just be ready for next turn's decision
            # For now, we assume their combat turn is "done" after this attack action.
            # The _handle_npc_combat_turn will be called again on their next AI tick.

        except json.JSONDecodeError:
            self.add_message_to_chat_log(f"{npc.name}'s attack is confusing. (LLM Format Error: {response_str})")
        except ValueError: # For int(damage_dealt)
             self.add_message_to_chat_log(f"The LLM provided an invalid damage amount for {npc.name}'s attack: {response_json.get('damage_dealt') if 'response_json' in locals() else 'Unknown'}")


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

                # Assign wealth (randomly for now) - This is now part of LLM prompt for personality
                npc.wealth_level = npc_data.get("wealth_level", random.choice(["poor", "average", "wealthy"]))

                # Combat AI attributes from LLM
                npc.combat_behavior = npc_data.get("combat_behavior", "defensive")
                npc.base_attack_name = npc_data.get("base_attack_name", "fists")

                # Basic logic for damage dice based on attack name or behavior
                # More sophisticated logic could be added here, e.g., guards get better defaults
                if "knife" in npc.base_attack_name.lower() or \
                   "dagger" in npc.base_attack_name.lower() or \
                   "tool" in npc.base_attack_name.lower() or \
                   "hammer" in npc.base_attack_name.lower() or \
                   "claws" in npc.base_attack_name.lower() or \
                   "teeth" in npc.base_attack_name.lower() or \
                   "spear" in npc.base_attack_name.lower():
                    npc.base_attack_damage_dice = "1d4"
                elif "sword" in npc.base_attack_name.lower() or \
                     "axe" in npc.base_attack_name.lower() or \
                     "mace" in npc.base_attack_name.lower():
                    npc.base_attack_damage_dice = "1d6"
                else: # fists, kick, staff, etc.
                    npc.base_attack_damage_dice = "1d3"

                if npc.combat_behavior == "aggressive" and npc.base_attack_damage_dice == "1d3":
                    npc.base_attack_damage_dice = "1d4" # Aggressive NPCs might hit a bit harder by default

                npc.attack_range = 1 # Default melee

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

                # Chance to give NPC a healing salve
                if random.random() < 0.33: # 33% chance
                    npc.npc_inventory["healing_salve"] = npc.npc_inventory.get("healing_salve", 0) + 1
                    # self.add_message_to_chat_log(f"Debug: {npc.name} received a healing salve.")

                # Assign starting equipment based on role/behavior
                if npc.profession in ["Sheriff", "Guard"] or npc.combat_behavior == "aggressive":
                    if "rusty_sword" in ITEM_DEFINITIONS:
                        npc.npc_inventory["rusty_sword"] = npc.npc_inventory.get("rusty_sword", 0) + 1
                        npc.equipped_weapon = "rusty_sword"
                        # self.add_message_to_chat_log(f"Debug: {npc.name} equipped a rusty_sword.")
                    if "leather_jerkin" in ITEM_DEFINITIONS:
                        npc.npc_inventory["leather_jerkin"] = npc.npc_inventory.get("leather_jerkin", 0) + 1
                        npc.equipped_armor_body = "leather_jerkin"
                        # self.add_message_to_chat_log(f"Debug: {npc.name} equipped a leather_jerkin.")
                    # Optionally, add a helmet too
                    if random.random() < 0.5 and "iron_helmet" in ITEM_DEFINITIONS: # 50% chance for guards/aggressive to also have helmet
                        npc.npc_inventory["iron_helmet"] = npc.npc_inventory.get("iron_helmet", 0) + 1
                        npc.equipped_armor_head = "iron_helmet"


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
                    # Check if player can hear this NPC
                    distance_to_player = abs(npc.x - self.player.x) + abs(npc.y - self.player.y) # Manhattan distance

                    can_hear = False
                    if distance_to_player <= self.player.hearing_radius and \
                       distance_to_player <= npc.speech_volume:
                        can_hear = True

                    if can_hear:
                        # For now, keep existing message format.
                        # Could later add "(you overhear)" or similar if NPC not visible.
                        self.add_message_to_chat_log(f"{npc.name}: {llm_dialogue.strip()}")
                    # Else, player doesn't hear it, so don't add to log.

                    npc.last_speech_time = current_time # Update speech time regardless of player hearing

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
        if building.width > 3 and building.height > 3: # Ensure mill is large enough
            # Relative local coords for the start of the 2x2 log pile area
            local_pile_start_x = 1
            local_pile_start_y = building.height - 3 # 1 up from bottom floor, then 1 more for 2x2

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
        if building.width > 5 and building.height > 3: # Need more width to avoid overlap if simple placement
            local_split_start_x = building.width - 3
            local_split_start_y = building.height - 3

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

            self.update_fov() # Player moved, so update FOV


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
        item_def = ITEM_DEFINITIONS.get(item_key)
        if not item_def:
            self.add_message_to_chat_log(f"You don't know how to use '{item_key}'.")
            return

        # Check if trying to use (extinguish) an active light source by "using" its lit state key
        if self.player.equipped_light_item_key == item_key and item_def.get("properties", {}).get("emits_light"):
            # This means player is trying to "use" their currently lit torch, so extinguish it.
            extinguish_becomes_key = item_def.get("properties", {}).get("on_extinguish_becomes")
            if extinguish_becomes_key:
                self.player.inventory[extinguish_becomes_key] = self.player.inventory.get(extinguish_becomes_key, 0) + 1

            self.add_message_to_chat_log(f"You extinguish your {self.player.equipped_light_item_key}.")
            self.player.equipped_light_item_key = None
            self.player.current_personal_light_radius = 0
            self.player.light_source_active_until_tick = -1
            self.update_fov()
            return

        # Standard item usage from inventory
        if self.player.inventory.get(item_key, 0) <= 0:
            self.add_message_to_chat_log(f"You don't have any {item_def.get('name', item_key)} to use.")
            return

        on_use_effect = item_def.get("on_use_effect")

        if on_use_effect == "light_torch":
            if self.player.equipped_light_item_key: # Already has a light source active
                self.add_message_to_chat_log(f"You already have a {self.player.equipped_light_item_key} lit.")
                return

            # Consume the unlit_torch
            self.player.inventory[item_key] -= 1
            if self.player.inventory[item_key] <= 0:
                del self.player.inventory[item_key]

            # Activate "torch_lit" state
            lit_torch_def = ITEM_DEFINITIONS.get("torch_lit", {})
            self.player.equipped_light_item_key = "torch_lit" # Use the key for the lit definition
            self.player.current_personal_light_radius = lit_torch_def.get("properties", {}).get("light_radius", 0)
            duration = lit_torch_def.get("properties", {}).get("duration_ticks", -1)
            if duration > 0:
                self.player.light_source_active_until_tick = self.game_time + duration
            else:
                self.player.light_source_active_until_tick = -1 # Infinite or not applicable

            self.add_message_to_chat_log(f"You light the {item_def.get('name', item_key)}. It casts a warm glow.")
            self.update_fov()
            return

        # Existing healing logic (or other on_use dictionary based effects)
        on_use_dict = item_def.get("on_use")
        if on_use_dict:
            heal_amount = on_use_dict.get("heal_amount")
            if heal_amount:
                if self.player.hp >= self.player.max_hp:
                    self.add_message_to_chat_log("You are already at full health!")
                else:
                    self.player.hp = min(self.player.max_hp, self.player.hp + heal_amount)
                    self.player.inventory[item_key] -= 1 # Consume item
                    if self.player.inventory[item_key] <= 0:
                        del self.player.inventory[item_key]
                    self.add_message_to_chat_log(f"You used a {item_def['name']} and healed {heal_amount} HP. Current HP: {self.player.hp}")
                return # Action taken

        # Fallback if no specific use effect handled
        self.add_message_to_chat_log(f"You can't figure out how to use the {item_def.get('name', item_key)} right now.")

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
        if quantity <= 0:
            return False

        if (x, y) in self.items_on_map:
            items_at_loc = self.items_on_map[(x, y)]
            for i, item_on_tile in enumerate(items_at_loc):
                if item_on_tile["item_key"] == item_key:
                    if item_on_tile["quantity"] >= quantity:
                        item_on_tile["quantity"] -= quantity
                        if item_on_tile["quantity"] <= 0:
                            items_at_loc.pop(i)
                            if not items_at_loc: # If list is empty, remove key from dict
                                del self.items_on_map[(x,y)]
                        # self.add_message_to_chat_log(f"Picked up {quantity} {ITEM_DEFINITIONS.get(item_key,{}).get('name',item_key)} from ({x},{y}).") # Optional debug
                        return True
                    else:
                        # Not enough quantity in this specific stack
                        # self.add_message_to_chat_log(f"Tried to pick up {quantity} of {item_key}, but only found {item_on_tile['quantity']}.")
                        return False
            # Item key not found in the list at this location
            return False
        return False # No items at this location