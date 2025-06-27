# engine.py
import math
import random
import numpy as np
import tcod.noise
import requests # Import requests
import time # Import time for NPC speech timing
from entities.base import NPC
from entities.tree import Tree, OakTree, AppleTree, PearTree
from config import (
    WORLD_WIDTH, WORLD_HEIGHT, POI_DENSITY, CHUNK_SIZE,
    NOISE_SCALE, NOISE_OCTAVES, NOISE_PERSISTENCE, NOISE_LACUNARITY,
    ELEVATION_DEEP_WATER, ELEVATION_WATER, ELEVATION_MOUNTAIN, ELEVATION_SNOW,
)
from data.tiles import TILE_DEFINITIONS, COLORS
from tile_types import Tile
from data.items import ITEM_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.prompts import LLM_PROMPTS, OLLAMA_ENDPOINT

import json # Import json for parsing LLM responses

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
    def __init__(self, x, y, width, height, building_type="house"):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.building_type = building_type
        self.interior_decorated = False # Flag for LLM decoration

class Village:
    def __init__(self):
        self.buildings = []

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
        self.max_hp = 30  # <-- ADD THIS
        self.hp = self.max_hp # <-- ADD THIS

    def take_damage(self, amount: int): # <-- ADD THIS METHOD
        self.hp -= amount
        if self.hp < 0:
            self.hp = 0

