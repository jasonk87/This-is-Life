"""Physical settlement accounting. Supply is a view, never a second inventory."""
from collections import Counter

from config import DAY_LENGTH_TICKS
from data.items import ITEM_DEFINITIONS
from simulation.world_model import TownEconomicNeed

FOODS = ("bread", "apple", "cooked_meat", "fish", "raw_fish", "cheese", "stew", "ration",
         "smoked_meat", "cooked_venison", "cooked_mutton", "cooked_fish")
DRINKS = ("water_flask", "ale", "beer", "wine", "cider")
SERVICES = {"Blacksmith": "blacksmith_shop", "Tavern Keeper": "tavern",
            "Merchant": "general_store", "Farmer": "farm", "Woodcutter": "lumber_mill",
            "Baker": "bakery"}
MARKETS = {"general_store", "warehouse", "market", "bakery", "tavern"}


def refresh_supply(village):
    stock = Counter()
    for building in village.buildings:
        stock.update({key: qty for key, qty in building.building_inventory.items()
                      if key != "money" and qty > 0})
    village.supply = dict(stock)
    return village.supply


def residents(world, village):
    return [n for n in world._get_settlement_residents(village)
            if not n.physical.is_dead and not n.travel.is_traveling]


def simulate_village_economy(world, village):
    """Summarize real people/goods and detect pressure; never produce or consume."""
    people = residents(world, village)
    village.population_cache = len(people)
    refresh_supply(village)
    # One day of food security, with alternatives counted together. A stocked
    # apple seller must not manufacture a bread famine merely by selling apples.
    food_stock = sum(village.supply.get(k, 0) for k in FOODS)
    village.demand["bread"] = max(village.demand.get("bread", 1),
                                  max(0, len(people)*2 - food_stock))
    for bp in world._get_village_blueprints(village):
        for key, qty in bp.remaining_materials().items():
            village.demand[key] = max(village.demand.get(key, 1), qty)
    # Unfulfilled workplace inputs are actionable shortages too.
    from data.professions import get_profession_data, get_sub_task_data
    required = Counter()
    for npc in people:
        building = world.buildings_by_id.get(npc.schedule.work_building_id)
        if building is None:
            continue
        for step in (get_profession_data(npc.economic.profession) or {}).get("default_sub_task_sequence", []):
            consumes = (get_sub_task_data(npc.economic.profession, step) or {}).get("consumes_item_from_workplace", {})
            for key, qty in consumes.items():
                required[key] += qty * 8
    for key, qty in required.items():
        village.demand[key] = max(village.demand.get(key, 1), qty)
    _update_village_economic_needs(world, village)


def _update_village_economic_needs(world, village):
    workers = Counter()
    for npc in world.village_npcs:
        building = world.buildings_by_id.get(npc.schedule.work_building_id)
        if building and building.settlement_id == village.id and not npc.physical.is_dead and not npc.travel.is_traveling:
            workers[building.building_type] += 1
    for need in list(world.town_board.economic_needs):
        if need.settlement_id != village.id:
            continue
        resolved = (need.type == "shortage" and
                    (village.demand.get(need.target_key, 0) <= 5 or
                     village.supply.get(need.target_key, 0) >= village.demand.get(need.target_key, 0)*1.5))
        if need.type == "service":
            resolved = workers[SERVICES.get(need.target_key, "")] > 0
        if resolved:
            world.town_board.economic_needs.remove(need)

    def add(kind, key, severity, description):
        existing = next((n for n in world.town_board.economic_needs
                         if n.settlement_id == village.id and n.type == kind and n.target_key == key), None)
        if existing:
            existing.severity = severity
            return
        world.town_board.economic_needs.append(TownEconomicNeed(
            type=kind, target_key=key, severity=severity, settlement_id=village.id,
            creation_tick=world.game_time, description=description))

    # Include recipe inputs instead of a disconnected generic "food" demand.
    for key, demand in village.demand.items():
        supply = village.supply.get(key, 0)
        if key in ITEM_DEFINITIONS and supply < demand*.5 and demand > 5:
            add("shortage", key, min(100, int((demand-supply)/demand*100)),
                f"The town seeks a supplier of {ITEM_DEFINITIONS[key].get('name', key)}.")
    for service, kind in SERVICES.items():
        has_building = any(b.building_type == kind for b in village.buildings)
        # Communities need baseline services even if no suitable workplace yet
        # exists. Empty/uninhabited sites do not request a full town's industries.
        if workers[kind] == 0 and (has_building or getattr(village, "population_cache", 0) >= 8):
            add("service", service, 80, f"The town seeks a {service}.")


