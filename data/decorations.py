# data/decorations.py
import tcod

# --- Decoration Item Definitions ---
# Note: The 'name' field is added here for the LLM to use when choosing decorations.
# The key of the dictionary (e.g., "wooden_chair") is what the LLM should return in its JSON.
DECORATION_ITEM_DEFINITIONS = {
    "wooden_chair": {
        "name": "Wooden Chair",
        "char": "h",
        "color": tcod.constants.SIENNA, # (160, 82, 45)
        "passable": False,
        "properties": {
            "potential_crafting_materials": {"log": 2}, # Alt: {"wooden_plank": 3}
            "interaction_hint": "sit"
        }
    },
    "wooden_table": {
        "name": "Wooden Table",
        "char": "T",
        "color": tcod.constants.SIENNA, # (160, 82, 45)
        "passable": False, # Typically tables are not passable on their main tile
        "properties": {
            "potential_crafting_materials": {"log": 3}, # Alt: {"wooden_plank": 4}
        }
    },
    "bed_simple": {
        "name": "Simple Bed",
        "char": "b",
        "color": tcod.constants.PERU, # (205, 133, 63)
        "passable": False,
        "properties": {
            "potential_crafting_materials": {"log": 4, "herb_generic": 5},
            "interaction_hint": "sleep"
        }
    },
    "chest_wooden": {
        "name": "Wooden Chest",
        "char": "C",
        "color": tcod.constants.SADDLEBROWN, # (139, 69, 19)
        "passable": False,
        "properties": {
            "potential_crafting_materials": {"log": 3},
            "functional_type": "container", # Hint that it can hold items
            "interaction_hint": "open",     # General interaction
            "is_lockable": True,            # Can it be locked?
            "is_locked": True,              # Default state: locked
            "lock_difficulty": 5,           # Example difficulty (1-10)
            "unlocks_to_reveal": "building_inventory" # What it accesses (conceptual for now)
        }
    },
    "wall_shelf": {
        "name": "Wall Shelf",
        "char": "S",
        "color": tcod.constants.TAN, # (210, 180, 140)
        "passable": True, # Player can walk under it if it's on a wall tile
        "properties": {
            "potential_crafting_materials": {"wooden_plank": 2}
        }
    },
    # --- Keeping some of the old generic ones for variety, or they can be removed/aliased ---
    "bookshelf": {
        "name": "Bookshelf",
        "char": "B", "color": (100, 50, 0), "passable": False,
        "properties": {"potential_crafting_materials": {"wooden_plank": 5}} # Example material
    },
    "fireplace": {
        "name": "Fireplace",
        "char": "F", "color": (150, 50, 0), "passable": False, # Player shouldn't walk into fireplace
        "properties": {
            "potential_crafting_materials": {"stone_chunk": 10, "log": 2}, # Example
            "functional_type": "heat_source", # Example hint
            "interaction_hint": "add_fuel"
        }
    },
    "rug": {
        "name": "Rug",
        "char": "=", "color": (150, 100, 50), "passable": True,
        "properties": {"potential_crafting_materials": {"herb_generic": 10}} # e.g. woven herb rug
    },
    "plant_pot": { # Renamed "plant" to be more specific
        "name": "Potted Plant",
        "char": "p", "color": (34, 139, 34), "passable": False,
        "properties": {"potential_crafting_materials": {"log":1, "herb_generic":1}} # e.g. simple pot and a plant
    },
    "barrel": {
        "name": "Barrel",
        "char": "o", "color": (100, 70, 30), "passable": False,
        "properties": {
            "potential_crafting_materials": {"wooden_plank": 3},
            "functional_type": "container_liquid" # Example
        }
    },
    "crate": {
        "name": "Crate",
        "char": "#", "color": (100, 70, 30), "passable": False,
        "properties": {
            "potential_crafting_materials": {"wooden_plank": 2},
            "functional_type": "container"
        }
    },
    # Removed generic "bed", "table", "chair", "chest" if they are superseded by specific types like "wooden_chair"
    # The LLM prompt will use the new keys.

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
}
