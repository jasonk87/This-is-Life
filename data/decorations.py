"""
This file defines the properties of all decorations and interactable objects in the game.
"""
from data.dawnlike import WORLD_DECORATION_SPRITES
from data.tiles import COLORS

DECORATION_ITEM_DEFINITIONS = {
    # --- Doors ---
    "wooden_door_closed": {
        "name": "Wooden Door",
        "description": "A closed wooden door.",
        "char": WORLD_DECORATION_SPRITES["wooden_door_closed"],
        "color": COLORS["sienna"],
        "passable": False, # Closed door
        "blocks_fov": True,
        "item_type_tags": ["interactable", "door"],
        "properties": {
            "is_door": True,
            "is_open": False,
            "opens_to": "wooden_door_open"
        }
    },
    "wooden_door_open": {
        "name": "Open Wooden Door",
        "description": "An open wooden door.",
        "char": WORLD_DECORATION_SPRITES["wooden_door_open"],
        "color": COLORS["sienna"],
        "passable": True, # Open door
        "blocks_fov": False,
        "item_type_tags": ["interactable", "door"],
        "properties": {
            "is_door": True,
            "is_open": True,
            "closes_to": "wooden_door_closed"
        }
    },
    # --- Furniture ---
    "chest_wooden": {
        "name": "Wooden Chest",
        "description": "A simple wooden chest for storage.",
        "char": WORLD_DECORATION_SPRITES["chest_wooden"],
        "color": COLORS["saddlebrown"],
        "passable": False,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "container", "furniture"],
        "properties": {
            "is_lockable": True,
            "is_locked": True, # Starts locked
            "lock_difficulty": 3, # On a scale of 1-10
            "unlocks_to_reveal": "building_inventory", # What it accesses (conceptual for now)
            "interaction_hint": "open"
        }
    },
    "bed_simple": {
        "name": "Simple Bed",
        "description": "A simple bed with a straw mattress.",
        "char": WORLD_DECORATION_SPRITES["bed_simple"],
        "color": COLORS["tan"],
        # Can walk over it, maybe? Or treat as non-passable? Let's say passable for now.
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture"],
        "properties": {
            "interaction_hint": "sleep"
        }
    },
    "wooden_chair": {
        "name": "Wooden Chair",
        "description": "A simple wooden chair.",
        "char": WORLD_DECORATION_SPRITES["wooden_chair"],
        "color": COLORS["saddlebrown"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture"],
        # No placement_cost for now as it's usually part of initial building gen by LLM
        "properties": {
            "interaction_hint": "sit"
        }
    },
    "workbench": {
        "name": "Workbench",
        "description": "A bench for crafting items.",
        "char": WORLD_DECORATION_SPRITES["workbench"],
        "color": COLORS["dark_orange"],
        "passable": False,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture", "workstation"],
        "properties": {
            "workstation_type": "workbench"
        }
    },
    "forge": {
        "name": "Forge",
        "description": "A hearth for heating metal.",
        "char": WORLD_DECORATION_SPRITES["forge"],
        "color": COLORS["dark_orange"],
        "passable": False,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture", "workstation"],
        "properties": {
            "workstation_type": "forge"
        }
    },
    "anvil": {
        "name": "Anvil",
        "description": "A heavy iron block for shaping metal.",
        "char": WORLD_DECORATION_SPRITES["anvil"],
        "color": COLORS["dark_slate_gray"],
        "passable": False,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture", "workstation"],
        "properties": {
            "workstation_type": "anvil"
        }
    },
    "loom": {
        "name": "Loom",
        "description": "A device for weaving thread into cloth.",
        "char": WORLD_DECORATION_SPRITES["loom"],
        "color": COLORS["saddlebrown"],
        "passable": False,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture", "workstation"],
        "properties": {
            "workstation_type": "loom"
        }
    },
    "smoking_rack": {
        "name": "Smoking Rack",
        "description": "A wooden rack for smoking meat and fish.",
        "char": WORLD_DECORATION_SPRITES["smoking_rack"],
        "color": COLORS["saddlebrown"],
        "passable": False,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture", "workstation"],
        "properties": {
            "workstation_type": "smoking_rack",
            "interaction_hint": "smoke"
        }
    },
     "wooden_table": {
        "name": "Wooden Table",
        "description": "A sturdy wooden table.",
        "char": WORLD_DECORATION_SPRITES["wooden_table"],
        "color": COLORS["saddlebrown"],
        "passable": False, # Can't walk through a table
        "blocks_fov": False,
        "item_type_tags": ["furniture"],
        "properties": {}
    },
    "wall_shelf": {
        "name": "Wall Shelf",
        "description": "A simple shelf mounted on the wall.",
        "char": WORLD_DECORATION_SPRITES["wall_shelf"],
        "color": COLORS["saddlebrown"],
        "passable": True, # Placed on a wall tile, so this doesn't matter much
        "blocks_fov": False,
        "item_type_tags": ["furniture", "container"], # Can conceptually hold things
        "properties": {}
    },
    "fire_pit_simple": {
        "name": "Simple Fire Pit",
        "description": "A ring of stones for a small fire.",
        "char": WORLD_DECORATION_SPRITES["fire_pit_simple"],
        "color": COLORS["grey"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "light_source_potential"],
        "properties": {
            "interaction_hint": "light_fire",
            "becomes_lit": "fire_pit_lit"
        }
    },
    "fire_pit_lit": {
        "name": "Lit Fire Pit",
        "description": "A crackling fire burns brightly.",
        "char": WORLD_DECORATION_SPRITES["fire_pit_lit"],
        "color": COLORS["flame"],
        "passable": False,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "light_source_active", "heat_source"],
        "properties": {
            "heat_source": True,
            "is_lit": True,
            "light_radius": 5,
            "extinguishes_to": "fire_pit_simple",
            "heat_source_radius": 4,
            "heat_intensity": 25.0,
            "workstation_type": "fire"
        }
    },
    "corpse_humanoid": {
        "name": "Corpse",
        "description": "The remains of a humanoid.",
        "char": WORLD_DECORATION_SPRITES["corpse_humanoid"],
        "color": COLORS["dark_sepia"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["corpse", "container"], # Can be looted
        "properties": {
            "interaction_hint": "loot",
            "decay_timer": 500 # Ticks until it disappears or turns to skeleton
        }
    },
    "iron_door_closed": {
        "char": WORLD_DECORATION_SPRITES["iron_door_closed"],
        "color": COLORS["dark_slate_gray"],
        "passable": False,
        "name": "Iron Door",
        "properties": {
            "is_door": True,
            "is_open": False,
            "opens_to": "iron_door_open",
            "is_lockable": True,
            "is_locked": True,
            "lock_difficulty": 7,
            "blocks_fov": True
        }
    },
    "iron_door_open": {
        "char": WORLD_DECORATION_SPRITES["iron_door_open"],
        "color": COLORS["dark_slate_gray"],
        "passable": True,
        "name": "Open Iron Door",
        "properties": {
            "is_door": True,
            "is_open": True,
            "closes_to": "iron_door_closed",
            "blocks_fov": False
        }
    },
    "rubble": {
        "name": "Rubble",
        "description": "A pile of fallen stones.",
        "char": WORLD_DECORATION_SPRITES["rubble"],
        "color": COLORS["grey"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["obstacle"],
        "properties": {"movement_cost": 2}
    },
    "corpse_animal": {
        "name": "Animal Corpse",
        "description": "The remains of an animal.",
        "char": WORLD_DECORATION_SPRITES["corpse_animal"],
        "color": COLORS["dark_sepia"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["corpse", "container"],
        "properties": {
            "interaction_hint": "butcher",
            "decay_timer": 300
        }
    },
    "bones": {
        "name": "Bones",
        "description": "A pile of bones.",
        "char": WORLD_DECORATION_SPRITES["bones"],
        "color": (245, 245, 220),
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["remains"],
        "properties": {
            "decay_timer": 1000
        }
    },
    "bookshelf": {
        "name": "Bookshelf",
        "description": "A wooden bookshelf filled with various tomes.",
        "char": WORLD_DECORATION_SPRITES["bookshelf"],
        "color": COLORS["saddlebrown"],
        "passable": False,
        "blocks_fov": True,
        "item_type_tags": ["interactable", "furniture", "container"],
        "properties": {
            "interaction_hint": "read"
        }
    },
    # --- Animal Dens ---
    "wolf_den": {
        "name": "Wolf Den",
        "description": "A dark cave entrance surrounded by bones.",
        "char": WORLD_DECORATION_SPRITES["wolf_den"],
        "color": COLORS["darkest_grey"],
        "passable": False,
        "blocks_fov": True,
        "item_type_tags": ["den", "spawner"],
        "properties": {
            "spawn_type": "wolf",
            "max_population": 5,
            "spawn_rate": 0.001
        }
    },
    "rabbit_hole": {
        "name": "Rabbit Hole",
        "description": "A small burrow in the ground.",
        "char": WORLD_DECORATION_SPRITES["rabbit_hole"],
        "color": COLORS["sienna"],
        "passable": True, # Small enough to walk over
        "blocks_fov": False,
        "item_type_tags": ["den", "spawner"],
        "properties": {
            "spawn_type": "rabbit",
            "max_population": 10,
            "spawn_rate": 0.005
        }
    },
    "bear_cave": {
        "name": "Bear Cave",
        "description": "A large, ominous cave entrance.",
        "char": WORLD_DECORATION_SPRITES["bear_cave"],
        "color": COLORS["saddlebrown"],
        "passable": False,
        "blocks_fov": True,
        "item_type_tags": ["den", "spawner"],
        "properties": {
            "spawn_type": "bear",
            "max_population": 2,
            "spawn_rate": 0.0005
        }
    },
    "fox_burrow": {
        "name": "Fox Burrow",
        "description": "A hidden den beneath roots.",
        "char": WORLD_DECORATION_SPRITES["fox_burrow"],
        "color": COLORS["dark_orange"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["den", "spawner"],
        "properties": {
            "spawn_type": "fox",
            "max_population": 3,
            "spawn_rate": 0.002
        }
    },
    "badger_sett": {
        "name": "Badger Sett",
        "description": "A complex of holes dug by badgers.",
        "char": WORLD_DECORATION_SPRITES["badger_sett"],
        "color": COLORS["grey"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["den", "spawner"],
        "properties": {
            "spawn_type": "badger",
            "max_population": 4,
            "spawn_rate": 0.002
        }
    },
    "thicket": {
        "name": "Dense Thicket",
        "description": "A dense patch of bushes where animals hide.",
        "char": WORLD_DECORATION_SPRITES["thicket"],
        "color": COLORS["forest_fg"],
        "passable": True, # Difficult terrain
        "blocks_fov": True,
        "item_type_tags": ["den", "spawner"],
        "properties": {
            "spawn_type": "deer", # Or boar
            "max_population": 6,
            "spawn_rate": 0.003,
            "movement_cost": 2
        }
    }
}