def provide_sleeping_sustenance(world, npc):
    """Abstract the errand, not the meal, property, price or water source."""
    from simulation.systems.survival import advance_npc_metabolism, check_emergency_npc_sustenance
    advance_npc_metabolism(world, npc)
    check_emergency_npc_sustenance(world, npc)
    if npc.physical.is_dead or "unconscious" in npc.physical.status_effects:
        return
    # Travelers live on carried provisions; they cannot shop back in their
    # origin town just because the last macro coordinate still points there.
    if npc.travel.is_traveling:
        return
    if npc.physical.hunger < 70 and npc.physical.thirst < 70:
        return
    village = world._get_village_for_npc(npc)
    if village is None:
        return
    for attr, keys in (("hunger", FOODS), ("thirst", DRINKS)):
        if getattr(npc.physical, attr) < 70:
            continue
        acquired = False
        for building in sorted(village.buildings, key=lambda b: b.id != npc.schedule.home_building_id):
            own_pantry = building.id == npc.schedule.home_building_id
            if not own_pantry and building.building_type not in MARKETS:
                continue
            for key in keys:
                ref = building.building_inventory.get_item_reference(key)
                if ref is None:
                    continue
                if own_pantry:
                    acquired = building.building_inventory.transfer_item_reference(npc.economic.npc_inventory, ref)
                else:
                    acquired = world.execute_trade(npc, building, ref,
                        max(1, world.quote_item_reference_price(ref, village=village)), equip_purchase=False)
                if acquired:
                    break
            if acquired:
                break
        check_emergency_npc_sustenance(world, npc)
        if attr == "thirst" and npc.physical.thirst >= 70:
            # The well is a real renewable water source, not an invented drink.
            for x, y in village.interaction_points.get("well", []):
                tile = world.get_tile_at(x, y)
                if tile and tile.name.lower() in {"well", "water", "deep water"}:
                    npc.physical.thirst = max(0, npc.physical.thirst-40)
                    break
    refresh_supply(village)


def procure_worker_inputs(world, npc, workplace):
    """Buy one production cycle's missing inputs from dormant local suppliers.

    This abstracts the haul, not ownership or payment. Active suppliers retain
    the ordinary delivery-task path; household pantries are never wholesale.
    """
    from data.professions import get_profession_data, get_sub_task_data
    village = world._get_npc_settlement(npc)
    if village is None or world._is_building_active(workplace):
        return 0
    required = Counter()
    for step in (get_profession_data(npc.economic.profession) or {}).get("default_sub_task_sequence", []):
        for key, qty in (get_sub_task_data(npc.economic.profession, step) or {}).get("consumes_item_from_workplace", {}).items():
            required[key] = max(required[key], qty)
    moved = 0
    for key, needed in required.items():
        remaining = max(0, needed-workplace.building_inventory.get(key, 0))
        for seller in village.buildings:
            if seller is workplace or world._is_building_active(seller):
                continue
            if "workplace" not in str(seller.category) and seller.building_type not in MARKETS:
                continue
            for _ in range(min(remaining, seller.building_inventory.get(key, 0))):
                ref = seller.building_inventory.get_item_reference(key)
                if not world.execute_trade(workplace, seller, ref,
                        max(1, world.quote_item_reference_price(ref, village=village)), equip_purchase=False):
                    break
                moved += 1
                remaining -= 1
            if remaining <= 0:
                break
    return moved


