"""Gear maintenance, durability degradation, and blacksmith repair system."""

from __future__ import annotations
from typing import Any
from data.items import ITEM_DEFINITIONS
from simulation.careers import entity_has_capability
from entities.items import (
    REPAIR_MONEY_COST_FRACTION_OF_VALUE,
    REPAIR_MATERIAL_KEY,
    REPAIR_MATERIAL_MAX_QTY,
)


def describe_repairable_player_items(player: Any) -> list[dict[str, Any]]:
    """Enumerates the player's damaged, repairable gear across armor slots and inventory items."""
    candidates: list[dict[str, Any]] = []

    # 1. Equipped Armor Slots
    for slot, item_key in getattr(player.equipment, "equipped_armor", {}).items():
        if not item_key:
            continue
        max_durability = player._get_equipped_armor_max_durability(slot) if hasattr(player, "_get_equipped_armor_max_durability") else None
        if max_durability is None or max_durability <= 0:
            continue
        current = getattr(player.equipment, "equipped_armor_durability", {}).get(slot, max_durability)
        if current >= max_durability:
            continue
        item_def = ITEM_DEFINITIONS.get(item_key, {})
        candidates.append({
            "kind": "armor_slot",
            "slot": slot,
            "item_key": item_key,
            "display_name": item_def.get("name", item_key.replace("_", " ").title()),
            "missing_fraction": max(0.0, min(1.0, 1 - (current / max_durability))),
            "value": item_def.get("value", 0),
        })

    # 2. Inventory Item References (weapons, tools)
    for item_key in list(getattr(player.economic, "inventory", {}).keys()):
        if item_key in ("item_references", "money"):
            continue
        item_ref = player.get_item_reference(item_key) if hasattr(player, "get_item_reference") else None
        if item_ref is None or item_ref.current_durability is None:
            continue
        max_durability = item_ref.max_durability
        if max_durability is None or max_durability <= 0 or item_ref.current_durability >= max_durability:
            continue
        candidates.append({
            "kind": "item_reference",
            "item_key": item_key,
            "item_reference": item_ref,
            "display_name": item_ref.name,
            "missing_fraction": max(0.0, min(1.0, 1 - (item_ref.current_durability / max_durability))),
            "value": item_ref.value,
        })

    return candidates


def calculate_repair_cost(candidate: dict[str, Any]) -> dict[str, Any]:
    """Calculate the coin and material cost to repair an item scaled to damage level."""
    missing_fraction = max(0.0, min(1.0, candidate.get("missing_fraction", 0.0)))
    money_cost = max(1, round(candidate.get("value", 0) * missing_fraction * REPAIR_MONEY_COST_FRACTION_OF_VALUE))
    material_qty = max(1, round(missing_fraction * REPAIR_MATERIAL_MAX_QTY))
    return {"money": money_cost, "material_key": REPAIR_MATERIAL_KEY, "material_qty": material_qty}


def player_attempt_repair_gear(world: Any, npc: Any) -> bool:
    """Executes a blacksmith repair on the player's most-damaged gear piece with max durability degradation."""
    npc_display_name = world.get_entity_display_name(npc) if hasattr(world, "get_entity_display_name") else getattr(npc, "name", "Blacksmith")
    if not entity_has_capability(npc, "repair"):
        world.add_message_to_chat_log(f"{npc_display_name} doesn't know how to repair gear.")
        return False

    candidates = describe_repairable_player_items(world.player)
    if not candidates:
        world.add_message_to_chat_log("You have nothing that needs repairing.")
        return False

    candidate = max(candidates, key=lambda c: c["missing_fraction"])
    cost = calculate_repair_cost(candidate)

    if world.player.economic.money < cost["money"]:
        world.add_message_to_chat_log(
            f"{npc_display_name} says repairing your {candidate['display_name']} would cost {cost['money']} coins - you don't have enough."
        )
        return False
    if not world.player.has_item(cost["material_key"], cost["material_qty"]):
        material_name = ITEM_DEFINITIONS.get(cost["material_key"], {}).get("name", cost["material_key"])
        world.add_message_to_chat_log(
            f"{npc_display_name} says repairing your {candidate['display_name']} needs {cost['material_qty']}x {material_name} - you don't have enough."
        )
        return False

    world.player.economic.money -= cost["money"]
    world.player.remove_item(cost["material_key"], cost["material_qty"])

    if candidate["kind"] == "armor_slot":
        result = world.player._repair_equipped_armor_slot(candidate["slot"])
    else:
        result = candidate["item_reference"].repair()

    if result.get("at_repair_limit"):
        world.add_message_to_chat_log(
            f"{npc_display_name} repairs your {candidate['display_name']} as best they can - "
            f"it's showing its age and won't hold up like it used to."
        )
    else:
        world.add_message_to_chat_log(f"{npc_display_name} repairs your {candidate['display_name']}.")
    return True
