"""Settlement identity, jurisdiction and bounded government evaluation scope.

World.politics remains a compatibility view of the current settlement. Villages
own the actual records; a daily pass visits every jurisdiction explicitly.
"""
from contextlib import contextmanager
from simulation.world_model import PoliticsTracker
from config import CHUNK_SIZE


def villages(world):
    found = {v.id: v for v in getattr(getattr(world, "atlas", None), "villages", [])}
    for row in getattr(world, "chunks", []):
        for chunk in row:
            if chunk.village is not None:
                found[chunk.village.id] = chunk.village
    return list(found.values())


def at(world, x, y):
    cx, cy = x // CHUNK_SIZE, y // CHUNK_SIZE
    chunks = getattr(world, "chunks", [])
    if 0 <= cy < len(chunks) and 0 <= cx < len(chunks[cy]):
        village = chunks[cy][cx].village
        if village is not None:
            return village
    # Rural businesses can belong to a settlement beyond its original chunk.
    building = world.get_building_at(x, y) if hasattr(world, "atlas") else None
    sid = getattr(building, "settlement_id", None)
    return next((v for v in villages(world) if v.id == sid), None) if sid else None


def current(world):
    scoped = getattr(world, "_governance_settlement_id", None)
    if scoped is not None:
        return next((v for v in villages(world) if v.id == scoped), None)
    player = getattr(world, "player", None)
    return at(world, player.x, player.y) if player else None


def ensure(world):
    all_villages = villages(world)
    for index, village in enumerate(all_villages):
        if not getattr(village, "name", ""):
            x, y = village.chunk_coords or (index, 0)
            prefixes = ("Alder", "Ash", "Birch", "Briar", "Cedar", "Elm", "Hazel", "Oak")
            suffixes = ("ford", "brook", "haven", "field", "wick", "stead", "ridge", "mere")
            base = prefixes[(x+3*y) % len(prefixes)] + suffixes[(x*3+y) % len(suffixes)]
            used = {v.name for v in all_villages if getattr(v, "name", "")}
            choices = [base, *[prefix + suffix for prefix in prefixes for suffix in suffixes]]
            village.name = next((name for name in choices if name not in used), f"New {base}")
    # Migrate the old world-wide record once, to its actual hall's settlement.
    legacy = world.__dict__.pop("politics", None)
    if not getattr(world, "settlement_governments_migrated", False):
        legacy = legacy or world.__dict__.pop("_legacy_politics", None)
    if legacy is not None and all_villages:
        owner = next((v for v in all_villages if any(b.id == legacy.town_hall_building_id for b in v.buildings)), None)
        owner = owner or current(world) or all_villages[0]
        owner.politics = legacy
    elif legacy is not None:
        world._legacy_politics = legacy
    world.settlement_governments_migrated = True
    player = getattr(world, "player", None)
    if player is not None and not hasattr(player, "civic_settlement_id"):
        home = current(world)
        player.civic_settlement_id = home.id if home else None


def government(world):
    # No repeated migration/settlement enumeration on every UI row.
    village = current(world)
    if village is not None:
        return village.politics
    if "_legacy_politics" not in world.__dict__:
        world._legacy_politics = PoliticsTracker()
    return world._legacy_politics


@contextmanager
def scope(world, village):
    previous = getattr(world, "_governance_settlement_id", None)
    world._governance_settlement_id = village.id
    try:
        yield
    finally:
        world._governance_settlement_id = previous


def residents(world):
    village = current(world)
    people = getattr(world, "village_npcs", [])
    if village is None:
        return people  # Legacy unit worlds without settlement geography.
    return [p for p in people if world._get_npc_settlement(p) is village]


def player_is_citizen(world):
    village = current(world)
    return village is None or getattr(world.player, "civic_settlement_id", None) == village.id


def record_arrival(world):
    village = at(world, world.player.x, world.player.y)
    sid = village.id if village else None
    previous = getattr(world, "player_last_settlement_id", None)
    world.player_last_settlement_id = sid
    if village is not None:
        known = getattr(world.player, "known_settlements", None)
        if known is None:
            known = world.player.known_settlements = {}
        known[sid] = {"name": village.name, "coords": world._get_village_anchor_coords(village)}
        if sid != previous:
            world.add_message_to_chat_log(f"You arrive in {village.name}.", category="system")
    elif previous is not None:
        world.add_message_to_chat_log("You leave the settlement for the surrounding countryside.", category="system")


