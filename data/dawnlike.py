"""Named DawnLike sprite coordinates and selection helpers."""

from __future__ import annotations


DAWNLIKE_COLUMNS = 16
DAWNLIKE_BASE_CODEPOINT = 0xE000


def dawnlike(col: int, row: int) -> int:
    """Return the private-use codepoint for a DawnLike tile cell."""
    return DAWNLIKE_BASE_CODEPOINT + (row * DAWNLIKE_COLUMNS) + col


HUMAN_SPRITES = {
    "player": dawnlike(0, 0),
    "male_commoner": dawnlike(0, 0),
    "female_commoner": dawnlike(6, 0),
    "male_child": dawnlike(0, 4),
    "female_child": dawnlike(2, 4),
    "merchant": dawnlike(7, 0),
    "traveling_merchant": dawnlike(7, 8),
    "guard": dawnlike(0, 19),
    "sheriff": dawnlike(7, 16),
    "hunter": dawnlike(6, 21),
    "scribe": dawnlike(7, 1),
    "healer": dawnlike(0, 3),
    "blacksmith": dawnlike(0, 16),
    "farmer": dawnlike(0, 8),
    "woodcutter": dawnlike(2, 17),
    "carpenter": dawnlike(1, 17),
    "miller": dawnlike(7, 1),
    "baker": dawnlike(5, 16),
    "fisherman": dawnlike(2, 21),
    "tavern_keeper": dawnlike(6, 21),
    "town_official": dawnlike(5, 22),
    "cultist": dawnlike(3, 23),
    "raider": dawnlike(0, 23),
    "unemployed": dawnlike(1, 0),
    "sleeping": dawnlike(1, 0),
    "sitting": dawnlike(7, 0),
}


PROFESSION_SPRITES = {
    "Blacksmith": HUMAN_SPRITES["blacksmith"],
    "Baker": HUMAN_SPRITES["baker"],
    "Carpenter": HUMAN_SPRITES["carpenter"],
    "Child": HUMAN_SPRITES["male_child"],
    "Cultist": HUMAN_SPRITES["cultist"],
    "Deputy": HUMAN_SPRITES["guard"],
    "Farmer": HUMAN_SPRITES["farmer"],
    "Fisherman": HUMAN_SPRITES["fisherman"],
    "Guard": HUMAN_SPRITES["guard"],
    "Healer": HUMAN_SPRITES["healer"],
    "Hunter": HUMAN_SPRITES["hunter"],
    "Lumber Mill Foreman": HUMAN_SPRITES["woodcutter"],
    "Merchant": HUMAN_SPRITES["merchant"],
    "Miller": HUMAN_SPRITES["miller"],
    "Miner": HUMAN_SPRITES["blacksmith"],
    "Raider": HUMAN_SPRITES["raider"],
    "Scribe": HUMAN_SPRITES["scribe"],
    "Sheriff": HUMAN_SPRITES["sheriff"],
    "Tavern Keeper": HUMAN_SPRITES["tavern_keeper"],
    "Town Official": HUMAN_SPRITES["town_official"],
    "Traveling Merchant": HUMAN_SPRITES["traveling_merchant"],
    "Unemployed": HUMAN_SPRITES["unemployed"],
    "Villager": HUMAN_SPRITES["unemployed"],
    "Woodcutter": HUMAN_SPRITES["woodcutter"],
}


ANIMAL_SPRITES = {
    "deer": dawnlike(6, 80),
    "bear": dawnlike(0, 89),
    "fish": dawnlike(1, 106),
    "wolf": dawnlike(2, 66),
    "dire_wolf": dawnlike(2, 67),
    "sheep": dawnlike(5, 48),
    "fox": dawnlike(0, 68),
    "boar": dawnlike(0, 64),
    "salmon": dawnlike(0, 106),
    "trout": dawnlike(1, 106),
    "rabbit": dawnlike(0, 105),
    "bison": dawnlike(4, 81),
    "badger": dawnlike(1, 105),
}


