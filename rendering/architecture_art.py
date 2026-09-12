"""Deterministic architectural forms fitted to actual building footprints.

Facade ornament is not a simulated object or a new floor. No random state,
inventory, ownership, doors, work zones or visibility is changed here.
"""

from functools import lru_cache
from runtime_compat import np
from rendering.village_art import rect, tone, STYLES, DEFAULT

FORMS = {
    "house": "hip",
    "common_house": "longhouse",
    "shack": "shed",
    "large_house": "cross",
    "tavern": "cross",
    "bakery": "gable",
    "blacksmith_shop": "monitor",
    "general_store": "mansard",
    "library": "gable",
    "clinic": "hip",
    "capital_hall": "pediment",
    "city_hall": "pediment",
    "sheriff_office": "parapet",
    "guard_post": "parapet",
    "jail": "parapet",
    "barracks": "longhouse",
    "lumber_mill": "shed",
    "lumber_shed": "shed",
    "carpenter_shop": "monitor",
    "mill": "gable",
    "storage_building": "shed",
    "butcher_shop": "mansard",
    "hunting_lodge": "longhouse",
}


def roof_form(kind, variant=None):
    if kind == "house" and variant == "house_rich":
        return "cross"
    if kind == "house" and variant == "house_poor":
        return "longhouse"
    return FORMS.get(kind, "hip")


def line(image, x0, y0, x1, y1, color, width=1):
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for step in range(steps + 1):
        x = round(x0 + (x1 - x0) * step / steps)
        y = round(y0 + (y1 - y0) * step / steps)
        rect(image, x, y, width, width, color)


