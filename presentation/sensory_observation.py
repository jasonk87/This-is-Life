"""Hardcore sensory observation engine for diegetic world inspection."""

from __future__ import annotations
from typing import Any


def observe_entity(entity: Any, viewer: Any, world: Any) -> str:
    """Build a rich, realistic physical observation of an NPC, Animal, or Player."""
    if entity is None:
        return "You see nothing here."

    # Animal inspection
    if getattr(entity, "is_animal", False) or hasattr(entity, "animal_type"):
        species = getattr(entity, "animal_type", "creature").replace("_", " ").title()
        name = getattr(entity, "name", species)
        hp = getattr(getattr(entity, "combat", None), "hp", 10)
        max_hp = getattr(getattr(entity, "combat", None), "max_hp", 10)
        sub_task = getattr(entity, "current_sub_task", "Roaming")
        behavior = getattr(entity, "behavior", "Neutral")

        health_desc = "healthy"
        if hp < max_hp * 0.4:
            health_desc = "severely injured and limping"
        elif hp < max_hp * 0.8:
            health_desc = "scratched and bruised"

        return f"{name} ({species}): {health_desc}, currently {sub_task.lower()} ({behavior.lower()})."

    # Humanoid NPC inspection
    name = str(getattr(entity, "name", "Stranger")).replace("_", " ")
    prof = getattr(getattr(entity, "economic", None), "profession", "Villager")
    relation = world.get_relationship_label(entity) if world and hasattr(world, "get_relationship_label") else ""

    header = f"{name} ({prof})"
    if relation:
        header += f" - your {relation.lower()}"

    observations = []

    # 1. Current physical action / task
    task = getattr(getattr(entity, "schedule", None), "current_task", None) or getattr(entity, "current_sub_task", None)
    if task:
        task_clean = str(task).replace("_", " ").lower()
        if "sleep" in task_clean:
            observations.append("sleeping soundly")
        elif "till" in task_clean:
            observations.append("tilling the soil in the field")
        elif "plant" in task_clean:
            observations.append("sowing seeds into the furrowed earth")
        elif "harvest" in task_clean:
            observations.append("harvesting mature crops")
        elif "mill" in task_clean or "grind" in task_clean:
            observations.append("operating the grinding stone to mill flour")
        elif "bake" in task_clean:
            observations.append("baking bread in the hot oven")
        elif "smelt" in task_clean or "forge" in task_clean:
            observations.append("working at the roaring forge")
        elif "craft" in task_clean:
            observations.append("crafting tools at the anvil")
        elif "chop" in task_clean:
            observations.append("chopping timber with an axe")
        elif "mine" in task_clean:
            observations.append("striking the rock face with a pickaxe")
        elif "patrol" in task_clean or "guard" in task_clean:
            observations.append("standing guard with a vigilant stance")
        elif "eat" in task_clean or "tavern" in task_clean:
            observations.append("eating a warm meal")
        elif "drink" in task_clean or "water" in task_clean:
            observations.append("drinking cool water")
        elif "walk" in task_clean or "travel" in task_clean or "seek" in task_clean:
            dest = getattr(entity.schedule, "current_destination_coords", None)
            observations.append("walking briskly towards destination" if dest else "on the move")
        else:
            observations.append(f"engaged in {task_clean}")
    else:
        observations.append("standing at ease")

    # 2. Visible equipment & held tools
    eq = getattr(entity, "equipment", None)
    held_items = []
    if eq:
        weapon_key = getattr(getattr(eq, "weapon", None), "item_key", getattr(eq, "weapon", None))
        if weapon_key and str(weapon_key) != "None":
            held_items.append(f"holding a {str(weapon_key).replace('_', ' ')}")
        body_key = getattr(getattr(eq, "body", None), "item_key", getattr(eq, "body", None))
        if body_key and str(body_key) != "None":
            held_items.append(f"wearing {str(body_key).replace('_', ' ')}")

    # Check top carried cargo in inventory
    inv = getattr(getattr(entity, "economic", None), "npc_inventory", {})
    cargo = []
    for item_key, count in inv.items():
        if item_key not in ["money", "item_references"] and count > 0:
            cargo.append(f"{count} {item_key.replace('_', ' ')}")
        if len(cargo) >= 2:
            break
    if cargo:
        held_items.append(f"carrying {', '.join(cargo)}")

    if held_items:
        observations.append("; ".join(held_items))

    # 3. Physical condition (Health, Hunger, Temperature, Fatigue)
    phys = getattr(entity, "physical", None)
    combat = getattr(entity, "combat", None)
    status_signs = []
    if combat:
        hp = getattr(combat, "hp", 100)
        max_hp = getattr(combat, "max_hp", 100)
        if hp < max_hp * 0.35:
            status_signs.append("severely wounded and bleeding")
        elif hp < max_hp * 0.75:
            status_signs.append("visibly bruised with minor injuries")
        else:
            status_signs.append("in good health")

    if phys:
        hunger = getattr(phys, "hunger", 0)
        if hunger >= 85:
            status_signs.append("gaunt and weak from starvation")
        elif hunger >= 70:
            status_signs.append("visibly hungry and fatigued")

        thirst = getattr(phys, "thirst", 0)
        if thirst >= 80:
            status_signs.append("parched from thirst")

        temp = getattr(phys, "body_temperature", 37.0)
        if temp < 35.0:
            status_signs.append("shivering in the cold wind")
        elif temp > 39.0:
            status_signs.append("sweating from the intense heat")

        fatigue = getattr(phys, "fatigue", 0)
        if fatigue >= 80:
            status_signs.append("eyelids heavy with exhaustion")

    if status_signs:
        observations.append(", ".join(status_signs))

    # 4. Demeanor and attitude
    attitude = getattr(entity, "attitude_to_player", "neutral")
    if attitude in ["warm", "friendly"]:
        observations.append("looks at you with a friendly, welcoming expression")
    elif attitude in ["unfriendly"]:
        observations.append("watches you with guarded, suspicious eyes")
    elif attitude in ["hostile"]:
        observations.append("glares with open hostility, hand near weapon")
    else:
        observations.append("maintains a neutral, calm demeanor")

    return f"{header}. " + ". ".join(s[0].upper() + s[1:] for s in observations if s) + "."


