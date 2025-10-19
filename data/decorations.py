# data/decorations.py
import tcod

# --- Decoration Item Definitions ---
# Note: The 'name' field is added here for the LLM to use when choosing decorations.
# The key of the dictionary (e.g., "wooden_chair") is what the LLM should return in its JSON.
DECORATION_ITEM_DEFINITIONS = {
    "wooden_chair": {
        "name": "Wooden Chair",
        "char": "h",
        "color": tcod.constants.SIENNA,
        "passable": False,
        "properties": {"interaction_hint": "sit", "blocks_fov": False},
        "placement_cost": {"wooden_plank": 2}
    },
    "wooden_table": {
        "name": "Wooden Table",
        "char": "T",
        "color": tcod.constants.SIENNA,
        "passable": False,
        "properties": {"blocks_fov": False}, # Low table
        "placement_cost": {"wooden_plank": 3}
    },
    "bed_simple": {
        "name": "Simple Bed",
        "char": "b",
        "color": tcod.constants.PERU,
        "passable": False,
        "properties": {"interaction_hint": "sleep", "blocks_fov": False}, # Bed is low
        "placement_cost": {"wooden_plank": 4, "herb_generic": 3} # Herb for stuffing
    },
    "chest_wooden": {
        "name": "Wooden Chest",
        "char": "C",
        "color": tcod.constants.SADDLEBROWN,
        "passable": False,
        "properties": {
            "functional_type": "container",
            "interaction_hint": "open",
            "is_lockable": True,            # Can it be locked?
            "is_locked": True,              # Default state: locked
            "lock_difficulty": 5,           # Example difficulty (1-10)
            "unlocks_to_reveal": "building_inventory", # What it accesses (conceptual for now)
            "blocks_fov": True # Chests are solid
        },
        "placement_cost": {"wooden_plank": 3, "raw_log": 1} # Logs for sturdier frame
    },
    "wall_shelf": {
        "name": "Wall Shelf",
        "char": "S",
        "color": tcod.constants.TAN,
        "passable": True,
        "properties": {"blocks_fov": False}, # Usually small and high
        "placement_cost": {"wooden_plank": 1}
    },
    "bookshelf": {
        "name": "Bookshelf",
        "char": "B", "color": (100, 50, 0), "passable": False,
        "properties": {"blocks_fov": True}, # Tall bookshelf blocks view
        "placement_cost": {"wooden_plank": 5}
    },
    "fireplace": { # This is more of a built-in structure, less for player placement yet
        "name": "Fireplace",
        "char": "F", "color": (150, 50, 0), "passable": False,
        "properties": {
            "functional_type": "heat_source",
            "interaction_hint": "add_fuel",
            "blocks_fov": False # Fire itself doesn't block, but structure might
        }
        # No placement_cost for now as it's usually part of initial building gen by LLM
    },
    "rug": {
        "name": "Rug",
        "char": "=", "color": (150, 100, 50), "passable": True,
        "properties": {"blocks_fov": False},
        "placement_cost": {"herb_generic": 5}
    },
    "plant_pot": {
        "name": "Potted Plant",
        "char": "p", "color": (34, 139, 34), "passable": False,
        "properties": {"blocks_fov": False},
        "placement_cost": {"raw_log":1, "herb_generic":1}
    },
    "barrel": {
        "name": "Barrel",
        "char": "o", "color": (100, 70, 30), "passable": False,
        "properties": {
            "functional_type": "container_liquid",
            "blocks_fov": True
        },
        "placement_cost": {"wooden_plank": 3}
    },
    "crate": {
        "name": "Crate",
        "char": "#", "color": (100, 70, 30), "passable": False,
        "properties": {
            "functional_type": "container",
            "blocks_fov": True
        },
        "placement_cost": {"wooden_plank": 2}
    },

    # --- Doors ---
    "wooden_door_closed": {
        "name": "Wooden Door (Closed)", # Name for LLM if it ever places doors explicitly
        "char": "D",
        "color": tcod.constants.SADDLEBROWN,
        "passable": False,
        "properties": {
            "is_door": True,
            "is_open": False,
            "opens_to": "wooden_door_open", # Key of the open state
            "description": "A closed wooden door."
        }
    },
    "wooden_door_open": {
        "name": "Wooden Door (Open)",
        "char": "/",
        "color": tcod.constants.SADDLEBROWN,
        "passable": True,
        "properties": {
            "is_door": True,
            "is_open": True,
            "closes_to": "wooden_door_closed", # Key of the closed state
            "description": "An open wooden door."
        }
    },
    # --- Combat Related ---
    "corpse_humanoid": {
        "name": "Lifeless Body",
        "char": "%",
        "color": tcod.constants.DARK_RED,
        "passable": True, # Usually can walk over corpses
        "properties": {
            "is_corpse": True,
            "description": "The still form of a humanoid."
            # Future: could store original NPC ID or type for looting/identification
        }
    },
    "fire_pit_simple": {
        "name": "Simple Fire Pit",
        "char": "F", # Using existing fireplace char, can differentiate later
        "color": tcod.constants.DARK_ORANGE, # Ashy/ember color
        "passable": False, # Don't walk into the fire pit
        "properties": {
            "is_heat_source": True,
            "interaction_hint": "cook_here", # For conceptual crafting station
            "description": "A ring of stones containing embers. Good for cooking.",
            "blocks_fov": False # Low to the ground
        },
        "placement_cost": {"stone_chunk": 5}
    }
}