def window(image, x, y, w, h, trim, arched=False, bars=False):
    rect(image, x - 2, y - 2, w + 4, h + 4, trim)
    rect(image, x, y, w, h, (38, 57, 59))
    rect(image, x + 1, y + 1, max(1, w // 2 - 2), max(1, h // 2 - 1), (97, 127, 119))
    rect(image, x + w // 2 - 1, y, 2, h, tone(trim, 9))
    rect(image, x, y + h // 2, w, 2, tone(trim, 9))
    if bars:
        for xx in range(x + 2, x + w, 4):
            rect(image, xx, y, 1, h, (26, 32, 32))
    if arched:
        for xx in range(w + 4):
            edge = min(xx, w + 3 - xx)
            rect(image, x - 2 + xx, y - 4 - min(3, edge // 3), 1, 3, trim)
    rect(image, x - 3, y + h + 2, w + 6, 2, tone(trim, 25))


def detail_wall(image, kind, side, has_window, door, interior=False):
    _, plaster, trim, _ = STYLES.get(kind, DEFAULT)
    if door:
        # The visible opening stays exactly where the original door is.
        if kind in {"bakery", "library", "clinic"}:
            for i in range(5):
                rect(image, 5 + i, 5 - i, 2, 2, tone(plaster, 22))
                rect(image, 25 - i, 5 - i, 2, 2, tone(plaster, 22))
        elif kind in {"blacksmith_shop", "jail", "sheriff_office", "guard_post"}:
            rect(image, 4, 1, 25, 3, tone(plaster, 15))
            for yy in (7, 16, 25):
                rect(image, 5, yy, 2, 2, (39, 43, 40))
                rect(image, 25, yy, 2, 2, (39, 43, 40))
        return image
    # Replace the generic panels before adding type-specific windows.
    rect(image, 3, 5, 26, 21, plaster)
    if kind in {
        "blacksmith_shop",
        "jail",
        "sheriff_office",
        "capital_hall",
        "city_hall",
        "guard_post",
    }:
        for yy in (10, 18, 25):
            rect(image, 3, yy, 26, 1, tone(plaster, -18))
            rect(image, 8 if yy == 18 else 20, yy - 6, 1, 6, tone(plaster, -16))
    elif kind in {"lumber_mill", "lumber_shed", "carpenter_shop", "hunting_lodge", "shack"}:
        for yy in range(6, 26, 5):
            rect(image, 3, yy, 26, 1, tone(plaster, -27))
            rect(image, 4, yy + 1, 24, 1, tone(plaster, 10))
    elif not interior and kind in {
        "house",
        "common_house",
        "large_house",
        "tavern",
        "general_store",
    }:
        line(image, 3, 6, 14, 24, trim, 2)
        line(image, 27, 6, 17, 24, trim, 2)
    if has_window:
        if kind in {"jail", "guard_post", "sheriff_office"}:
            window(image, 13, 9, 8, 13, trim, bars=True)
        elif kind in {"general_store", "butcher_shop"}:
            window(image, 6, 9, 22, 13, trim)
        elif kind in {"bakery", "library", "clinic"}:
            window(image, 10, 10, 13, 12, trim, arched=True)
        elif kind in {"lumber_mill", "lumber_shed", "blacksmith_shop", "carpenter_shop"}:
            rect(image, 7, 10, 20, 12, trim)
            for yy in (11, 14, 17, 20):
                rect(image, 8, yy, 18, 1, tone(plaster, -28))
        else:
            window(image, 10, 9, 13, 12, trim)
            rect(image, 6, 9, 3, 13, tone(trim, 30))
            rect(image, 24, 9, 3, 13, tone(trim, 30))
    return image


def tiled_slope(image, x0, y0, x1, y1, color, material="tile"):
    """Texture within an already painted plane, preserving silhouette edges."""
    region = image[y0:y1, x0:x1]
    y, x = np.indices(region.shape[:2])
    y, x = y + y0, x + x0
    shade = ((x * 13 + y * 7) // 5) % 5 - 2
    if material == "thatch":
        shade += np.where((x % 4 == 1) & (y % 15 < 11), 11, np.where(x % 4 == 0, -8, 0))
        shade -= np.where(y % 24 < 2, 15, 0)
    elif material == "board":
        shade += np.where(x % 9 == 0, -22, np.where(x % 9 == 1, 8, 0))
        shade -= np.where(((x // 9 + y // 23) % 5 == 0) & (y % 23 == 0), 14, 0)
    else:
        shade += np.where(y % 8 == 0, -23, np.where(y % 8 == 1, 11, 0))
        shade -= np.where(((x + (y // 8 % 2) * 7) % 14 == 0) & (y % 8 > 1), 13, 0)
    region[:, :, :3] = np.clip(region[:, :, :3].astype(np.int16) + shade[:, :, None], 0, 255)


def gable(image, cx, top, bottom, half, roof, plaster, trim, kind):
    """A street-facing gable integrated in the existing roof, not a new room."""
    for y in range(top, bottom):
        span = max(1, min(half, (y - top) * half // max(1, bottom - top)))
        rect(image, cx - span, y, span * 2 + 1, 1, plaster)
        rect(image, cx - span, y, 3, 1, trim)
        rect(image, cx + span - 2, y, 3, 1, trim)
    line(image, cx, top, cx - half, bottom, tone(roof, 16), 3)
    line(image, cx, top, cx + half, bottom, tone(roof, -25), 3)
    rect(image, cx - 1, top + 4, 3, bottom - top - 4, trim)
    rect(image, cx - half, bottom - 2, half * 2, 3, trim)
    if half >= 25:
        if kind in {"capital_hall", "city_hall"}:
            for dx in (-18, -6, 6, 18):
                rect(image, cx + dx, bottom - 15, 3, 13, tone(plaster, -35))
        elif kind == "tavern":
            for dx in (-21, 7):
                window(image, cx + dx, bottom - 17, 12, 11, trim)
        else:
            window(image, cx - 7, bottom - 18, 14, 12, trim, arched=kind in {"bakery", "library"})


@lru_cache(maxsize=128)
def roof_surface(kind, width, height, entrance, variant=None):
    from rendering.village_art import wall_surface

    roof, plaster, trim, _ = STYLES.get(kind, DEFAULT)
    form = roof_form(kind, variant)
    w, h = width * 32, height * 32
    image = np.zeros((h, w, 4), dtype=np.uint8)
    if width < 3 or height < 3:
        return image
    eaves = h - 35
    ridge = max(20, eaves // 3)
    thatched = (
        kind in {"house", "common_house", "shack", "hunting_lodge"} and variant != "house_rich"
    )
    material = "thatch" if thatched else "board" if form == "shed" else "tile"
    for y in range(5, eaves):
        if form in {"gable", "pediment"}:
            inset = 5 + max(0, 14 - y)
        elif form in {"monitor", "shed", "parapet"}:
            inset = 5 + max(0, 10 - y)
        else:
            inset = max(4, 25 - y, y - (eaves - 18))
        delta = -14 if y < ridge else 0
        if form == "shed":
            delta = 9 - y * 22 // max(1, eaves)
        rect(image, inset, y, w - inset * 2, 1, tone(roof, delta))
        if form in {"gable", "pediment"}:
            rect(image, inset, y, w // 2 - inset, 1, tone(roof, 14))
            rect(image, w // 2, y, w // 2 - inset, 1, tone(roof, -22))
        elif form == "mansard":
            rect(image, inset, y, w - inset * 2, 1, tone(roof, -22))
            if y < eaves - 30:
                rect(image, max(inset, 28), y, w - max(inset, 28) * 2, 1, tone(roof, 7))
        elif form == "hip":
            edge = min((eaves - y) // 3, w // 3)
            if edge > inset:
                rect(image, inset, y, edge - inset, 1, tone(roof, delta - 15))
                rect(image, w - edge, y, edge - inset, 1, tone(roof, delta - 15))
    tiled_slope(image, 0, 5, w, eaves, roof, material)
    for column in range(width):
        image[h - 32 : h, column * 32 : (column + 1) * 32] = wall_surface(
            kind, "horizontal", column % 3 == 1, None
        )
    rect(image, 3, eaves, w - 6, 5, tone(trim, -19))
    rect(image, 4, eaves + 5, w - 8, 2, tone(plaster, -40))
    if form in {"gable", "pediment"}:
        rect(image, w // 2 - 2, 5, 5, eaves - 8, tone(roof, 24))
        rect(image, w // 2 + 3, 5, 2, eaves - 8, tone(roof, -32))
        half = min(w // 2 - 8, 54 if form == "gable" else w // 3)
        gable(image, w // 2, eaves - half + 2, eaves, half, roof, plaster, trim, kind)
    elif form == "cross":
        rect(image, 12, ridge - 3, w - 24, 4, tone(roof, 25))
        half = min(50, w // 3)
        for y in range(ridge + 3, eaves - 30):
            span = min(half, (y - ridge) // 2 + 5)
            rect(image, w // 2 - span, y, span, 1, tone(roof, 19))
            rect(image, w // 2, y, span, 1, tone(roof, -9))
            rect(image, w // 2 - 1, y, 3, 1, tone(roof, 31))
        gable(image, w // 2, eaves - half, eaves, half, roof, plaster, trim, kind)
    elif form == "monitor":
        # Long raised vent in the smith/workshop roof; no moving machinery.
        rect(image, 18, ridge - 12, w - 36, 23, tone(trim, -17))
        rect(image, 16, ridge - 15, w - 32, 5, tone(roof, 27))
        for x in range(22, w - 22, 9):
            rect(image, x, ridge - 7, 4, 14, tone(roof, -35))
            rect(image, x + 4, ridge - 7, 2, 14, tone(plaster, -15))
        rect(image, 17, ridge + 11, w - 34, 4, trim)
        rect(image, 9, eaves - 8, w - 18, 4, tone(roof, 14))
    elif form == "parapet":
        rect(image, 5, 5, w - 10, 7, tone(plaster, 5))
        rect(image, 5, 5, 7, eaves - 5, tone(plaster, -23))
        rect(image, w - 12, 5, 7, eaves - 5, tone(plaster, -31))
        for x in range(5, w - 10, 24):
            rect(image, x, 1, 12, 10, tone(plaster, 12))
        for x in range(5, w - 10, 24):
            rect(image, x, eaves - 8, 12, 12, plaster)
        rect(image, 5, eaves, w - 10, 5, tone(plaster, -25))
    else:
        rect(image, 15, ridge - 3, w - 30, 4, tone(roof, 24))
        rect(image, 15, ridge + 1, w - 30, 2, tone(roof, -25))
        if form in {"hip", "longhouse", "mansard"}:
            line(image, 16, ridge + 2, 5, eaves - 5, tone(roof, -25), 2)
            line(image, w - 17, ridge + 2, w - 7, eaves - 5, tone(roof, -25), 2)
        if form == "mansard":
            rect(image, 24, eaves - 30, w - 48, 3, tone(roof, 23))
            for x in (w // 3, 2 * w // 3):
                window(image, x - 7, eaves - 23, 14, 13, trim)
    # No fake entrance rendered into a roof, including north/side doors.
    ex, ey = entrance
    image[max(0, ey * 32) : min(h, (ey + 1) * 32), max(0, ex * 32) : min(w, (ex + 1) * 32), 3] = 0
    return image
