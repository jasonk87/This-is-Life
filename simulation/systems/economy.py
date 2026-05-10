"""Economy-domain simulation helpers (pricing, trade exchanges, market effects)."""

from __future__ import annotations

from data.items import ITEM_DEFINITIONS
from simulation.world_model import TownEconomicNeed


def process_traveling_merchant_village_trade(world, npc, village) -> None:
    """Execute one merchant trade pass against the current village market."""
    for item_key, quantity in list(npc.economic.npc_inventory.items()):
        if item_key == "money":
            continue
        demand = village.demand.get(item_key, 1)
        supply = village.supply.get(item_key, 1)
        if demand / supply > 1.5:
            price = world.get_dynamic_price(item_key, village)
            npc.economic.npc_inventory[item_key] -= 1
            if npc.economic.npc_inventory[item_key] <= 0:
                del npc.economic.npc_inventory[item_key]
            npc.economic.money += price
            village.supply[item_key] = village.supply.get(item_key, 0) + 1
            world.add_message_to_chat_log(
                f"{world.get_entity_display_name(npc)} sold a {ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)} to the village."
            )

    inventory_space = 20 - sum(v for k, v in npc.economic.npc_inventory.items() if k != "money")
    if inventory_space <= 0:
        return

    for item_key, quantity in list(village.supply.items()):
        if item_key == "money":
            continue
        demand = village.demand.get(item_key, 1)
        supply = village.supply.get(item_key, 1)
        if supply / demand > 1.5:
            price = world.get_dynamic_price(item_key, village)
            if npc.economic.money >= price:
                npc.economic.money -= price
                npc.economic.npc_inventory[item_key] = npc.economic.npc_inventory.get(item_key, 0) + 1
                village.supply[item_key] -= 1
                if village.supply[item_key] <= 0:
                    del village.supply[item_key]
                world.add_message_to_chat_log(
                    f"{world.get_entity_display_name(npc)} bought a {ITEM_DEFINITIONS.get(item_key, {}).get('name', item_key)} from the village."
                )
                break

def _find_storage_building(village):
    """Finds a building to store or take resources from."""
    for b in village.buildings:
        if b.building_type in ["general_store", "warehouse", "market"]:
            return b
    if village.buildings:
        return village.buildings[0]
    return None