def observe_tile(world: Any, x: int, y: int) -> str:
    """Build a detailed sensory description of a world tile and everything on it."""
    tile = world.get_tile_at(x, y) if world else None
    if not tile:
        return "An unexplored void beyond the horizon."

    lines = []

    # 1. Tile Base Description
    tname = getattr(tile, "name", "Unknown Ground")
    props = getattr(tile, "properties", {})

    if tname == "Plains":
        lines.append("Open wild plains covered in coarse grass and fertile soil, suitable for tilling.")
    elif tname == "Tilled Soil":
        lines.append("Dark, moist tilled soil, neatly furrowed and ready for planting seeds.")
    elif tname == "Growing Wheat":
        prog = props.get("growth_progress", 0)
        need = props.get("growth_needed", 100)
        pct = int((prog / max(1, need)) * 100)
        lines.append(f"Vibrant green wheat shoots pushing through the furrowed earth ({pct}% mature).")
    elif tname == "Wheat":
        lines.append("Tall golden wheat crop, heavy with grain and ready for immediate harvest.")
    elif tname == "Road" or "Cobblestone" in tname:
        lines.append("A well-trodden stone pathway connecting village districts and trade routes.")
    elif tname == "Water":
        lines.append("Clear, cold water rippling gently.")
    elif tname == "Oak Tree":
        lines.append("A tall, sturdy oak tree with lush foliage and harvestable timber.")
    elif tname == "Apple Tree":
        lines.append("A fruit-bearing apple tree providing sweet apples and shade.")
    elif props.get("workstation_type") == "fire" or "Fire" in tname:
        lines.append("An active campfire with crackling flames and radiant heat, suitable for cooking and thawing hands.")
    elif props.get("workstation_type") == "oven" or "Oven" in tname:
        lines.append("A stone baking oven radiating heat, ideal for baking freshly milled flour into bread.")
    elif props.get("workstation_type") == "grinding_stone" or "Mill" in tname or "Grinding" in tname:
        lines.append("A heavy stone grinding wheel for milling harvested wheat into fine flour.")
    elif props.get("workstation_type") == "forge" or "Forge" in tname:
        lines.append("A roaring blacksmith forge glowing orange with heat, used to smelt ores and forge trade tools.")
    elif props.get("is_door"):
        door_state = "open" if tile.passable else "closed"
        lines.append(f"A sturdy wooden door ({door_state}).")
    elif props.get("is_container") or "Chest" in tname:
        lines.append("A wooden storage chest with iron hinges for holding household goods and provisions.")
    elif "Wall" in tname:
        lines.append(f"A solid {tname.lower()} providing shelter from wind and predators.")
    else:
        lines.append(f"{tname}.")

    # 2. Workstation and Thermal Properties
    if props.get("heat_source"):
        radius = props.get("heat_source_radius", 4)
        lines.append(f"Radiating comfortable warmth up to {radius} paces away.")

    # 3. Ground Items
    if hasattr(world, "items_on_map") and (x, y) in world.items_on_map:
        ground_items = []
        for item_key, count in world.items_on_map[(x, y)].items():
            if item_key not in ["item_references"] and count > 0:
                ground_items.append(f"{count} {item_key.replace('_', ' ')}")
        if ground_items:
            lines.append(f"On the ground: {', '.join(ground_items)}.")

    # 4. Living Entities Present
    if hasattr(world, "all_npcs"):
        occupants = [npc for npc in world.all_npcs if npc.x == x and npc.y == y and not getattr(npc, "is_dead", False)]
        for npc in occupants:
            lines.append(observe_entity(npc, world.player, world))

    return "\n".join(lines)