TREE_SPRITES = {
    "tree_generic": dawnlike(0, 192),
    "stump_generic": dawnlike(4, 192),
    "oak_tree": dawnlike(0, 192),
    "apple_tree": dawnlike(0, 198),
    "pear_tree": dawnlike(0, 213),
    "sapling": dawnlike(0, 216),
}


WORLD_TILE_SPRITES = {
    "plains": dawnlike(8, 133),
    "forest": TREE_SPRITES["tree_generic"],
    "road": dawnlike(14, 134),
    "wood_wall": dawnlike(8, 147),
    "stone_wall": dawnlike(8, 149),
    "brick_wall": dawnlike(8, 148),
    "plaster_wall": dawnlike(8, 142),
    "log_wall": dawnlike(9, 147),
    "door": dawnlike(1, 145),
    "wood_floor": dawnlike(0, 160),
    "stone_floor": dawnlike(3, 162),
    "brick_floor": dawnlike(4, 162),
    "dirt_floor": dawnlike(0, 162),
    "window": dawnlike(0, 177),
    "water": dawnlike(1, 160),
    "deep_water": dawnlike(2, 160),
    "mountain": dawnlike(7, 162),
    "snow": dawnlike(5, 162),
    "tall_grass": dawnlike(5, 178),
    "flower": dawnlike(7, 178),
    "well": dawnlike(4, 177),
    "capital_hall_wall": dawnlike(8, 143),
    "jail_bars": dawnlike(0, 148),
    "sheriff_office_wall": dawnlike(8, 152),
    "tree_generic": TREE_SPRITES["tree_generic"],
    "boulder": dawnlike(2, 178),
    "fire_trap_active": dawnlike(6, 160),
    "fire_trap_hidden": dawnlike(0, 160),
    "stump_generic": TREE_SPRITES["stump_generic"],
    "sapling": TREE_SPRITES["sapling"],
    "tilled_soil": dawnlike(0, 149),
    "wheat_plant_growing": dawnlike(9, 133),
    "wheat_plant": dawnlike(10, 133),
    "cracked_stone_wall": dawnlike(8, 150),
    "mossy_cobblestone": dawnlike(10, 133),
}


WORLD_DECORATION_SPRITES = {
    "wooden_door_closed": dawnlike(1, 145),
    "wooden_door_open": dawnlike(7, 144),
    "iron_door_closed": dawnlike(4, 144),
    "iron_door_open": dawnlike(7, 145),
    "chest_wooden": dawnlike(0, 143),
    "storage": dawnlike(0, 143),
    "bed_simple": dawnlike(0, 185),
    "wooden_chair": dawnlike(0, 183),
    "workbench": dawnlike(0, 181),
    "counter": dawnlike(1, 181),
    "desk": dawnlike(0, 182),
    "dresser": dawnlike(2, 182),
    "forge": dawnlike(1, 185),
    "anvil": dawnlike(0, 187),
    "loom": dawnlike(6, 185),
    "smoking_rack": dawnlike(3, 185),
    "wooden_table": dawnlike(1, 183),
    "wall_shelf": dawnlike(0, 180),
    "shelf": dawnlike(0, 180),
    "fire_pit_simple": dawnlike(5, 207),
    "fire_pit_lit": dawnlike(6, 207),
    "fireplace": dawnlike(5, 207),
    "rubble": dawnlike(2, 178),
    "bones": dawnlike(1, 178),
    "bookshelf": dawnlike(0, 182),
    "wooden_bed": dawnlike(1, 185),
    "stone_anvil": dawnlike(0, 187),
    "wolf_den": dawnlike(7, 147),
    "rabbit_hole": dawnlike(5, 143),
    "bear_cave": dawnlike(7, 144),
    "fox_burrow": dawnlike(5, 143),
    "badger_sett": dawnlike(5, 143),
    "corpse_humanoid": dawnlike(2, 188),
    "corpse_animal": dawnlike(0, 189),
    "thicket": dawnlike(0, 223),
}


