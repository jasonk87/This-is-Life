"""
Utility-based AI evaluation for emergent goal selection based on needs and personality.
"""

from __future__ import annotations
import random
from simulation.systems.task_types import TaskType

def evaluate_needs_utility(world, npc) -> bool:
    """
    Evaluate physiological needs and return True if a need-driven task was assigned,
    overriding the standard schedule.
    """
    protected_tasks = {
        "seeking_healer", "waiting_for_treatment", "resting_in_bed",
        "avoiding_social_threat", "fleeing_from_player", "combat_action_flee_from_player",
        "attacking_player", "going_to_report_crime",
    }
    if npc.schedule.current_task in protected_tasks:
        return False

    # Lock active utility tasks to prevent thrashing
    active_utility_tasks = [
        TaskType.GOING_TO_BUY_FOOD, TaskType.FORAGING_FOOD, TaskType.GOING_TO_STEAL_FOOD,
        TaskType.LOOKING_FOR_WORK
    ]

    if npc.schedule.current_task in active_utility_tasks:
        # Process arrivals for food tasks
        if npc.schedule.current_task == TaskType.GOING_TO_BUY_FOOD and (npc.x, npc.y) == npc.schedule.current_destination_coords:
            _execute_buy_food(world, npc)
        elif npc.schedule.current_task == TaskType.FORAGING_FOOD and (npc.x, npc.y) == npc.schedule.current_destination_coords:
            _execute_forage(world, npc)
        elif npc.schedule.current_task == TaskType.GOING_TO_STEAL_FOOD and (npc.x, npc.y) == npc.schedule.current_destination_coords:
            _execute_steal_food(world, npc)

        # Still working on a utility task, lock the schedule
        return True

    # 1. Check Primary Needs (e.g., Hunger)
    is_hungry = False
    if hasattr(npc, "physical") and hasattr(npc.physical, "hunger") and hasattr(npc.physical, "max_hunger"):
        hunger_threshold = npc.physical.max_hunger * 0.7
        is_hungry = npc.physical.hunger >= hunger_threshold

    if not is_hungry:
        # Fallthrough to secondary needs if not hungry
        return _evaluate_wealth_utility(world, npc)

    # We are hungry. Evaluate options based on Utility (Score = Base Utility + Personality Modifiers)
    options = {}
    personality = ""
    if hasattr(npc, "social") and hasattr(npc.social, "personality"):
        personality = getattr(npc.social, "personality", "").lower()

    # Option A: Buy Food
    # Base utility depends on having money
    if hasattr(npc, "economic") and hasattr(npc.economic, "money") and npc.economic.money > 0:
        score = 50 + (npc.economic.money // 10)
        if "greedy" in personality: score -= 20 # Greedy people don't like spending money
        if "lawful" in personality: score += 20
        options["buy_food"] = score

    # Option B: Forage
    # Base utility is safe but takes time
    score = 40
    if "lazy" in personality: score -= 30
    if "lawful" in personality: score += 10
    options["forage"] = score

    # Option C: Steal Food
    # Base utility is high (fast) but risky
    score = 30
    if "greedy" in personality: score += 40
    if "lawful" in personality: score -= 80 # Very unlikely for lawful
    if "chaotic" in personality or "criminal" in personality: score += 50
    options["steal_food"] = score

    # Choose best option
    if not options:
        return False

    best_option = max(options, key=options.get)

    # Apply the goal
    if best_option == "buy_food":
        _set_buy_food_goal(world, npc)
        return True
    elif best_option == "forage":
        _set_forage_goal(world, npc)
        return True
    elif best_option == "steal_food":
        _set_steal_goal(world, npc)
        return True

    return False

def _evaluate_wealth_utility(world, npc) -> bool:
    """Evaluate poverty/wealth needs."""
    if not hasattr(npc, "economic") or not hasattr(npc.economic, "money") or not hasattr(npc.economic, "profession"):
        return False

    if npc.economic.money < 5 and npc.economic.profession.lower() in ["unemployed", "beggar"]:
        # We are poor. Evaluate finding a job vs begging/stealing.
        options = {}
        personality = ""
        if hasattr(npc, "social") and hasattr(npc.social, "personality"):
            personality = getattr(npc.social, "personality", "").lower()

        score = 50
        if "lazy" in personality: score -= 30
        if "lawful" in personality: score += 20
        options["seek_job"] = score

        score = 40
        if "greedy" in personality: score += 20
        if "chaotic" in personality: score += 30
        if "lawful" in personality: score -= 50
        options["beg_or_steal"] = score

        best = max(options, key=options.get)
        if best == "seek_job":
            npc.schedule.current_task = TaskType.LOOKING_FOR_WORK
            return True
        elif best == "beg_or_steal":
            _set_steal_goal(world, npc)
            return True

    return False

def _execute_buy_food(world, npc):
    """Attempt to buy food from the target building."""
    village = world._get_village_for_npc(npc)
    if village and npc.economic.money >= 5: # Assuming base cost of food
        target_building = None
        for b in village.buildings:
            if world._get_building_global_center_coords(b.id) == (npc.x, npc.y):
                target_building = b
                break

        if target_building:
            food_items = ["bread", "raw_meat", "cooked_meat", "berry", "fish", "stew", "wheat", "cheese"]
            for item in food_items:
                if item in target_building.building_inventory and target_building.building_inventory[item] > 0:
                    price = world.get_dynamic_price(item, village)
                    if npc.economic.money >= price:
                        target_building.building_inventory[item] -= 1
                        if target_building.building_inventory[item] == 0:
                            del target_building.building_inventory[item]
                        npc.economic.money -= price
                        if hasattr(npc, "physical") and hasattr(npc.physical, "hunger"):
                            npc.physical.hunger = max(0, npc.physical.hunger - 50)
                        npc.schedule.current_task = TaskType.IDLE
                        world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} bought some {item}.")
                        return
    # Failed to buy, idle
    npc.schedule.current_task = TaskType.IDLE