def get_tile_sensory_summary(world: Any, x: int, y: int) -> str:
    """Return a crisp, high-density one-line summary for HUD footer and mouse hover."""
    if not world:
        return ""
    tile = world.get_tile_at(x, y)
    if not tile:
        return "[Unexplored]"

    tname = getattr(tile, "name", "Ground")
    props = getattr(tile, "properties", {})

    # Check for occupants first
    occupants = [npc for npc in world.all_npcs if npc.x == x and npc.y == y and not getattr(npc, "is_dead", False)]
    if occupants:
        npc = occupants[0]
        name = getattr(npc, "name", "Someone").replace("_", " ")
        prof = getattr(getattr(npc, "economic", None), "profession", "Villager")
        task = getattr(getattr(npc, "schedule", None), "current_task", "") or getattr(npc, "current_sub_task", "")
        task_str = f" | {task.replace('_', ' ').title()}" if task else ""
        weapon = getattr(getattr(npc, "equipment", None), "weapon", None)
        weapon_str = f" | Holding {weapon.replace('_', ' ')}" if weapon else ""
        return f"[{name} ({prof}){task_str}{weapon_str}]"

    # Workstation / Special Tiles
    if props.get("workstation_type") == "fire":
        return "[Active Campfire - Cooking & Warmth]"
    if props.get("workstation_type") == "oven":
        return "[Stone Oven - Bread Baking]"
    if props.get("workstation_type") == "grinding_stone":
        return "[Grinding Stone - Wheat Milling]"
    if props.get("workstation_type") == "forge":
        return "[Blacksmith Forge - Smelting & Crafting]"
    if tname == "Growing Wheat":
        prog = props.get("growth_progress", 0)
        need = props.get("growth_needed", 100)
        return f"[Growing Wheat ({int(prog/max(1, need)*100)}%)]"
    if tname == "Wheat":
        return "[Mature Wheat - Ready to Harvest]"
    if tname == "Tilled Soil":
        return "[Tilled Soil - Ready for Seeds]"
    if props.get("is_door"):
        return f"[Door ({'Open' if tile.passable else 'Closed'})]"
    if props.get("is_container"):
        return "[Wooden Chest]"

    # Ground Items
    if hasattr(world, "items_on_map") and (x, y) in world.items_on_map:
        items = [f"{c}x {k.replace('_', ' ')}" for k, c in world.items_on_map[(x, y)].items() if k != "item_references" and c > 0]
        if items:
            return f"[{tname} | Ground: {', '.join(items[:2])}]"

    return f"[{tname}]"