ITEM_SPRITES = {
    "raw_log": dawnlike(2, 185),
    "stone_chunk": dawnlike(2, 178),
    "medicinal_herb": dawnlike(1, 243),
    "herb_generic": dawnlike(6, 241),
    "wheat": dawnlike(6, 243),
    "flour": dawnlike(1, 245),
    "bread": dawnlike(0, 245),
    "iron_ore": dawnlike(0, 98),
    "iron_ingot": dawnlike(1, 98),
    "coal": dawnlike(0, 106),
    "wooden_plank": dawnlike(2, 185),
    "workbench": WORLD_DECORATION_SPRITES["workbench"],
    "forge": WORLD_DECORATION_SPRITES["forge"],
    "anvil": WORLD_DECORATION_SPRITES["anvil"],
    "wooden_chair": WORLD_DECORATION_SPRITES["wooden_chair"],
    "wooden_table": WORLD_DECORATION_SPRITES["wooden_table"],
    "bed_simple": WORLD_DECORATION_SPRITES["bed_simple"],
    "desk": WORLD_DECORATION_SPRITES["desk"],
    "counter": WORLD_DECORATION_SPRITES["counter"],
    "dresser": WORLD_DECORATION_SPRITES["dresser"],
    "storage": WORLD_DECORATION_SPRITES["storage"],
    "shelf": WORLD_DECORATION_SPRITES["shelf"],
    "fireplace": WORLD_DECORATION_SPRITES["fireplace"],
    "chest_wooden": WORLD_DECORATION_SPRITES["chest_wooden"],
    "bookshelf": WORLD_DECORATION_SPRITES["bookshelf"],
    "wooden_bed": WORLD_DECORATION_SPRITES["wooden_bed"],
    "stone_anvil": WORLD_DECORATION_SPRITES["stone_anvil"],
    "lumber_processed": dawnlike(2, 185),
    "wheat_seeds": dawnlike(4, 243),
    "axe_stone": dawnlike(0, 209),
    "broken_tool_handle": dawnlike(0, 243),
    "lockpick": dawnlike(2, 243),
    "healing_salve": dawnlike(7, 241),
    "herbal_remedy": dawnlike(7, 241),  # Shares the salve sprite, matching the existing water_flask precedent below.
    "unlit_torch": dawnlike(2, 240),
    "torch_lit": dawnlike(0, 240),
    "burnt_out_torch": dawnlike(7, 240),
    "water_flask": dawnlike(7, 241),
    "apple": dawnlike(0, 242),
    "pear": dawnlike(5, 242),
    "acorn": dawnlike(2, 242),
    "sapling": TREE_SPRITES["sapling"],
    "raw_venison": dawnlike(0, 244),
    "raw_meat": dawnlike(1, 244),
    "cooked_meat": dawnlike(4, 245),
    "smoked_meat": dawnlike(2, 245),
    "animal_pelt": dawnlike(4, 244),
    "tanned_leather": dawnlike(4, 244),
    "raw_mutton": dawnlike(0, 244),
    "raw_wool": dawnlike(3, 241),
    "rusty_sword": dawnlike(3, 208),
    "crude_spear": dawnlike(6, 224),
    "short_bow": dawnlike(2, 225),
    "arrow": dawnlike(7, 96),
    "wooden_shield": dawnlike(4, 99),
    "leather_jerkin": dawnlike(3, 98),
    "iron_helmet": dawnlike(0, 99),
    "stone_pickaxe": dawnlike(0, 227),
    "stone_hoe": dawnlike(2, 227),
    "iron_sword": dawnlike(4, 208),
    "iron_breastplate": dawnlike(4, 98),
    "fur_cloak": dawnlike(4, 244),
    "hooded_cowl": dawnlike(3, 244),
    "fish": dawnlike(1, 106),
    "knife_stone": dawnlike(1, 224),
    "shears": dawnlike(1, 188),
    "loom": WORLD_DECORATION_SPRITES["loom"],
    "cloth": dawnlike(3, 244),
    "cloth_tunic": dawnlike(3, 244),
    "fishing_rod": dawnlike(1, 97),
    "raw_fish": dawnlike(1, 106),
    "cooked_fish": dawnlike(2, 245),
    "smoked_fish": dawnlike(2, 245),
    "cooked_venison": dawnlike(4, 245),
    "cooked_mutton": dawnlike(4, 245),
    "book_census": dawnlike(3, 98),
    "book_chronicle": dawnlike(4, 98),
    "rotten_food": dawnlike(0, 106),
}


