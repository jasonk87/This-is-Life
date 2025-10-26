PROFESSIONS = {
    "Woodcutter": {
        "display_name": "Woodcutter",
        "wage": 20,
        "description": "Chops trees and processes logs into lumber.",
        "work_building_categories": ["Lumber Mill"],
        "sub_tasks": [
            {
                "id": "chop_trees",
                "display_name": "Chopping Trees",
                "duration_ticks": 75, # Average ticks this sub-task takes when at the location
                "target_zone_tag": "chopping_area", # NPC will look for actual tree tiles in this zone/nearby
                "action_verb": "chopping", # For display "Woodcutter is chopping"
                # Output is implicit: a felled tree / logs ready to be hauled
            },
            {
                "id": "haul_logs",
                "display_name": "Hauling Logs",
                "duration_ticks": 20, # Ticks for the action of dropping off logs at the pile
                "target_zone_tag": "log_pile_area", # A designated spot at the lumber mill building
                "action_verb": "depositing logs",
                "consumes_item_from_npc_inventory": {"raw_log": 1}, # Assumes NPC carries 1 log's worth
                "deposits_item_to_workplace": {"raw_log": 1}
            },
            {
                "id": "split_stack_wood",
                "display_name": "Splitting & Stacking Wood",
                "duration_ticks": 60,
                "target_zone_tag": "splitting_area", # Another designated spot
                "action_verb": "splitting wood",
                "consumes_item_from_workplace": {"raw_log": 1}, # Corrected to raw_log
                "produces_item_at_workplace": {"wooden_plank": 1} # Adjusted output to 1 lumber per log
            }
        ],
        "default_sub_task_sequence": ["chop_trees", "haul_logs", "split_stack_wood"]
    },
    "Farmer": {
        "display_name": "Farmer",
        "wage": 15,
        "description": "Cultivates crops and tends to farmland.",
        "work_building_categories": ["Farm"], # Ensure "Farm" is a defined building category/type
        "sub_tasks": [
            {
                "id": "till_soil",
                "display_name": "Tilling Soil",
                "duration_ticks": 50,
                "target_zone_tag": "field_patch", # Farmer will look for 'plains' tiles in this zone
                "action_verb": "tilling soil",
                "target_tile_type_key": "plains", # Tile to look for to perform action on
                "becomes_tile_type_key": "tilled_soil" # Tile it becomes after action
            },
            {
                "id": "plant_seeds",
                "display_name": "Planting Seeds",
                "duration_ticks": 40,
                "target_zone_tag": "field_patch", # Farmer will look for 'tilled_soil' tiles
                "action_verb": "planting seeds",
                "target_tile_type_key": "tilled_soil",
                "becomes_tile_type_key": "mature_wheat_crop", # Direct to mature for now
                "consumes_item_from_workplace": {"wheat_seeds": 1}
            },
            {
                "id": "harvest_crops",
                "display_name": "Harvesting Crops",
                "duration_ticks": 60,
                "target_zone_tag": "field_patch", # Looks for 'mature_wheat_crop'
                "action_verb": "harvesting crops",
                "target_tile_type_key": "mature_wheat_crop",
                # Tile properties will define what it becomes_on_harvest_key and yield
                # This sub-task will trigger that logic in engine.py
                # For simplicity, we can still define a default 'becomes_tile_type_key' if tile doesn't specify
                "becomes_tile_type_key": "tilled_soil",
                 # Actual item production will be based on tile's harvest_yield_item_key and quantity
                "produces_item_at_workplace_from_tile_harvest": True # Special flag
            }
        ],
        "default_sub_task_sequence": ["till_soil", "plant_seeds", "harvest_crops"]
    },
    "Miner": {
        "display_name": "Miner",
        "wage": 25,
        "description": "Extracts ores and minerals from the earth.",
        "work_building_categories": ["Mine"],
        "sub_tasks": [
            {
                "id": "mine_ore",
                "display_name": "Mining Ore",
                "duration_ticks": 100,
                "target_zone_tag": "mine_face",
                "action_verb": "mining"
            },
            {
                "id": "haul_ore",
                "display_name": "Hauling Ore",
                "duration_ticks": 30,
                "target_zone_tag": "storage_area",
                "action_verb": "hauling ore",
                "consumes_item_from_npc_inventory": {"iron_ore": 1},
                "deposits_item_to_workplace": {"iron_ore": 1}
            }
        ],
        "default_sub_task_sequence": ["mine_ore", "haul_ore"]
    },
    "Blacksmith": {
        "display_name": "Blacksmith",
        "wage": 30,
        "description": "Forges tools, weapons, and armor from metal.",
        "work_building_categories": ["blacksmith_shop"],
        "sub_tasks": [
            {
                "id": "fetch_ore",
                "display_name": "Fetching Ore",
                "duration_ticks": 120,
                "target_zone_tag": "mine",
                "action_verb": "fetching ore"
            },
            {
                "id": "smelt_ingot",
                "display_name": "Smelting Ingot",
                "duration_ticks": 150,
                "target_zone_tag": "forge",
                "action_verb": "smelting ingot",
                "consumes_item_from_workplace": {"iron_ore": 2, "coal": 1},
                "produces_item_at_workplace": {"iron_ingot": 1}
            },
            {
                "id": "craft_tool",
                "display_name": "Crafting Tool",
                "duration_ticks": 200,
                "target_zone_tag": "anvil",
                "action_verb": "crafting tool",
                "consumes_item_from_workplace": {"iron_ingot": 1},
                "produces_item_at_workplace": {"axe_stone": 1}
            }
        ],
        "default_sub_task_sequence": ["fetch_ore", "smelt_ingot", "craft_tool"]
    },
    "Merchant": {
        "display_name": "Merchant",
        "wage": 20,
        "description": "Buys and sells goods at a store or market.",
        "work_building_categories": ["General Store", "Market Stall"],
        # Merchants might not have sub-tasks in the same way, their "work" is trading.
        "sub_tasks": [],
        "default_sub_task_sequence": []
    },
    "Lumber Mill Foreman": {
        "display_name": "Lumber Mill Foreman",
        "wage": 25,
        "description": "Manages the operations at the lumber mill.",
        "work_building_categories": ["Lumber Mill"],
        # May have supervisory tasks or also perform some woodcutter tasks. For now, none.
        "sub_tasks": [],
        "default_sub_task_sequence": []
    },
    "Guard": {
        "display_name": "Guard",
        "wage": 20,
        "description": "Maintains peace and order, patrols designated areas.",
        "work_building_categories": ["Guardhouse", "Barracks", "Town Hall"], # Can work out of various places
        "sub_tasks": [
            {"id": "patrol_area", "display_name": "Patrolling", "duration_ticks": 200, "target_zone_tag": "patrol_route", "action_verb": "patrolling"},
            {"id": "stand_guard", "display_name": "Standing Guard", "duration_ticks": 150, "target_zone_tag": "guard_post", "action_verb": "standing guard"}
        ],
        "default_sub_task_sequence": ["patrol_area", "stand_guard"]
    },
    "Sheriff": {
        "display_name": "Sheriff",
        "wage": 35,
        "description": "Upholds the law and manages town security.",
        "work_building_categories": ["Sheriff's Office", "Town Hall"],
        "sub_tasks": [ # Similar to guard but perhaps more investigative or office-based tasks later
            {"id": "patrol_town", "display_name": "Patrolling Town", "duration_ticks": 250, "target_zone_tag": "town_patrol_route", "action_verb": "patrolling"},
            {"id": "office_work", "display_name": "Office Work", "duration_ticks": 180, "target_zone_tag": "office_desk", "action_verb": "doing paperwork"},
            {"id": "arrest_player", "display_name": "Arresting a Criminal", "duration_ticks": 100, "target_zone_tag": "jail_cell", "action_verb": "arresting"}
        ],
        "default_sub_task_sequence": ["patrol_town", "office_work"]
    },
    "Carpenter": {
        "display_name": "Carpenter",
        "wage": 22,
        "description": "Builds and repairs wooden structures and furniture.",
        "work_building_categories": ["Carpenter Shop"],
        "sub_tasks": [
            {"id": "fetch_wood", "display_name": "Fetching Wood", "duration_ticks": 100, "target_zone_tag": "lumber_mill", "action_verb": "fetching wood"},
            {"id": "craft_furniture", "display_name": "Crafting Furniture", "duration_ticks": 200, "target_zone_tag": "workbench", "action_verb": "crafting furniture"}
        ],
        "default_sub_task_sequence": ["fetch_wood", "craft_furniture"]
    },
    "Miller": {
        "display_name": "Miller",
        "wage": 18,
        "description": "Grinds grain into flour.",
        "work_building_categories": ["Mill"],
        "sub_tasks": [
            {
                "id": "fetch_wheat",
                "display_name": "Fetching Wheat",
                "duration_ticks": 120,
                "target_zone_tag": "farm",
                "action_verb": "fetching wheat"
            },
            {
                "id": "mill_flour",
                "display_name": "Milling Flour",
                "duration_ticks": 150,
                "target_zone_tag": "grinding_stone",
                "action_verb": "milling flour",
                "consumes_item_from_workplace": {"wheat": 1},
                "produces_item_at_workplace": {"flour": 1}
            }
        ],
        "default_sub_task_sequence": ["fetch_wheat", "mill_flour"]
    },
    "Baker": {
        "display_name": "Baker",
        "wage": 20,
        "description": "Bakes bread and other goods.",
        "work_building_categories": ["Bakery"],
        "sub_tasks": [
            {
                "id": "fetch_flour",
                "display_name": "Fetching Flour",
                "duration_ticks": 120,
                "target_zone_tag": "mill",
                "action_verb": "fetching flour"
            },
            {
                "id": "bake_bread",
                "display_name": "Baking Bread",
                "duration_ticks": 180,
                "target_zone_tag": "oven",
                "action_verb": "baking bread",
                "consumes_item_from_workplace": {"flour": 1},
                "produces_item_at_workplace": {"bread": 1}
            }
        ],
        "default_sub_task_sequence": ["fetch_flour", "bake_bread"]
    },
    "Tavern Keeper": {
        "display_name": "Tavern Keeper",
        "wage": 25,
        "description": "Runs the local tavern, serving drinks and food.",
        "work_building_categories": ["Tavern"],
        "sub_tasks": [],
        "default_sub_task_sequence": []
    },
    "Cook": {
        "display_name": "Cook",
        "wage": 22,
        "description": "Prepares meals for the village.",
        "work_building_categories": ["Tavern"],
        "sub_tasks": [
            {
                "id": "fetch_fish",
                "display_name": "Fetching Fish",
                "action_verb": "fetching fish from",
                "duration_ticks": 100,
                "target_zone_tag": "fishing_hut"
            },
            {
                "id": "store_raw_ingredients",
                "display_name": "Storing Ingredients",
                "action_verb": "storing ingredients in",
                "duration_ticks": 20,
                "target_zone_tag": "kitchen_storage",
                "consumes_item_from_npc_inventory": {"raw_fish": 1},
                "deposits_item_to_workplace": {"raw_fish": 1}
            },
            {
                "id": "cook_fish_meal",
                "display_name": "Cooking Fish",
                "action_verb": "cooking at",
                "duration_ticks": 120,
                "target_zone_tag": "cooking_station",
                "consumes_item_from_workplace": {"raw_fish": 1},
                "produces_item_at_workplace": {"cooked_fish": 1}
            }
        ],
        "default_sub_task_sequence": ["fetch_fish", "store_raw_ingredients", "cook_fish_meal"]
    },
    "Fisherman": {
        "display_name": "Fisherman",
        "wage": 18,
        "description": "Catches fish to supply the village.",
        "work_building_categories": ["Fishing Hut"],
        "sub_tasks": [
            {
                "id": "fish_at_spot",
                "display_name": "Fishing",
                "action_verb": "fishing at",
                "duration_ticks": 150,
                "target_zone_tag": "fishing_spot"
            },
            {
                "id": "store_fish",
                "display_name": "Storing Fish",
                "action_verb": "storing fish in",
                "duration_ticks": 20,
                "target_zone_tag": "storage_area",
                "consumes_item_from_npc_inventory": {"raw_fish": 1},
                "deposits_item_to_workplace": {"raw_fish": 1}
            }
        ],
        "default_sub_task_sequence": ["fish_at_spot", "store_fish"]
    },
    "Town Official": {
        "display_name": "Town Official",
        "wage": 40,
        "description": "Manages the civic duties of a settlement.",
        "work_building_categories": ["Town Hall", "Capital Hall"],
        "sub_tasks": [],
        "default_sub_task_sequence": []
    },
    "Traveling Merchant": {
        "display_name": "Traveling Merchant",
        "wage": 0, # They earn money by trading
        "description": "Travels between towns to buy and sell goods.",
        "work_building_categories": [], # No fixed workplace
        "sub_tasks": [],
        "default_sub_task_sequence": []
    },
    "Unemployed": {
        "display_name": "Unemployed",
        "wage": 0,
        "description": "Currently without a formal job.",
        "work_building_categories": [],
        "sub_tasks": [],
        "default_sub_task_sequence": []
    },
    "Scribe": {
        "display_name": "Scribe",
        "wage": 28,
        "description": "Records historical events, maintains the town census, and authors books.",
        "work_building_categories": ["Library"],
        "sub_tasks": [
            {
                "id": "write_book",
                "display_name": "Writing a Book",
                "action_verb": "writing at",
                "duration_ticks": 5000,
                "target_zone_tag": "writing_desk"
            }
        ],
        "default_sub_task_sequence": ["write_book"]
    }
}

