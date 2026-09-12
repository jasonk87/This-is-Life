"""Real weapon stock carried between existing village markets by merchants."""
from data.items import ITEM_DEFINITIONS

COMPONENTS = {"bowstring", "arrow_shaft", "arrowhead", "feather"}
GOODS = COMPONENTS | {k for k,v in ITEM_DEFINITIONS.items()
                      if set(v.get("item_type_tags",[])) & {"weapon","ammunition"}}


def market_trade(world, merchant, village):
    markets = [b for b in village.buildings if b.building_type in {"general_store","warehouse","market"}]
    if not markets:
        return 0
    market = min(markets,key=lambda b:abs(b.global_center_x-merchant.x)+abs(b.global_center_y-merchant.y))
    if not getattr(merchant,"is_sleeping",False) and max(abs(market.global_center_x-merchant.x),abs(market.global_center_y-merchant.y)) > 3:
        from simulation.systems.combat_response import approach
        approach(world,merchant,market.global_center_x,market.global_center_y)
        return 0
    visit = getattr(merchant,"arms_trade_visit",None)
    if not visit or visit["village_id"] != village.id:
        visit = merchant.arms_trade_visit = dict(village_id=village.id,bought=set(),sold=set())
    cargo,stock = merchant.economic.npc_inventory,market.building_inventory
    moved = 0
    for key in sorted(GOODS):
        reserve = 8 if key == "arrow" else 4 if key in COMPONENTS else 1
        desired = reserve*2
        if key not in visit["bought"] and cargo.get(key,0)>0 and stock.get(key,0)<desired:
            ref = cargo.get_item_reference(key)
            price = world.quote_item_reference_price(ref,village=village)
            if world.execute_trade(market,merchant,ref,price):
                visit["sold"].add(key)
                moved += 1
        elif key not in visit["sold"] and stock.get(key,0)>reserve and sum(q for k,q in cargo.items() if k != "money")<40:
            ref = stock.get_item_reference(key)
            price = world.quote_item_reference_price(ref,village=village)
            if world.execute_trade(merchant,market,ref,price,equip_purchase=False):
                visit["bought"].add(key)
                moved += 1
        village.supply[key] = sum(b.building_inventory.get(key,0) for b in village.buildings)
    if moved:
        world.log_event("weapon_trade", f"{{subject}} exchanged {moved} weapon/ammunition goods at a village market.",
                        subject_id=merchant.id,location=(merchant.x,merchant.y))
    return moved