WEATHER_SPRITES = {
    "clear": dawnlike(0, 160),
    "rain": dawnlike(7, 96),
    "snow": dawnlike(0, 228),
}


# Equipment overlay sprite definitions.
# Maps equipment item keys from entities/items.py to (codepoint, anchor_x, anchor_y, z_order).
# Anchor (x, y) is a fraction within the zoomed cell grid (0.0–1.0 from top-left).
# z_order controls draw order: 0 = bottom (body armour), 2 = top (held items).
EQUIPMENT_OVERLAY_SPRITES: dict[str, tuple[int, float, float, int]] = {
    # Weapons (z=2 — held in hand, drawn on top)
    "rusty_sword":    (ITEM_SPRITES["rusty_sword"],     0.60, 0.35, 2),
    "iron_sword":     (ITEM_SPRITES["iron_sword"],      0.60, 0.35, 2),
    "crude_spear":    (ITEM_SPRITES["crude_spear"],     0.65, 0.25, 2),
    "short_bow":      (ITEM_SPRITES["short_bow"],       0.55, 0.20, 2),
    "knife_stone":    (ITEM_SPRITES["knife_stone"],     0.55, 0.40, 2),
    "axe_stone":      (ITEM_SPRITES["axe_stone"],       0.58, 0.30, 2),
    "stone_pickaxe":  (ITEM_SPRITES["stone_pickaxe"],   0.58, 0.30, 2),
    "stone_hoe":      (ITEM_SPRITES["stone_hoe"],       0.58, 0.30, 2),
    "fishing_rod":    (ITEM_SPRITES["fishing_rod"],     0.62, 0.35, 2),
    # Shields (z=2 — held in off-hand)
    "wooden_shield":  (ITEM_SPRITES["wooden_shield"],   0.10, 0.35, 2),
    # Head wear (z=1 — mid layer)
    "iron_helmet":    (ITEM_SPRITES["iron_helmet"],     0.30, 0.05, 1),
    "hooded_cowl":    (ITEM_SPRITES["hooded_cowl"],     0.30, 0.05, 1),
    # Body armour (z=0 — under layer)
    "leather_jerkin":   (ITEM_SPRITES["leather_jerkin"],    0.25, 0.25, 0),
    "iron_breastplate": (ITEM_SPRITES["iron_breastplate"],  0.25, 0.25, 0),
    "fur_cloak":        (ITEM_SPRITES["fur_cloak"],         0.25, 0.20, 0),
    "cloth_tunic":      (ITEM_SPRITES["cloth_tunic"],       0.25, 0.25, 0),
}


# Appearance overlay sprite definitions (hair, facial hair) - the
# appearance-driven counterpart to EQUIPMENT_OVERLAY_SPRITES above.
#
# NOTE: both tables below are intentionally empty. The DawnLike sheet in
# use here (assets/dawnlike_combined.png) is a library of complete,
# pre-baked character sprites (see HUMAN_SPRITES above) - it does not
# contain any separable hair or facial-hair tiles to stamp as an overlay.
# This was confirmed by visually surveying every populated tile in the
# sheet's character block (rows 0-42, where HUMAN_SPRITES/
# PROFESSION_SPRITES live) plus its GUI icon block (rows 256-271) and item
# block (rows 96-106) - none contain isolated hair/beard art. See the
# visual-overhaul options report for real asset-pack candidates that do
# ship layered hair/beard art (e.g. Shad.din's "Top-Down Shortcut:
# Characters" pack has 60+ hairstyles and 20+ facial-hair styles as
# separate sprites, though its commercial license needs confirming; the
# Universal LPC Spritesheet is another option but in a different,
# side-view art style).
#
# Once suitable tile art is sourced, populate these the same way
# ITEM_SPRITES/EQUIPMENT_OVERLAY_SPRITES are populated above - e.g.
# HAIR_SPRITES["short"] = dawnlike(col, row) - and _get_appearance_overlays
# below will start drawing them immediately with no other code changes:
# the entity data model (Appearance, in entities/base.py), the
# compositing/z-order logic, and the console_renderer.py wiring are all
# already in place and tested against this exact "not catalogued yet"
# empty-dict state.
HAIR_SPRITES: dict[str, int] = {}
BEARD_SPRITES: dict[str, int] = {}