# Helper function to get profession details
def get_profession_data(profession_name: str) -> dict | None:
    return PROFESSIONS.get(profession_name)

def get_sub_task_data(profession_name: str, sub_task_id: str) -> dict | None:
    profession = get_profession_data(profession_name)
    if profession and "sub_tasks" in profession:
        for sub_task in profession["sub_tasks"]:
            if sub_task["id"] == sub_task_id:
                return sub_task
    return None

# Example of items that might be produced/consumed by sub-tasks
# These would ideally be more centrally defined with other items
# For now, just listing them as concepts for the sub-task definitions
"""
ITEM_DEFINITIONS_EXPANDED = {
    "log_raw": {"display_name": "Raw Log", "value": 2, "type": "resource"},
    "lumber_processed": {"display_name": "Processed Lumber", "value": 5, "type": "resource", "craftable_good": True},
    "wheat_sheaf": {"display_name": "Sheaf of Wheat", "value": 1, "type": "resource"},
    "flour_bag": {"display_name": "Bag of Flour", "value": 3, "type": "resource", "craftable_good": True},
    "iron_ore_chunk": {"display_name": "Iron Ore Chunk", "value": 3, "type": "resource"},
    "iron_ingot": {"display_name": "Iron Ingot", "value": 8, "type": "resource", "craftable_good": True},
}
"""