def _find_storage_building(village):
    return next((b for b in village.buildings if b.building_type in {"general_store", "warehouse", "market"}), None)


def process_traveling_merchant_village_trade(world, npc, village):
    """All cargo trades use item identities and funded counterparties."""
    from simulation.systems.weapon_economy import GOODS, market_trade
    moved = market_trade(world, npc, village)
    market = _find_storage_building(village)
    if market is None:
        return moved
    if not npc.is_sleeping and max(abs(market.global_center_x-npc.x), abs(market.global_center_y-npc.y)) > 3:
        return moved
    refresh_supply(village)
    visit = getattr(npc, "commodity_trade_visit", None)
    if not visit or visit["village_id"] != village.id:
        visit = npc.commodity_trade_visit = dict(village_id=village.id, bought=set(), sold=set())
    cargo, stock = npc.economic.npc_inventory, market.building_inventory
    for key in sorted((set(cargo) | set(stock)) - GOODS - {"money", "rotten_food"}):
        desired = max(4, min(30, int(village.demand.get(key, 4))))
        if key not in visit["bought"] and cargo.get(key, 0) and stock.get(key, 0) < desired:
            ref = cargo.get_item_reference(key)
            if world.execute_trade(market, npc, ref, max(1, world.quote_item_reference_price(ref, village=village)), equip_purchase=False):
                visit["sold"].add(key)
                moved += 1
        elif key not in visit["sold"] and stock.get(key, 0) > desired and sum(q for k,q in cargo.items() if k != "money") < 40:
            reserved = sum(bp.remaining_materials().get(key, 0) for bp in world._get_village_blueprints(village))
            if village.supply.get(key, 0) <= reserved + desired:
                continue
            ref = stock.get_item_reference(key)
            if world.execute_trade(npc, market, ref, max(1, world.quote_item_reference_price(ref, village=village)), equip_purchase=False):
                visit["bought"].add(key)
                moved += 1
    refresh_supply(village)
    return moved


def trade_settlement_surplus(world, source, destination):
    """Daily distant caravans transfer real surplus and real payment."""
    if destination.id in source.at_war_with:
        return 0
    market = _find_storage_building(destination)
    if market is None:
        return 0
    refresh_supply(source)
    refresh_supply(destination)
    moved = 0
    for key, qty in sorted(source.supply.items()):
        if key in {"rotten_food"}:
            continue
        reserved = sum(bp.remaining_materials().get(key, 0) for bp in world._get_village_blueprints(source))
        surplus = qty - max(reserved, int(source.demand.get(key, 10)), 10)
        wanted = max(10, int(destination.demand.get(key, 10))) - destination.supply.get(key, 0)
        remaining = min(10, surplus, wanted)
        if remaining <= 0:
            continue
        for seller in source.buildings:
            if "workplace" not in str(seller.category) and seller.building_type not in MARKETS:
                continue  # A caravan cannot sell somebody else's household pantry.
            for _ in range(min(remaining, seller.building_inventory.get(key, 0))):
                ref = seller.building_inventory.get_item_reference(key)
                if not world.execute_trade(market, seller, ref,
                    max(1, world.quote_item_reference_price(ref, village=source)), equip_purchase=False):
                    break
                remaining -= 1
                moved += 1
            if remaining <= 0:
                break
    refresh_supply(source)
    refresh_supply(destination)
    if moved:
        from simulation.systems.settlements import record_trade_relations
        record_trade_relations(world, source, destination)
        world.log_event("trade_deal", f"A caravan exchanged {moved} goods between {source.name} and {destination.name}.",
                        subject_id=-1, location=world._get_village_anchor_coords(source))
    return moved