# Anchor/z-order for appearance overlays, in the same (anchor_x, anchor_y,
# z_order) shape EQUIPMENT_OVERLAY_SPRITES' tuples use. z_order=0 puts
# hair/facial hair in the same paint tier as body armor/clothing (i.e.
# "attached to the body"), strictly below headwear's z=1 - though in
# practice hair is additionally suppressed outright whenever a head-slot
# item is equipped (see _get_appearance_overlays' JUDGMENT CALL note
# below), rather than relying on z-order paint-over alone.
#
# Chosen so hair and beard land in DIFFERENT quadrant cells at zoom 2/3/4
# (see _draw_overlay_stamp in console_renderer.py: an anchor fraction
# snaps to one whole zoom-grid cell, e.g. only a 4x4 grid of possible
# positions at zoom=4 - it is not free sub-tile pixel placement), verified
# by hand against every EQUIPMENT_OVERLAY_SPRITES anchor above so a beard
# doesn't silently get painted over by body armor at the same z_order.
# Full collision-freedom isn't achievable at this resolution though - e.g.
# hair and body-armor anchors still land in the same zoom=3 cell, same as
# some existing equipment-to-equipment anchor pairs already do at zoom=2.
# That coarseness is an inherent property of quadrant-snapped anchors at
# low zoom, not something introduced here; worth re-tuning once real hair/
# beard art makes the collisions visible rather than theoretical.
HAIR_OVERLAY_ANCHOR: tuple[float, float, int] = (0.30, 0.05, 0)
BEARD_OVERLAY_ANCHOR: tuple[float, float, int] = (0.55, 0.15, 0)


def _get_appearance_overlays(entity) -> list[tuple[int, float, float, int]]:
    """
    Mirrors _get_equipment_overlays: returns (codepoint, anchor_x, anchor_y,
    z_order) tuples for the entity's hairstyle and facial hair, drawn
    through the exact same zoomed-cell-stamping pipeline in
    console_renderer.py. Returns [] whenever the entity has no
    `appearance` component, or its hairstyle/facial_hair value (however
    plausible) isn't catalogued in HAIR_SPRITES/BEARD_SPRITES - which, as
    of this writing, is every value, since both tables are empty (see the
    NOTE above them). This is a deliberate no-op today, not a bug: the
    function, the data model, and the renderer wiring are all ready to go
    the moment real tile art is added.

    JUDGMENT CALL: a hat/helmet/hood in the head equipment slot suppresses
    hair entirely (a hood covers hair) rather than relying on z-order
    paint-over, which could leave a sliver of hair visible around a
    helmet's edges depending on anchor offsets. Facial hair is NOT
    suppressed by headwear (most headwear catalogued here - berets, caps,
    crowns - doesn't cover the lower face). Both of these are reasonable
    defaults, not confirmed product decisions - worth revisiting once
    there's real hair/beard art to look at.
    """
    overlays: list[tuple[int, float, float, int]] = []
    appearance = getattr(entity, "appearance", None)
    if appearance is None:
        return overlays

    equipment = getattr(entity, "equipment", None)
    head_slot_occupied = False
    if equipment is not None:
        head_slot_occupied = bool(getattr(getattr(equipment, "head", None), "item_key", None)) or bool(
            (getattr(equipment, "equipped_armor", None) or {}).get("head")
        )

    hairstyle = getattr(appearance, "hairstyle", "none") or "none"
    if hairstyle != "none" and not head_slot_occupied:
        codepoint = HAIR_SPRITES.get(hairstyle)
        if codepoint is not None:
            ax, ay, az = HAIR_OVERLAY_ANCHOR
            overlays.append((codepoint, ax, ay, az))

    facial_hair = getattr(appearance, "facial_hair", "none") or "none"
    if facial_hair != "none":
        codepoint = BEARD_SPRITES.get(facial_hair)
        if codepoint is not None:
            ax, ay, az = BEARD_OVERLAY_ANCHOR
            overlays.append((codepoint, ax, ay, az))

    overlays.sort(key=lambda entry: entry[3])
    return overlays


