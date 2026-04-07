"""Economy-domain simulation helpers (pricing, trade exchanges, market effects)."""

from __future__ import annotations

from data.items import ITEM_DEFINITIONS


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
