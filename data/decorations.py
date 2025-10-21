# data/decorations.py
from data.tiles import COLORS

DECORATION_ITEM_DEFINITIONS = {
    # --- Doors ---
    "wooden_door_closed": {
        "name": "Wooden Door",
        "description": "A closed wooden door.",
        "char": "+",
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
        "char": "-",
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
        "char": "C",
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
        "char": "B",
        "color": COLORS["tan"],
        "passable": True, # Can walk over it, maybe? Or treat as non-passable? Let's say passable for now.
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture"],
        "properties": {
            "interaction_hint": "sleep"
        }
    },
    # More to be added by agent...
    "wooden_chair": {
        "name": "Wooden Chair",
        "description": "A simple wooden chair.",
        "char": "h",
        "color": COLORS["saddlebrown"],
        "passable": True,
        "blocks_fov": False,
        "item_type_tags": ["interactable", "furniture"],
        # No placement_cost for now as it's usually part of initial building gen by LLM
        "properties": {
            "interaction_hint": "sit"
        }
    },
     "wooden_table": {
        "name": "Wooden Table",
        "description": "A sturdy wooden table.",
        "char": "T",
        "color": COLORS["saddlebrown"],
        "passable": False, # Can't walk through a table
        "blocks_fov": False,
        "item_type_tags": ["furniture"],
        "properties": {}
    },
    "wall_shelf": {
        "name": "Wall Shelf",
        "description": "A simple shelf mounted on the wall.",
        "char": "=",
        "color": COLORS["saddlebrown"],
        "passable": True, # Placed on a wall tile, so this doesn't matter much
        "blocks_fov": False,
        "item_type_tags": ["furniture", "container"], # Can conceptually hold things
        "properties": {}
    },
    "fire_pit_simple": {
        "name": "Simple Fire Pit",
        "description": "A ring of stones for a small fire.",
        "char": "o",
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
        "char": "O",
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
            "heat_intensity": 25.0
        }
    },
    "corpse_humanoid": {
        "name": "Corpse",
        "description": "The remains of a humanoid.",
        "char": "%",
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
        "char": "+",
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
        "char": "'",
        "color": COLORS["dark_slate_gray"],
        "passable": True,
        "name": "Open Iron Door",
        "properties": {
            "is_door": True,
            "is_open": True,
            "closes_to": "iron_door_closed",
            "blocks_fov": False
        }
    }
}