def _execute_forage(world, npc):
    """Attempt to forage at the current forest tile."""
    # Check if the tile is still a forest
    tile = world.get_tile_at(npc.x, npc.y)
    if tile and tile.name == "Forest":
        village = world._get_village_for_npc(npc)
        if hasattr(world, "ecology") and village and hasattr(village, "region_id"):
            gathered = world.ecology.consume_resource(world, village.region_id, "forage", 1)
            if gathered > 0:
                if hasattr(npc, "physical") and hasattr(npc.physical, "hunger"):
                    npc.physical.hunger = max(0, npc.physical.hunger - 20) # Not as filling as bought food
                world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} foraged some food in the woods.")
                npc.schedule.current_task = TaskType.IDLE
                return
    npc.schedule.current_task = TaskType.IDLE

def _execute_steal_food(world, npc):
    """Attempt to steal food from the building."""
    village = world._get_village_for_npc(npc)
    if village:
        target_building = None
        for b in village.buildings:
            if world._get_building_global_center_coords(b.id) == (npc.x, npc.y):
                target_building = b
                break

        if target_building:
            food_items = ["bread", "raw_meat", "cooked_meat", "berry", "fish", "stew", "wheat", "cheese"]
            for item in food_items:
                if item in target_building.building_inventory and target_building.building_inventory[item] > 0:
                    target_building.building_inventory[item] -= 1
                    if target_building.building_inventory[item] == 0:
                        del target_building.building_inventory[item]
                    if hasattr(npc, "physical") and hasattr(npc.physical, "hunger"):
                        npc.physical.hunger = max(0, npc.physical.hunger - 50)
                    npc.schedule.current_task = TaskType.IDLE
                    world.add_message_to_chat_log(f"{world.get_entity_display_name(npc)} stole some {item}.")

                    # Small chance to be caught by a sheriff/guard
                    if random.random() < 0.2:
                        world.add_message_to_chat_log(
                            f"{world.get_entity_display_name(npc)} was caught stealing!"
                        )
                        world.record_crime_event(
                            crime_kind="theft",
                            suspect_id=npc.id,
                            description="{subject} was caught stealing from a building.",
                            location=(npc.x, npc.y),
                        )
                        world._accrue_crime_bounty(npc, "theft")
                    return
    # Failed to steal
    npc.schedule.current_task = TaskType.IDLE

def _set_buy_food_goal(world, npc):
    """Path to the nearest store/market."""
    # Simplified: Find a general store or food vendor
    target_building = None
    village = world._get_village_for_npc(npc)
    if village:
        for b in village.buildings:
            if b.building_type in ["general_store", "tavern", "farm"]:
                target_building = b
                break

    if target_building:
        dest = world._get_building_global_center_coords(target_building.id)
        if dest:
            npc.schedule.current_task = TaskType.GOING_TO_BUY_FOOD
            npc.schedule.current_destination_coords = dest
            npc.schedule.current_path = world.calculate_path(npc.x, npc.y, dest[0], dest[1]) or []
            if not npc.schedule.current_path:
                npc.schedule.current_task = TaskType.IDLE
            return

    # Fallback if no store
    _set_forage_goal(world, npc)

def _set_forage_goal(world, npc):
    """Find a nearby forest/plains tile to forage."""
    # Spiral search out to a smaller radius to minimize performance hit
    max_radius = 8
    for r in range(1, max_radius + 1):
        # Sample points along the perimeter of the radius
        for dx in range(-r, r + 1, max(1, r // 2)):
            for dy in [-r, r]:
                x, y = npc.x + dx, npc.y + dy
                tile = world.get_tile_at(x, y)
                if tile and tile.name == "Forest":
                    npc.schedule.current_task = TaskType.FORAGING_FOOD
                    npc.schedule.current_destination_coords = (x, y)
                    npc.schedule.current_path = world.calculate_path(npc.x, npc.y, x, y) or []
                    if not npc.schedule.current_path:
                        npc.schedule.current_task = TaskType.IDLE
                    return
            for dy in range(-r + 1, r, max(1, r // 2)):
                for dx in [-r, r]:
                    x, y = npc.x + dx, npc.y + dy
                    tile = world.get_tile_at(x, y)
                    if tile and tile.name == "Forest":
                        npc.schedule.current_task = TaskType.FORAGING_FOOD
                        npc.schedule.current_destination_coords = (x, y)
                        npc.schedule.current_path = world.calculate_path(npc.x, npc.y, x, y) or []
                        if not npc.schedule.current_path:
                            npc.schedule.current_task = TaskType.IDLE
                        return

def _set_steal_goal(world, npc):
    """Find another NPC's home or a store to steal from."""
    village = world._get_village_for_npc(npc)
    if village and village.buildings:
        # Pick a random building that isn't their home
        targets = [b for b in village.buildings if b.id != npc.schedule.home_building_id]
        if targets:
            target_building = random.choice(targets)
            dest = world._get_building_global_center_coords(target_building.id)
            if dest:
                npc.schedule.current_task = TaskType.GOING_TO_STEAL_FOOD
                npc.schedule.current_destination_coords = dest
                npc.schedule.current_path = world.calculate_path(npc.x, npc.y, dest[0], dest[1]) or []
                if not npc.schedule.current_path:
                    npc.schedule.current_task = TaskType.IDLE
                return
