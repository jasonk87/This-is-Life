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
