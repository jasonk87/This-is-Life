"""
This file defines the properties of all NPC professions in the game.
"""
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
                # Average ticks this sub-task takes when at the location
                "duration_ticks": 75,
                "target_zone_tag": "chopping_area",
                "action_verb": "chopping",
            },
            {
                "id": "haul_logs",
                "display_name": "Hauling Logs",
                "duration_ticks": 20,
                "target_zone_tag": "log_pile_area",
                "action_verb": "depositing logs",
                "consumes_item_from_npc_inventory": {"raw_log": 1},
                "deposits_item_to_workplace": {"raw_log": 1}
            },
            {
                "id": "split_stack_wood",
                "display_name": "Splitting & Stacking Wood",
                "duration_ticks": 60,
                "target_zone_tag": "splitting_area",
                "action_verb": "splitting wood",
                "consumes_item_from_workplace": {"raw_log": 1},
                "produces_item_at_workplace": {"wooden_plank": 1}
            }
        ],
        "default_sub_task_sequence": ["chop_trees", "haul_logs", "split_stack_wood"]
    },
    "Farmer": {
        "display_name": "Farmer",
        "wage": 15,
        "description": "Cultivates crops and tends to farmland.",
        "work_building_categories": ["Farm"],
        "sub_tasks": [
            {
                "id": "till_soil",
                "display_name": "Tilling Soil",
                "duration_ticks": 50,
                "target_zone_tag": "field_patch",
                "action_verb": "tilling soil",
                "target_tile_type_key": "plains",
                "becomes_tile_type_key": "tilled_soil"
            },
            {
                "id": "plant_seeds",
                "display_name": "Planting Seeds",
                "duration_ticks": 40,
                "target_zone_tag": "field_patch",
                "action_verb": "planting seeds",
                "target_tile_type_key": "tilled_soil",
                "becomes_tile_type_key": "mature_wheat_crop",
                "consumes_item_from_workplace": {"wheat_seeds": 1}
            },
            {
                "id": "harvest_crops",
                "display_name": "Harvesting Crops",
                "duration_ticks": 60,
                "target_zone_tag": "field_patch",
                "action_verb": "harvesting crops",
                "target_tile_type_key": "mature_wheat_crop",
                "becomes_tile_type_key": "tilled_soil",
                "produces_item_at_workplace_from_tile_harvest": True
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
            },
            {
                # Coal had no source anywhere in the game. It is consumed by
                # exactly one thing - the blacksmith's smelt_ingot, one lump per
                # ingot - and produced by nothing: no work step, no recipe, no
                # tile. The world's entire supply was the 10-25 lumps seeded into
                # each blacksmith shop at generation, about 60 in total, and once
                # those were burnt smelting stopped for good.
                #
                # Measured over two simulated days: iron ore climbed 154 -> 291
                # as miners kept digging, while ingots fell 36 -> 46 -> 1 as the
                # last coal ran out and smiths went on spending ingots making
                # tools. Every iron item downstream - sword, breastplate, shears,
                # helmet, anvil - becomes permanently unmakeable at that point.
                #
                # A mine is where coal comes from, so the miners dig it. Deposits
                # straight to the mine's stores, which is where the blacksmith's
                # fetch_coal buys it, the same way the miller buys wheat from the
                # farm and the baker buys flour from the mill.
                # Stone had the same hole coal did: consumed by four
                # construction recipes and by the forge, produced by nothing.
                # The world's whole supply was what generation seeded into mines
                # and smithies, so once a settlement had built its clinic and its
                # fire pits there was no more stone, ever. A mine is where stone
                # comes from too.
                "id": "mine_stone",
                "display_name": "Cutting Stone",
                "duration_ticks": 100,
                "target_zone_tag": "mine_face",
                "action_verb": "cutting stone",
                "produces_item_at_workplace": {"stone_chunk": 1}
            },
            {
                "id": "mine_coal",
                "display_name": "Mining Coal",
                "duration_ticks": 100,
                "target_zone_tag": "mine_face",
                "action_verb": "mining coal",
                "produces_item_at_workplace": {"coal": 1}
            }
        ],
        "default_sub_task_sequence": ["mine_ore", "haul_ore", "mine_coal", "mine_stone"]
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
                # Smelting burns a lump per ingot and the shop's seeded supply is
                # finite, so a smith has to restock. Mirrors fetch_wheat and
                # fetch_flour: buy from the supplier and deposit into the shop,
                # because smelt_ingot consumes from the workplace rather than
                # from the smith's pockets.
                "id": "fetch_coal",
                "display_name": "Fetching Coal",
                "duration_ticks": 120,
                "target_zone_tag": "mine",
                "action_verb": "fetching coal"
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
        "default_sub_task_sequence": ["fetch_ore", "fetch_coal", "smelt_ingot", "craft_tool"]
    },
    "Merchant": {
        "display_name": "Merchant",
        "wage": 20,
        "description": "Buys and sells goods at a store or market.",
        "work_building_categories": ["General Store", "Market Stall", "general_store"],
        "sub_tasks": [
            {"id": "tend_counter", "display_name": "Tending Counter", "duration_ticks": 100, "target_zone_tag": "counter", "action_verb": "tending counter"},
            {"id": "organize_shelves", "display_name": "Organizing Shelves", "duration_ticks": 60, "target_zone_tag": "shelves", "action_verb": "organizing goods"},
            {"id": "inspect_crates", "display_name": "Inspecting Inventory", "duration_ticks": 50, "target_zone_tag": "crates", "action_verb": "counting inventory"},
            {"id": "sweep_shop", "display_name": "Sweeping Floor", "duration_ticks": 40, "target_zone_tag": "storefront", "action_verb": "sweeping"}
        ],
        "default_sub_task_sequence": ["tend_counter", "organize_shelves", "inspect_crates", "sweep_shop"]
    },
    "Lumber Mill Foreman": {
        "display_name": "Lumber Mill Foreman",
        "wage": 25,
        "description": "Manages the operations at the lumber mill.",
        "work_building_categories": ["Lumber Mill", "lumber_mill"],
        # The foreman ran the mill and did nothing.
        #
        # This was one of only three professions with no work defined at all -
        # the other two being Traveling Merchant and Unemployed, which do not
        # need any. Measured over three thousand ticks, every foreman in the
        # world completed zero steps and stood at their mill for the whole run.
        #
        # What they do now closes a chain that was open at both ends.
        # lumber_processed - "smooth, processed lumber, ready for fine
        # construction" - was defined and priced, and was produced by nothing
        # and consumed by nothing: dead weight in the item table. A mill is
        # where rough planks become finished timber, so that is the foreman's
        # trade, and the carpenter now has something to do with the result.
        #
        # Timber runs log -> plank -> processed lumber -> fine furniture, over
        # three trades and two buildings.
        "sub_tasks": [
            {"id": "sort_timber", "display_name": "Sorting Timber",
             "duration_ticks": 40, "target_zone_tag": "log_pile_area",
             "action_verb": "sorting timber"},
            {"id": "mill_lumber", "display_name": "Milling Lumber",
             "duration_ticks": 90, "target_zone_tag": "splitting_area",
             "action_verb": "milling lumber",
             "consumes_item_from_workplace": {"wooden_plank": 2},
             "produces_item_at_workplace": {"lumber_processed": 1}},
            {"id": "tally_stock", "display_name": "Tallying Stock",
             "duration_ticks": 50, "target_zone_tag": "manager_spot",
             "action_verb": "tallying stock"}
        ],
        "default_sub_task_sequence": ["sort_timber", "mill_lumber", "tally_stock"]
    },
    "Guard": {
        "display_name": "Guard",
        "wage": 20,
        "description": "Maintains peace and order, patrols designated areas.",
        "work_building_categories": ["Guardhouse", "Barracks", "Town Hall"],
        "sub_tasks": [
            {"id": "patrol_area", "display_name": "Patrolling", "duration_ticks": 120,
             "target_zone_tag": "patrol_route", "action_verb": "patrolling"},
            {"id": "stand_guard", "display_name": "Standing Guard", "duration_ticks": 90,
             "target_zone_tag": "guard_post", "action_verb": "standing guard"}
        ],
        "default_sub_task_sequence": ["patrol_area", "stand_guard"]
    },
    "Sheriff": {
        "display_name": "Sheriff",
        "wage": 35,
        "description": "Upholds the law and manages town security.",
        "work_building_categories": ["Sheriff's Office", "Town Hall", "sheriff_office"],
        "sub_tasks": [
            {"id": "patrol_town", "display_name": "Patrolling Town", "duration_ticks": 150,
             "target_zone_tag": "town_patrol_route", "action_verb": "patrolling"},
            {"id": "office_work", "display_name": "Office Work", "duration_ticks": 100,
             "target_zone_tag": "office_desk", "action_verb": "doing paperwork"},
            {"id": "arrest_player", "display_name": "Arresting a Criminal",
             "duration_ticks": 80, "target_zone_tag": "jail_cell", "action_verb": "arresting"}
        ],
        "default_sub_task_sequence": ["patrol_town", "office_work"]
    },
    "Deputy": {
        "display_name": "Deputy",
        "wage": 25,
        "description": "Assists the Sheriff with patrols and law enforcement.",
        "work_building_categories": ["Sheriff's Office", "Town Hall", "sheriff_office"],
        "sub_tasks": [
            {"id": "patrol_town", "display_name": "Patrolling Streets", "duration_ticks": 120,
             "target_zone_tag": "town_patrol_route", "action_verb": "patrolling"},
            {"id": "stand_guard", "display_name": "Station Guard", "duration_ticks": 90,
             "target_zone_tag": "guard_post", "action_verb": "standing watch"}
        ],
        "default_sub_task_sequence": ["patrol_town", "stand_guard"]
    },
    "Militia": {
        "display_name": "Militia",
        "wage": 18,
        "description": "Volunteer citizen soldier defending the settlement.",
        "work_building_categories": ["Guardhouse", "Barracks", "Town Hall"],
        "sub_tasks": [
            {"id": "patrol_area", "display_name": "Patrolling Perimeter", "duration_ticks": 120,
             "target_zone_tag": "patrol_route", "action_verb": "patrolling"},
            {"id": "stand_guard", "display_name": "Watch Duty", "duration_ticks": 90,
             "target_zone_tag": "guard_post", "action_verb": "standing watch"}
        ],
        "default_sub_task_sequence": ["patrol_area", "stand_guard"]
    },
    "Carpenter": {
        "display_name": "Carpenter",
        "wage": 22,
        "description": "Builds and repairs wooden structures and furniture.",
        "work_building_categories": ["Carpenter Shop"],
        "sub_tasks": [
            {"id": "fetch_wood", "display_name": "Fetching Wood", "duration_ticks": 80,
             "target_zone_tag": "lumber_mill", "action_verb": "fetching wood"},
            {"id": "craft_furniture", "display_name": "Crafting Furniture",
             "duration_ticks": 120, "target_zone_tag": "workbench",
             "action_verb": "crafting furniture"},
            # Gives the mill's processed lumber somewhere to go, so the
            # foreman's output is not simply another item nothing wants.
            {"id": "craft_fine_furniture", "display_name": "Crafting Fine Furniture",
             "duration_ticks": 220, "target_zone_tag": "workbench",
             "action_verb": "crafting fine furniture",
             "consumes_item_from_workplace": {"lumber_processed": 1},
             "produces_item_at_workplace": {"wooden_table": 1}}
        ],
        "default_sub_task_sequence": ["fetch_wood", "craft_furniture", "craft_fine_furniture"]
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
                "duration_ticks": 80,
                "target_zone_tag": "farm",
                "action_verb": "fetching wheat"
            },
            {
                "id": "mill_flour",
                "display_name": "Milling Flour",
                "duration_ticks": 100,
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
                "duration_ticks": 80,
                "target_zone_tag": "mill",
                "action_verb": "fetching flour"
            },
            {
                "id": "bake_bread",
                "display_name": "Baking Bread",
                "duration_ticks": 120,
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
        "work_building_categories": ["Tavern", "tavern"],
        "sub_tasks": [
            {"id": "tend_bar", "display_name": "Tending Bar", "duration_ticks": 90, "target_zone_tag": "counter", "action_verb": "pouring drinks"},
            {"id": "clean_tables", "display_name": "Wiping Tables", "duration_ticks": 50, "target_zone_tag": "tables", "action_verb": "cleaning tables"},
            {"id": "restock_cellar", "display_name": "Checking Kegs", "duration_ticks": 60, "target_zone_tag": "cellar", "action_verb": "checking supplies"},
            {"id": "chat_patrons", "display_name": "Greeting Guests", "duration_ticks": 60, "target_zone_tag": "patron_area", "action_verb": "chatting with guests"}
        ],
        "default_sub_task_sequence": ["tend_bar", "clean_tables", "restock_cellar", "chat_patrons"]
    },
    "Hunter": {
        "display_name": "Hunter",
        "wage": 22,
        "description": "Hunts wild animals and scouts the wilderness.",
        "work_building_categories": ["Hunter's Lodge", "Town Hall"], # Or no fixed building
        "sub_tasks": [
            {
                "id": "hunt_animals",
                "display_name": "Hunting",
                "duration_ticks": 300,
                "target_zone_tag": "wilderness",
                "action_verb": "hunting"
            },
            {
                "id": "butcher_carcass",
                "display_name": "Butchering",
                "duration_ticks": 100,
                "target_zone_tag": "corpse", # Special tag to find nearest corpse
                "action_verb": "butchering",
                # No direct production here, handled by special logic in _produce_sub_task_output due to variable drops
            },
            {
                "id": "deposit_meat",
                "display_name": "Depositing Meat",
                "duration_ticks": 30,
                "target_zone_tag": "storage_area",
                "action_verb": "storing meat",
                "deposits_item_to_workplace": {"raw_meat": 1, "raw_venison": 1, "animal_pelt": 1, "raw_mutton": 1}
                # Note: Deposits all matching items from inventory
            },
            {
                "id": "scout_area",
                "display_name": "Scouting",
                "duration_ticks": 200,
                "target_zone_tag": "scout_route",
                "action_verb": "scouting"
            }
        ],
        # Butchering and depositing are in the sequence now. The comment this
        # replaces said butchering was "dynamic", but nothing scheduled it:
        # ButcherCarcassSubTaskCommand is written, registered and tested, and a
        # Hunter never reached it, so hunting produced no meat at all.
        # hunt_animals stays even though it targets a "wilderness" zone that has
        # no resolver - the work chain skips a step it cannot find a station for
        # and moves on, so it costs nothing and keeps the intent visible.
        "default_sub_task_sequence": ["scout_area", "hunt_animals", "butcher_carcass", "deposit_meat"]
    },
    "Butcher": {
        "display_name": "Butcher",
        "wage": 24,
        "description": "Processes hunted meat and stores food for the settlement.",
        "work_building_categories": ["Butcher Shop", "Tavern"],
        "sub_tasks": [
            {
                "id": "process_meat",
                "display_name": "Butchering Meat",
                "duration_ticks": 120,
                "target_zone_tag": "workbench",
                "action_verb": "butchering meat",
                "consumes_item_from_workplace": {"raw_meat": 1},
                "produces_item_at_workplace": {"processed_meat": 1}
            }
        ],
        "default_sub_task_sequence": ["process_meat"]
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
        "sub_tasks": [
            {
                "id": "idle_at_desk",
                "display_name": "Reviewing Documents",
                "action_verb": "reviewing",
                "duration_ticks": 150,
                "target_zone_tag": "desk_area"
            },
            {
                "id": "compile_census",
                "display_name": "Compiling Census",
                "action_verb": "compiling",
                "duration_ticks": 6000,
                "target_zone_tag": "desk_area"
            }
        ],
        "default_sub_task_sequence": ["idle_at_desk", "compile_census"]
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
    "Healer": {
        "display_name": "Healer",
        "wage": 35,
        "description": "Treats injuries and illnesses.",
        "work_building_categories": ["Clinic"],
        "sub_tasks": [
            {
                "id": "treating_patient",
                "display_name": "Treating Patient",
                "action_verb": "treating",
                "duration_ticks": 50,
                "target_zone_tag": "medical_bed"
            },
            {
                "id": "preparing_salves",
                "display_name": "Preparing Salves",
                "action_verb": "preparing",
                "duration_ticks": 100,
                "target_zone_tag": "alchemy_station",
                "produces_item_at_workplace": {"healing_salve": 1}
            }
        ],
        "default_sub_task_sequence": ["preparing_salves"]
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
            },
            {
                "id": "write_biography",
                "display_name": "Writing a Biography",
                "action_verb": "writing at",
                "duration_ticks": 6000,
                "target_zone_tag": "writing_desk"
            }
        ],
        "default_sub_task_sequence": ["write_book", "write_biography"]
    },
    "Outlaw": {
        "display_name": "Outlaw",
        "wage": 0,
        "description": "Lives off the land in wilderness encampments outside town jurisdiction.",
        "work_building_categories": [],
        "sub_tasks": [
            {
                "id": "forage_wilderness",
                "display_name": "Foraging",
                "duration_ticks": 100,
                "target_zone_tag": "wilderness",
                "action_verb": "foraging",
            },
            {
                "id": "tend_campfire",
                "display_name": "Tending Campfire",
                "duration_ticks": 80,
                "target_zone_tag": "campfire",
                "action_verb": "tending fire",
            }
        ],
        "default_sub_task_sequence": ["forage_wilderness", "tend_campfire"]
    }
}

def get_profession_data(profession_name: str) -> dict | None:
    """
    Retrieves the data for a given profession.

    Args:
        profession_name: The name of the profession.

    Returns:
        A dictionary containing the profession's data, or None if not found.
    """
    return PROFESSIONS.get(profession_name)

def get_sub_task_data(profession_name: str, sub_task_id: str) -> dict | None:
    """
    Retrieves the data for a specific sub-task of a profession.

    Args:
        profession_name: The name of the profession.
        sub_task_id: The ID of the sub-task.

    Returns:
        A dictionary containing the sub-task's data, or None if not found.
    """
    profession = get_profession_data(profession_name)
    if profession and "sub_tasks" in profession:
        for sub_task in profession["sub_tasks"]:
            if sub_task["id"] == sub_task_id:
                return sub_task
    return None