def simulate_village_economy(world, village) -> None:
    """Handle macroscopic village resource production and consumption."""

    # Needs a minimum population to run economy effectively
    if not hasattr(village, "population_cache") or village.population_cache <= 0:
        return

    population = village.population_cache
    storage_building = _find_storage_building(village)

    # 1. Consumption
    # Villages consume food (supply) based on population
    food_items = ["bread", "raw_meat", "cooked_meat", "berry", "fish", "stew", "wheat", "cheese"]

    food_consumed_this_tick = 0
    food_needed = max(1, population // 5) # 1 unit of food per 5 people per tick

    # Find food to consume from actual building inventories
    for item in food_items:
        if food_consumed_this_tick >= food_needed:
            break
        for b in village.buildings:
            if food_consumed_this_tick >= food_needed:
                break
            if item in b.building_inventory and b.building_inventory[item] > 0:
                consume_amount = min(b.building_inventory[item], food_needed - food_consumed_this_tick)
                b.building_inventory[item] -= consume_amount
                food_consumed_this_tick += consume_amount
                if b.building_inventory[item] <= 0:
                    del b.building_inventory[item]

    # If food demand isn't met, increase demand for food
    if food_consumed_this_tick < food_needed:
        for item in ["bread", "raw_meat"]:
            village.demand[item] = village.demand.get(item, 1) + 1

    # 2. Production (Abstracted)
    if storage_building:
        has_farm = any(b.building_type == "farm" for b in village.buildings)
        has_lumber = any(b.building_type == "lumber_mill" for b in village.buildings)
        has_mine = any(b.building_type == "mine" for b in village.buildings)

        if has_farm:
            # Farms passively produce some wheat over time
            storage_building.building_inventory["wheat"] = storage_building.building_inventory.get("wheat", 0) + 2
            village.demand["wheat"] = max(1, village.demand.get("wheat", 1) - 1)

        if has_lumber:
            # Try to gather from ecology if available
            wood_gathered = 1
            if hasattr(world, "ecology") and hasattr(village, "region_id"):
                wood_gathered = world.ecology.consume_resource(world, village.region_id, "wood", 3)

            if wood_gathered > 0:
                storage_building.building_inventory["raw_log"] = storage_building.building_inventory.get("raw_log", 0) + wood_gathered

        if has_mine:
            storage_building.building_inventory["stone_chunk"] = storage_building.building_inventory.get("stone_chunk", 0) + 2

        # Cap excessive supplies to prevent integer overflow or infinite wealth
        for item, amount in list(storage_building.building_inventory.items()):
            if amount > 1000:
                storage_building.building_inventory[item] = 1000

    # Normalize demand slowly towards 1 to prevent runaway prices
    for item, amount in list(village.demand.items()):
        if amount > 1:
            village.demand[item] -= 0.1 # Slow decay
            if village.demand[item] < 1:
                village.demand[item] = 1

    _update_village_economic_needs(world, village)


def _update_village_economic_needs(world, village) -> None:
    """Evaluate shortages and unmet needs, updating the TownBoard."""

    # 1. Clean up old or resolved needs
    resolved_needs = []
    for need in world.town_board.economic_needs:
        if need.settlement_id != village.id:
            continue

        if need.type == "shortage":
            # Is it still a shortage?
            if village.supply.get(need.target_key, 0) >= village.demand.get(need.target_key, 0) * 1.5:
                resolved_needs.append(need)
        elif need.type == "service":
            # Is the service now provided?
            workers = sum(1 for v in world.village_npcs if getattr(v.schedule, "work_building_id", None) and world.buildings_by_id.get(v.schedule.work_building_id, None) and world.buildings_by_id[v.schedule.work_building_id].settlement_id == village.id and v.economic.profession == need.target_key)
            if workers > 0:
                resolved_needs.append(need)

    for need in resolved_needs:
        world.town_board.economic_needs.remove(need)

    # 2. Detect new shortages
    # Define essential resources
    essentials = ["raw_log", "wheat", "stone_chunk", "bread", "raw_meat"]

    for item in essentials:
        supply = village.supply.get(item, 0)
        demand = village.demand.get(item, 1)

        if supply < demand * 0.5 and demand > 5: # Real shortage
            # Check if need already exists
            existing = next((n for n in world.town_board.economic_needs if n.settlement_id == village.id and n.target_key == item), None)
            if not existing:
                need = TownEconomicNeed(
                    type="shortage",
                    target_key=item,
                    severity=min(100, int((demand - supply) / max(1, demand) * 100)),
                    settlement_id=village.id,
                    creation_tick=world.game_time,
                    description=f"The town seeks a supplier of {ITEM_DEFINITIONS.get(item, {}).get('name', item)}."
                )
                world.town_board.economic_needs.append(need)
                world.add_message_to_chat_log(f"Economic Need: {village.id[:4]} is short on {item}.")

    # 3. Detect missing critical services
    critical_services = ["Blacksmith", "Tavern Keeper", "Merchant", "Farmer", "Woodcutter"]
    for service in critical_services:
        workers = sum(1 for v in world.village_npcs if getattr(v.schedule, "work_building_id", None) and world.buildings_by_id.get(v.schedule.work_building_id, None) and world.buildings_by_id[v.schedule.work_building_id].settlement_id == village.id and v.economic.profession == service)

        # Determine if we have the building for it
        building_reqs = {
            "Blacksmith": "blacksmith_shop",
            "Tavern Keeper": "tavern",
            "Merchant": "general_store",
            "Farmer": "farm",
            "Woodcutter": "lumber_mill"
        }

        has_building = any(b.building_type == building_reqs[service] for b in village.buildings)

        if has_building and workers == 0:
            existing = next((n for n in world.town_board.economic_needs if n.settlement_id == village.id and n.target_key == service), None)
            if not existing:
                need = TownEconomicNeed(
                    type="service",
                    target_key=service,
                    severity=80,
                    settlement_id=village.id,
                    creation_tick=world.game_time,
                    description=f"The town seeks a {service}."
                )
                world.town_board.economic_needs.append(need)