def read_civic_notice(world):
    village = current(world)
    if village is None:
        return False
    from engine import DAY_LENGTH_TICKS, ELECTION_TERM_DAYS
    day = world.game_time // DAY_LENGTH_TICKS
    for name, office in village.politics.offices.items():
        due = max(0, office.last_elected_day + ELECTION_TERM_DAYS - day)
        world.add_message_to_chat_log(f"{village.name} — {name}: {world.get_office_holder_name(name)}; election in {due} days.")
    citizen = player_is_citizen(world)
    world.add_message_to_chat_log(f"Local tax: {village.tax_rate:.0%}. " +
        ("You are registered here and eligible at the next election. Local reputation and relationships determine votes."
         if citizen else "You are a visitor. Register here to stand in local elections (R on this board)."))
    return True


def register_citizen(world):
    village = current(world)
    if village is None or world.player.state.is_jailed:
        return False
    if any(o.holder_id == world.player.id for v in villages(world) for o in v.politics.offices.values()):
        world.add_message_to_chat_log("Finish your current term before moving your civic registration.")
        return False
    world.player.civic_settlement_id = village.id
    world.add_message_to_chat_log(f"You register as a citizen of {village.name}; you may stand at its next election.")
    return True


def read_destination(world, sid):
    village = next((v for v in villages(world) if v.id == sid), None)
    if village is None:
        return False
    coords = world._get_village_anchor_coords(village)
    if coords is None:
        return False
    if not hasattr(world.player, "known_settlements"):
        world.player.known_settlements = {}
    world.player.known_settlements[sid] = {"name": village.name, "coords": coords}
    world.player.travel_destination_id = sid
    world.add_message_to_chat_log(f"Road notice: {village.name}, town square at {coords[0]}, {coords[1]}. Destination marked in your field guide; travel on foot.")
    return True


def record_trade_relations(world, seller, buyer):
    from config import DAY_LENGTH_TICKS
    day = world.game_time // DAY_LENGTH_TICKS
    if not hasattr(world, "diplomatic_trade_days"):
        world.diplomatic_trade_days = {}
    pair = tuple(sorted((seller.id, buyer.id)))
    if world.diplomatic_trade_days.get(pair) == day:
        return
    world.diplomatic_trade_days[pair] = day
    seller.village_relationships[buyer.id] = min(100, seller.village_relationships.get(buyer.id, 0)+2)
    buyer.village_relationships[seller.id] = min(100, buyer.village_relationships.get(seller.id, 0)+2)


def procure_construction_material(world, village, blueprint, item_key):
    """Offscreen hauling moves a real item and real payment, without cloning it.

    Old isolated aggregate-only settlement fixtures retain their ledger path;
    registered world settlements must buy from actual stores.
    """
    atlas = getattr(world, "atlas", None)
    registered = atlas is not None and atlas.get_village(village.id) is village
    if not registered:
        from entities.items import ItemReference
        if village.supply.get(item_key, 0) <= 0:
            return False
        if not blueprint.deposit_item_reference(ItemReference(item_key)):
            return False
    else:
        payer = world.get_entity_by_id(blueprint.owner_id) if blueprint.owner_id is not None else next((b for b in village.buildings if b.building_type == "capital_hall"), None)
        if payer is None:
            return False
        supplier = next((b for b in village.buildings if b.building_inventory.get(item_key, 0) > 0), None)
        if supplier is None:
            return False
        price = 0 if supplier is payer or (blueprint.owner_id is not None and supplier.owner_id == blueprint.owner_id) else max(1, int(world.get_item_definition(item_key).get("value", 1)))
        if world._get_trade_money_balance(payer) < price:
            return False
        item = supplier.building_inventory.pop_item_reference(item_key)
        if item is None:
            return False
        if not blueprint.deposit_item_reference(item):
            supplier.building_inventory.add_item_reference(item)
            return False
        if price:
            world._set_trade_money_balance(payer, world._get_trade_money_balance(payer)-price)
            world._set_trade_money_balance(supplier, world._get_trade_money_balance(supplier)+price)
    village.supply[item_key] = max(0, village.supply.get(item_key, 0)-1)
    return True
