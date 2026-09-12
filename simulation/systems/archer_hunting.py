"""Bow hunting consumes arrows, requires shots, and collects a real carcass."""
import random
from data.animals import ANIMAL_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from simulation.systems import body_combat as combat
from simulation.systems.combat_response import approach, distance, sees


def advance(world, hunter, data, dropoff):
    state = data.get("state")
    inventory = hunter.economic.npc_inventory
    if state == "field_dressing":
        x,y = data["carcass_pos"]
        if max(abs(hunter.x-x),abs(hunter.y-y))>1:
            approach(world,hunter,x,y)
            return True
        tile = world.get_tile_at(x,y)
        if (tile is None or tile.name != "Animal Corpse"
                or tile.properties.get("animal_type") != data["species"]):
            world._clear_hunting_task(hunter)
            return True
        for key,loot in ANIMAL_DEFINITIONS[data["species"]].get("loot_drops",{}).items():
            if random.random() < loot["chance"]:
                qty = loot["quantity"]
                inventory.add_item(key,random.randint(*qty) if isinstance(qty,list) else qty)
        world._change_map_tile((x,y),DECORATION_ITEM_DEFINITIONS["bones"])
        data["state"] = "returning"
        hunter.schedule.current_task = "returning_with_meat"
        hunter.current_sub_task = "Carrying dressed game"
        hunter.schedule.current_destination_coords = None
        hunter.schedule.current_path = []
        return True
    if state != "pursuing" or not combat.ranged_weapon(hunter):
        return False
    if inventory.get("arrow",0) <= 0:
        village = (world._get_village_for_npc(hunter,by_coords=True)
                   or world._get_village_for_npc(hunter))
        # A hunter in the woods still knows the assigned dropoff/workplace.
        # Do not make its existing supplies disappear outside village bounds.
        buildings = [dropoff, *[b for b in getattr(village,"buildings",[]) if b is not dropoff]]
        suppliers = [b for b in buildings if b.building_inventory.get("arrow",0)>0
                     and (b is dropoff or b.building_type in {"general_store","market"})]
        if not suppliers:
            world._clear_hunting_task(hunter)
            hunter.current_sub_task = "Needs arrows"
            return True
        source = min(suppliers,key=lambda b:abs(hunter.x-b.global_center_x)+abs(hunter.y-b.global_center_y))
        x,y = source.global_center_x,source.global_center_y
        if max(abs(hunter.x-x),abs(hunter.y-y))>1:
            approach(world,hunter,x,y)
            hunter.current_sub_task = "Collecting arrows"
            return True
        for _ in range(12):
            ref = source.building_inventory.get_item_reference("arrow")
            if not ref: break
            if source is dropoff:
                source.building_inventory.transfer_item_reference(inventory,ref)
            elif not world.execute_trade(hunter,source,ref,world.quote_item_reference_price(ref,village)):
                break
        if inventory.get("arrow",0) <= 0: world._clear_hunting_task(hunter)
        return True
    prey = world.get_entity_by_id(data.get("prey_id"))
    if prey is None or prey.physical.is_dead:
        world._clear_hunting_task(hunter)
        return True
    combat.ensure_body(hunter,world.game_time)
    reach = combat.held_reference(hunter).definition["properties"]["attack_range"]
    hunter.schedule.current_task = "hunting_prey"
    if distance(hunter,prey)>reach or not sees(world,hunter,prey):
        approach(world,hunter,prey.x,prey.y)
        return True
    result = world.npc_attempt_attack_npc(hunter,prey)
    if prey.physical.is_dead:
        data.update(state="field_dressing",carcass_pos=(prey.x,prey.y),species=prey.animal_type)
        hunter.schedule.current_path = []
        hunter.schedule.current_destination_coords = None
    elif getattr(result,"attempted",False) or hunter.combat.anatomy.attack_ready_tick>world.game_time:
        hunter.schedule.current_path = []
        hunter.current_sub_task = "Drawing bow"
    else:
        approach(world,hunter,prey.x,prey.y)
    return True