def get_human_sprite(
    gender: str | None = None,
    profession: str | None = None,
    age: int | None = None,
    is_player: bool = False,
) -> int:
    """Select a DawnLike sprite for a human actor."""
    if is_player:
        return HUMAN_SPRITES["player"]

    if age is not None and age < 18:
        return HUMAN_SPRITES["female_child" if gender == "female" else "male_child"]

    if profession:
        profession_sprite = PROFESSION_SPRITES.get(profession)
        if profession_sprite is not None:
            return profession_sprite

    if gender == "female":
        return HUMAN_SPRITES["female_commoner"]
    return HUMAN_SPRITES["male_commoner"]


def get_animal_sprite(animal_type: str | None) -> int:
    """Select a DawnLike sprite for an animal entity."""
    return ANIMAL_SPRITES.get(animal_type or "", ANIMAL_SPRITES["wolf"])


def get_entity_sprite(entity) -> int:
    """Select the render sprite for a player, villager, or animal-like entity."""
    if getattr(entity, "animal_type", None):
        return get_animal_sprite(getattr(entity, "animal_type", None))

    if getattr(getattr(entity, "schedule", None), "current_task", None) == "sleeping":
        return HUMAN_SPRITES["sleeping"]

    if getattr(getattr(entity, "state", None), "is_sitting", False):
        return HUMAN_SPRITES["sitting"]

    profession = getattr(getattr(entity, "economic", None), "profession", None)
    if profession == "Creature" and getattr(entity, "name", "") == "Player":
        return HUMAN_SPRITES["player"]

    if entity.__class__.__name__ == "Player" or getattr(entity, "name", None) == "Player":
        return get_human_sprite(is_player=True)

    return get_human_sprite(
        gender=getattr(entity, "gender", None),
        profession=profession,
        age=getattr(entity, "age", None),
    )


def _get_equipment_overlays(entity) -> list[tuple[int, float, float, int]]:
    """
    Return a list of (codepoint, anchor_x, anchor_y, z_order) tuples for
    every piece of visible equipment the entity is wearing or holding.
    Returns an empty list if the entity has no equipment or no matching
    overlay sprite is defined.
    """
    overlays: list[tuple[int, float, float, int]] = []
    equipment = getattr(entity, "equipment", None)
    if equipment is None:
        return overlays

    seen_sprites: set[int] = set()

    def try_add(item_key: str | None):
        if item_key is None:
            return
        entry = EQUIPMENT_OVERLAY_SPRITES.get(item_key)
        if entry is not None:
            codepoint, ax, ay, az = entry
            if codepoint not in seen_sprites:
                seen_sprites.add(codepoint)
                overlays.append((codepoint, ax, ay, az))

    # Check EquipmentSlot-based slots
    try_add(getattr(getattr(equipment, "head", None), "item_key", None))
    try_add(getattr(getattr(equipment, "body", None), "item_key", None))
    try_add(getattr(getattr(equipment, "weapon", None), "item_key", None))

    # Check equipped_armor dict (fallback for head/body items stored there)
    armor = getattr(equipment, "equipped_armor", {})
    if isinstance(armor, dict):
        try_add(armor.get("head"))
        try_add(armor.get("body"))

    # Sort by z_order so body armour is drawn first and weapons last
    overlays.sort(key=lambda x: x[3])
    return overlays


def all_catalog_codepoints() -> dict[str, int]:
    """Return every named DawnLike codepoint for validation."""
    catalog = {}
    for group_name, mapping in (
        ("humans", HUMAN_SPRITES),
        ("professions", PROFESSION_SPRITES),
        ("animals", ANIMAL_SPRITES),
        ("trees", TREE_SPRITES),
        ("world_tiles", WORLD_TILE_SPRITES),
        ("world_decor", WORLD_DECORATION_SPRITES),
        ("items", ITEM_SPRITES),
        ("weather", WEATHER_SPRITES),
    ):
        for key, codepoint in mapping.items():
            catalog[f"{group_name}.{key}"] = codepoint
    return catalog