class World:
    """World class now uses a generator for a more complex map."""
    def __init__(self):
        self.chat_log = [] # Stores chat messages
        self.chunk_width = WORLD_WIDTH // CHUNK_SIZE
        self.chunk_height = WORLD_HEIGHT // CHUNK_SIZE
        self.player = Player(WORLD_WIDTH // 2, WORLD_HEIGHT // 2)
        self.generator = WorldGenerator(self.chunk_width, self.chunk_height)
        self.chunks = self._initialize_chunks()
        self.npcs = [] # Initialize NPCs list
        self._find_starting_position()
        self._populate_npcs()
        self.village_npcs = [] # To store NPCs specific to villages
        self.mouse_x = 0
        self.mouse_y = 0
        self.game_state = "PLAYING" # Initial game state

    def add_message_to_chat_log(self, message: str):
        self.chat_log.append(message)
        # Keep chat log to a reasonable size
        if len(self.chat_log) > 100:
            self.chat_log.pop(0)

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

    def _handle_npc_speech(self):
        current_time = time.time()
        for npc in self.npcs + self.village_npcs:
            if current_time - npc.last_speech_time > random.randint(10, 30): # NPCs speak every 10-30 seconds
                prompt = f"Generate a short, in-character dialogue response from {npc.name} to the player. {npc.name} is {npc.personality} and has {npc.attitude_to_player} attitude towards the player. Their family ties are {npc.family_ties}. Keep it concise and relevant to their personality and attitude."
                llm_dialogue = self._call_ollama(prompt)
                if llm_dialogue:
                    self.add_message_to_chat_log(f"{npc.name}: {llm_dialogue}")
                    npc.last_speech_time = current_time

    def decorate_building_interior(self, building):
        print(f"Decorating building at {building.x}, {building.y}")
        # Generate interior decoration using LLM
        decoration_items_list = ", ".join(DECORATION_ITEM_DEFINITIONS.keys())
        prompt = LLM_PROMPTS["building_interior"].format(
            building_type=building.building_type,
            width=building.width,
            height=building.height,
            decoration_items=decoration_items_list
        )
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
                            chunk_x, chunk_y = global_x // CHUNK_SIZE, global_y // CHUNK_SIZE
                            local_x, local_y = global_x % CHUNK_SIZE, global_y % CHUNK_SIZE
                            
                            # Ensure the chunk is generated before trying to modify its tiles
                            chunk = self.chunks[chunk_y][chunk_x]
                            if not chunk.is_generated:
                                self._generate_chunk_detail(chunk)

                            self.chunks[chunk_y][chunk_x].tiles[local_y][local_x] = Tile(
                                decoration_tile_def["char"],
                                decoration_tile_def["color"],
                                decoration_tile_def["passable"],
                                decoration_tile_def["name"]
                            )
                            print(f"Placed {item_type} at ({global_x}, {global_y})")
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
            prompt = f"The player approaches {closest_npc.name}. {closest_npc.name} is {closest_npc.personality} and has {closest_npc.attitude_to_player} attitude towards the player. Their family ties are {closest_npc.family_ties}. Generate a short, in-character dialogue response from {closest_npc.name} to the player. Keep it concise and relevant to their personality and attitude."
                
            llm_dialogue = self._call_ollama(prompt)
            print("\n{}: {}".format(closest_npc.name, llm_dialogue))
        else:
            print("No one to talk to nearby.")

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

    def _generate_chunk_detail(self, chunk: Chunk):
        """Generates the detailed tiles for a chunk based on its biome and POI."""
        if chunk.is_generated: return

        if chunk.poi_type == "village":
            chunk.village = Village()
            # Generate village lore
            prompt = LLM_PROMPTS["village_lore"]
            lore_response = self._call_ollama(prompt)
            print(f"Village Lore: {lore_response}")
            # You might want to store this lore in the chunk.village object
            # chunk.village.lore = lore_response
            
            
            tiles = self._generate_village_layout(chunk)
        else:
            # Generate the base biome tiles
            tiles = [[Tile(TILE_DEFINITIONS[chunk.biome]["char"], TILE_DEFINITIONS[chunk.biome]["color"], TILE_DEFINITIONS[chunk.biome]["passable"], TILE_DEFINITIONS[chunk.biome]["name"]) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

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

    def _generate_trees(self, tiles):
        for y_local in range(CHUNK_SIZE):
            for x_local in range(CHUNK_SIZE):
                if random.random() < 0.02: # 2% chance for a tree
                    tree_type = random.choice(["oak", "apple", "pear"])
                    if tree_type == "oak":
                        tree = OakTree(x_local, y_local)
                    elif tree_type == "apple":
                        tree = AppleTree(x_local, y_local)
                    else:
                        tree = PearTree(x_local, y_local)
                    tiles[y_local][x_local] = tree

    def _generate_village_layout(self, chunk: Chunk):
        tiles = [[Tile(TILE_DEFINITIONS["plains"]["char"], TILE_DEFINITIONS["plains"]["color"], TILE_DEFINITIONS["plains"]["passable"], TILE_DEFINITIONS["plains"]["name"]) for _ in range(CHUNK_SIZE)] for _ in range(CHUNK_SIZE)]

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
        well_x, well_y = road_x, road_y
        tiles[well_y][well_x] = Tile(TILE_DEFINITIONS["well"]["char"], TILE_DEFINITIONS["well"]["color"], TILE_DEFINITIONS["well"]["passable"], TILE_DEFINITIONS["well"]["name"])

        # Generate Capital Hall
        capital_hall_w, capital_hall_h = 9, 7
        capital_hall_x = road_x - capital_hall_w - 2 # To the left of the main road
        capital_hall_y = road_y - capital_hall_h // 2
        capital_hall = Building(capital_hall_x, capital_hall_y, capital_hall_w, capital_hall_h, "capital_hall")
        chunk.village.add_building(capital_hall)
        self._draw_building(tiles, capital_hall, "capital_hall_wall")

        # Generate Jail
        jail_w, jail_h = 7, 5
        jail_x = road_x + 2 # To the right of the main road
        jail_y = road_y - jail_h // 2
        jail = Building(jail_x, jail_y, jail_w, jail_h, "jail")
        chunk.village.add_building(jail)
        self._draw_building(tiles, jail, "jail_bars")

        # Generate Sheriff's Office
        sheriff_office_w, sheriff_office_h = 7, 5
        sheriff_office_x = road_x + 2 # To the right of the main road, below jail
        sheriff_office_y = jail_y + jail_h + 2
        sheriff_office = Building(sheriff_office_x, sheriff_office_y, sheriff_office_w, sheriff_office_h, "sheriff_office")
        chunk.village.add_building(sheriff_office)
        self._draw_building(tiles, sheriff_office, "sheriff_office_wall")

        # Generate a few regular houses
        num_houses = random.randint(3, 5)
        for _ in range(num_houses):
            w, h = random.randint(5, 9), random.randint(5, 9)
            attempts = 0
            while attempts < 100:
                bx = random.randint(1, CHUNK_SIZE - w - 1)
                by = random.randint(1, CHUNK_SIZE - h - 1)

                # Avoid placing on roads or existing buildings
                overlap = False
                for i in range(h):
                    for j in range(w):
                        if tiles[by + i][bx + j].char == TILE_DEFINITIONS["road"]["char"]:
                            overlap = True
                            break
                    if overlap: break
                
                for existing_building in chunk.village.buildings:
                    if not (bx + w < existing_building.x or bx > existing_building.x + existing_building.width or 
                            by + h < existing_building.y or by > existing_building.y + existing_building.height):
                        overlap = True
                        break
                
                if not overlap:
                    break
                attempts += 1
            
            if attempts == 100:
                continue

            house = Building(bx, by, w, h, "house")
            chunk.village.add_building(house)
            self._draw_building(tiles, house, "wood_wall")

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
            tiles[door_y][door_x] = Tile(TILE_DEFINITIONS["door"]["char"], TILE_DEFINITIONS["door"]["color"], TILE_DEFINITIONS["door"]["passable"], TILE_DEFINITIONS["door"]["name"])

    def get_tile_at(self, x, y):
        if not (0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT):
            return None
        chunk_x, chunk_y = x // CHUNK_SIZE, y // CHUNK_SIZE
        local_x, local_y = x % CHUNK_SIZE, y % CHUNK_SIZE
        
        if not (0 <= chunk_x < self.chunk_width and 0 <= chunk_y < self.chunk_height):
            return None

        chunk = self.chunks[chunk_y][chunk_x]
        if not chunk.is_generated:
            self._generate_chunk_detail(chunk)
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
        new_x, new_y = self.player.x + dx, self.player.y + dy
        destination_tile = self.get_tile_at(new_x, new_y)

        if destination_tile and destination_tile.passable:
            self.player.x, self.player.y = new_x, new_y

            # Check if player entered a building
            building = self.get_building_at(new_x, new_y)
            if building and not building.interior_decorated:
                self.decorate_building_interior(building)

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