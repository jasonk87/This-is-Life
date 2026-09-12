"""Saved grooming time and stable identity. Rendering never advances either."""

import hashlib

from config import DAY_LENGTH_TICKS

STYLE_DAYS = {"none": 0.0, "stubble": 2.0, "mustache": 7.0, "short_beard": 7.0, "full_beard": 21.0}
EYES = ("brown", "hazel", "green", "blue", "gray")
BUILDS = ("slim", "average", "broad")


def identity_for(actor):
    """Read-only and RNG-independent, including for a not-yet-migrated save."""
    appearance = getattr(actor, "appearance", None)
    seed = hashlib.blake2b(
        str(getattr(actor, "id", getattr(actor, "name", "person"))).encode(), digest_size=4
    ).digest()
    face = getattr(appearance, "face_variant", -1)
    return (
        int(face) % 4 if face is not None and face >= 0 else seed[0] % 4,
        getattr(appearance, "eye_color", "") or EYES[seed[1] % len(EYES)],
        getattr(appearance, "body_build", "") or BUILDS[seed[2] % len(BUILDS)],
    )


def style_for_days(days):
    return (
        "full_beard"
        if days >= 21
        else "short_beard" if days >= 7 else "stubble" if days >= 2 else "none"
    )


def advance_actor_appearance(actor, tick):
    appearance = getattr(actor, "appearance", None)
    if appearance is None or getattr(actor, "animal_type", None):
        return
    face, eyes, build = identity_for(actor)
    appearance.face_variant, appearance.eye_color, appearance.body_build = face, eyes, build
    style = getattr(appearance, "facial_hair", "none")
    last = getattr(appearance, "beard_last_tick", None)
    days = getattr(appearance, "beard_days", None)
    if days is None or getattr(appearance, "beard_style_at_last_tick", None) != style:
        # Honor external grooming/customization edits, not a stale accumulated length.
        days, last = STYLE_DAYS.get(style, 0.0), tick
    if last is None:
        last = tick
    adult = getattr(actor, "age", 25) >= 18
    enabled = getattr(appearance, "beard_growth_enabled", None)
    if enabled is None:
        enabled = adult and (getattr(actor, "gender", None) == "male" or style != "none")
        if adult:
            # Persist the resolved capability; shaving must not switch it off.
            # Children leave auto unresolved until they become adults.
            appearance.beard_growth_enabled = enabled
    if enabled and adult and not getattr(getattr(actor, "physical", None), "is_dead", False):
        days = min(60.0, days + max(0, tick - last) / max(1, DAY_LENGTH_TICKS))
        # A maintained mustache remains a mustache; length alone does not
        # invent a different groomed shape across the cheeks.
        if style != "mustache":
            style = style_for_days(days)
            appearance.facial_hair = style
    appearance.beard_days = days
    appearance.beard_last_tick = max(last, tick)
    appearance.beard_style_at_last_tick = style


def advance_appearance(world):
    tick = int(getattr(world, "game_time", 0))
    # Hour bucket gating also catches time jumps without a modulo-equality trap.
    bucket = tick // max(1, DAY_LENGTH_TICKS // 24)
    if getattr(world, "_appearance_hour", None) == bucket:
        return
    world._appearance_hour = bucket
    seen = set()
    for actor in [getattr(world, "player", None), *getattr(world, "all_npcs", [])]:
        if actor is None or id(actor) in seen:
            continue
        seen.add(id(actor))
        advance_actor_appearance(actor, tick)


def groom(actor, world, style="none"):
    """Explicit action, with an actual owned/equipped cutting tool; no auto-shave."""
    if style not in {"none", "stubble", "short_beard", "mustache"}:
        return False, "That grooming style is not available."
    appearance = getattr(actor, "appearance", None)
    physical = getattr(actor, "physical", None)
    if (
        appearance is None
        or getattr(physical, "is_dead", False)
        or getattr(actor, "is_sleeping", False)
        or getattr(getattr(actor, "state", None), "is_sleeping", False)
    ):
        return False, "You cannot groom right now."
    economic, equipment = getattr(actor, "economic", None), getattr(actor, "equipment", None)
    inventories = (
        getattr(economic, "inventory", {}) or {},
        getattr(economic, "npc_inventory", {}) or {},
    )
    weapon = getattr(getattr(equipment, "weapon", None), "item_key", None)
    if not (
        any(inventory.get("knife_stone", 0) > 0 for inventory in inventories)
        or weapon == "knife_stone"
    ):
        return False, "You need a knife to shave or trim."
    tick = int(getattr(world, "game_time", 0))
    advance_actor_appearance(actor, tick)
    target = STYLE_DAYS[style]
    if target > appearance.beard_days:
        return False, "Your facial hair is not long enough for that trim."
    appearance.facial_hair = style
    appearance.beard_days, appearance.beard_last_tick = target, tick
    appearance.beard_style_at_last_tick = style
    return True, "You shave your facial hair." if style == "none" else "You trim your facial hair."
