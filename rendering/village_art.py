"""Footprint-aware architectural silhouettes and connected street surfaces.

All geometry stays on the simulation grid. Roofs depict exterior mass only;
they never mark hidden floors explored or reveal residents or stock.
"""

from functools import lru_cache
from pathlib import Path
from runtime_compat import np
from rendering import pixel_scene as pixels, terrain_art

# roof, plaster, trim, sign motif
STYLES = {
    "bakery": ((157, 77, 49), (213, 187, 135), (80, 48, 35), "bread"),
    "tavern": ((73, 103, 104), (188, 165, 121), (70, 44, 38), "mug"),
    "blacksmith_shop": ((65, 75, 86), (130, 133, 126), (47, 43, 43), "anvil"),
    "lumber_mill": ((111, 116, 83), (163, 124, 75), (60, 47, 32), "timber"),
    "mill": ((104, 112, 98), (187, 174, 140), (76, 60, 40), "grain"),
    "house": ((158, 134, 73), (191, 171, 132), (77, 56, 36), None),
    "common_house": ((137, 120, 75), (172, 158, 124), (66, 54, 37), None),
    "general_store": ((111, 99, 119), (185, 172, 142), (67, 49, 45), "crate"),
    "clinic": ((95, 119, 107), (210, 205, 165), (74, 69, 48), "cross"),
    "library": ((109, 94, 116), (198, 181, 146), (74, 52, 48), "book"),
    "capital_hall": ((85, 101, 114), (192, 190, 164), (68, 67, 57), "civic"),
    "city_hall": ((85, 101, 114), (192, 190, 164), (68, 67, 57), "civic"),
    "sheriff_office": ((89, 95, 92), (163, 164, 146), (61, 61, 50), "badge"),
    "guard_post": ((89, 95, 92), (163, 164, 146), (61, 61, 50), "badge"),
    "jail": ((75, 81, 82), (141, 148, 141), (48, 54, 50), "bars"),
    "barracks": ((78, 86, 97), (152, 155, 139), (50, 53, 49), "badge"),
    "large_house": ((121, 100, 83), (205, 185, 148), (68, 49, 37), None),
    "shack": ((132, 113, 67), (141, 118, 81), (60, 47, 33), None),
    "carpenter_shop": ((119, 111, 76), (170, 140, 95), (67, 49, 32), "timber"),
    "lumber_shed": ((99, 99, 70), (157, 119, 73), (57, 44, 31), "timber"),
    "storage_building": ((108, 109, 96), (165, 143, 99), (64, 52, 38), "crate"),
    "butcher_shop": ((127, 83, 70), (192, 172, 139), (72, 48, 38), "cleaver"),
    "hunting_lodge": ((124, 120, 78), (149, 118, 80), (56, 46, 33), "antler"),
}
DEFAULT = ((103, 112, 116), (171, 164, 141), (67, 62, 50), None)
_trees = ()


def install():
    global _trees
    path = Path(__file__).resolve().parents[1] / "assets/world32/trees-atlas-v1.png"
    if path.exists():
        _trees = pixels.source_sheet(path, 2, 2, 64, 80)


def style(building):
    return STYLES.get(building.building_type, DEFAULT)


def rect(image, x, y, w, h, color):
    image[max(0, y) : min(image.shape[0], y + h), max(0, x) : min(image.shape[1], x + w)] = (
        *color,
        255,
    )


def tone(color, delta):
    return tuple(max(0, min(255, c + delta)) for c in color)


@lru_cache(maxsize=512)
def wall_surface_v1(kind, side, window, door):
    _, plaster, trim, _ = STYLES.get(kind, DEFAULT)
    image = np.zeros((32, 32, 4), dtype=np.uint8)
    rect(image, 0, 0, 32, 32, tone(trim, -16))
    rect(image, 1, 3, 30, 25, plaster)
    rect(image, 1, 3, 30, 2, tone(plaster, 20))
    rect(image, 0, 0, 32, 3, trim)
    rect(image, 0, 26, 32, 6, tone(trim, -8))
    rect(image, 1, 26, 30, 2, tone(trim, 14))
    rect(image, 0, 2, 3, 24, trim)
    rect(image, 29, 2, 3, 24, trim)
    if kind == "lumber_mill":
        for xx in range(5, 29, 5):
            rect(image, xx, 4, 1, 22, tone(plaster, -23))
    if window:
        rect(image, 8, 7, 17, 17, trim)
        rect(image, 10, 9, 13, 12, (44, 62, 65))
        rect(image, 11, 10, 5, 4, (106, 138, 137))
        rect(image, 16, 9, 2, 13, trim)
        rect(image, 10, 15, 13, 2, trim)
        rect(image, 6, 23, 21, 3, tone(trim, 20))
        rect(image, 5, 8, 3, 14, tone(trim, 30))
        rect(image, 25, 8, 3, 14, tone(trim, 30))
    if side == "vertical" and not door:
        rect(image, 0, 0, 4, 32, tone(trim, -10))
        rect(image, 28, 0, 4, 32, tone(trim, -10))
    if door:
        rect(image, 6, 3, 21, 27, tone(trim, -20))
        if door == "closed":
            rect(image, 9, 5, 15, 24, (109, 75, 43))
            for xx in (12, 17, 22):
                rect(image, xx, 6, 1, 22, (72, 48, 31))
            rect(image, 10, 10, 13, 2, (52, 47, 38))
            rect(image, 10, 24, 13, 2, (52, 47, 38))
            rect(image, 20, 17, 2, 2, (222, 179, 86))
        rect(image, 4, 29, 25, 3, (142, 134, 113))
    return image


@lru_cache(maxsize=512)
def wall_surface(kind, side, window, door, interior=False):
    from rendering.architecture_art import detail_wall

    return detail_wall(
        wall_surface_v1(kind, side, window, door).copy(), kind, side, window, door, interior
    )


def draw_wall(console, world, camera_x, camera_y, x, y, key):
    if (
        not key
        or not pixels.enabled(world)
        or not ("wall" in key or key in {"door", "open_door", "closed_door"})
    ):
        return False
    building = getattr(world, "get_building_at", lambda *_: None)(x, y)
    if building is None:
        return False
    rx, ry = x - building.global_origin_x, y - building.global_origin_y
    outer = rx in (0, building.width - 1) or ry in (0, building.height - 1)
    if not outer:
        return False
    from rendering.console_renderer import _get_zoom_factor, is_visible

    zoom = int(_get_zoom_factor(world))
    side = "horizontal" if ry in (0, building.height - 1) else "vertical"
    door = ("open" if key == "open_door" else "closed") if "door" in key else None
    window = not door and (rx if side == "horizontal" else ry) % 3 == 1
    player = getattr(world, "player", None)
    interior = player is not None and building.contains_global_coords(player.x, player.y)
    image = wall_surface(building.building_type, side, window, door, interior)
    token = ("wall32", building.building_type, side, window, door, zoom, interior)
    scaled = pixels.scaled(image, zoom * 16, zoom * 16, token=token)
    tint = (255, 255, 255) if is_visible(world, x, y) else (100, 109, 104)
    return pixels.stamp(
        console,
        scaled,
        (x - camera_x) * zoom * 16,
        (y - camera_y) * zoom * 16,
        token=token,
        tint=tint,
    )


@lru_cache(maxsize=128)
def road_surface(mask, variant):
    image = pixels.resize(terrain_art._surface("plains", variant), 32, 32)
    # The shoulder bends to the real road adjacency instead of ending as a
    # hard rectangular texture at every tile boundary.
    ground = (116, 101, 75)
    rect(image, 3, 3, 26, 26, ground)
    for bit, box in [
        (1, (3, 0, 26, 6)),
        (2, (26, 3, 6, 26)),
        (4, (3, 26, 26, 6)),
        (8, (0, 3, 6, 26)),
    ]:
        if mask & bit:
            rect(image, *box, ground)
    for yy in range(2, 32, 6):
        for xx in range((yy // 6 % 2) * 5, 32, 10):
            if tuple(image[min(31, yy + 1), min(31, xx + 1), :3]) == ground:
                rect(image, xx + 1, yy, 5, 1, tone(ground, 11))
                rect(image, xx + 2, yy + 1, 5, 2, tone(ground, 4))
    return image


def draw_road(console, world, camera_x, camera_y, x, y, key):
    if key != "road" or not pixels.enabled(world):
        return False
    from rendering.console_renderer import _get_tile_key, _get_zoom_factor, is_visible

    mask = 0
    for bit, dx, dy in [(1, 0, -1), (2, 1, 0), (4, 0, 1), (8, -1, 0)]:
        other = world.get_tile_at(x + dx, y + dy)
        if other and (
            _get_tile_key(other) in {"road", "door", "open_door"}
            or getattr(other, "properties", {}).get("is_door")
        ):
            mask |= bit
    zoom = int(_get_zoom_factor(world))
    token = ("road32", mask, (x + y) % 4, zoom)
    image = pixels.scaled(road_surface(mask, (x + y) % 4), zoom * 16, zoom * 16, token=token)
    tint = (255, 255, 255) if is_visible(world, x, y) else (104, 115, 110)
    return pixels.stamp(
        console,
        image,
        (x - camera_x) * zoom * 16,
        (y - camera_y) * zoom * 16,
        token=token,
        tint=tint,
    )


@lru_cache(maxsize=8)
def understory_surface(kind, variant):
    """Low-contrast grass/flowers retain the real tile without visual shouting."""
    image = np.zeros((32, 32, 4), dtype=np.uint8)
    for index, (x, y) in enumerate(((8, 24), (14, 26), (22, 20))):
        x += (variant + index) % 3
        color = (78, 105, 56) if index % 2 else (103, 124, 65)
        for step in range(7):
            rect(image, x - step // 3, y - step, 1, 2, color)
            rect(image, x + 2 + step // 3, y - step, 1, 2, tone(color, -12))
        if kind == "flower":
            rect(image, x - 2, y - 7, 5, 2, (195, 170, 115))
            rect(image, x, y - 9, 2, 6, (204, 189, 142))
            rect(image, x, y - 7, 2, 2, (168, 111, 66))
    return image


def draw_understory(console, world, camera_x, camera_y, x, y, key):
    if key not in {"tall_grass", "flower"} or not pixels.enabled(world):
        return False
    from rendering.console_renderer import _get_zoom_factor, is_visible

    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    token = ("understory32", key, (x + y) % 4, zoom)
    image = pixels.scaled(understory_surface(key, (x + y) % 4), unit, unit, token=token)
    tint = (255, 255, 255) if is_visible(world, x, y) else (104, 115, 110)
    return pixels.stamp(
        console, image, (x - camera_x) * unit, (y - camera_y) * unit, token=token, tint=tint
    )


def roof_mode(world, building):
    """Exterior, cutaway or unseen. Never mutates visibility/exploration."""
    fov = getattr(world, "player_fov_map", None)
    if fov is None:
        return "cutaway"
    x, y, w, h = building.global_origin_x, building.global_origin_y, building.width, building.height
    region = fov[max(0, y) : y + h, max(0, x) : x + w]
    if not region.any():
        return "unseen"
    if building.contains_global_coords(world.player.x, world.player.y):
        return "cutaway"
    if region.shape[0] > 2 and region.shape[1] > 2 and region[1:-1, 1:-1].any():
        return "cutaway"
    return "exterior"


@lru_cache(maxsize=128)
def roof_surface_v1(kind, width, height, entrance):
    roof, plaster, trim, motif = STYLES.get(kind, DEFAULT)
    w, h = width * 32, height * 32
    image = np.zeros((h, w, 4), dtype=np.uint8)
    # Hipped silhouette, deep eaves and a distinct ridge. Every row is bounded
    # by the real footprint; no sprite stretches a house into another plot.
    ridge = max(20, (h - 32) // 3)
    eaves = h - 34
    for yy in range(5, eaves):
        inset = max(3, 20 - yy, yy - (eaves - 16))
        color = tone(roof, -17 if yy < ridge else 0)
        rect(image, inset, yy, w - inset * 2, 1, color)
        if (yy - ridge) % 7 == 0:
            rect(image, inset, yy, w - inset * 2, 1, tone(color, -22))
            rect(image, inset, yy + 1, w - inset * 2, 1, tone(color, 13))
        for xx in range(inset + ((yy // 7) % 2) * 7, w - inset, 14):
            if yy % 7 in (2, 3, 4):
                rect(image, xx, yy, 1, 1, tone(color, -14))
    if kind in {"house", "common_house"}:
        # Straw is laid down the slope; homes read differently from tiled shops.
        for xx in range(9, w - 9, 4):
            for yy in range(8, eaves - 5, 13):
                rect(image, xx, yy, 1, 9, tone(roof, 12 if xx % 3 else -18))
    # A full tile of front wall gives each roof a grounded building silhouette:
    # timber posts, shutters, windows and a foundation at the same world scale.
    for column in range(width):
        image[h - 32 : h, column * 32 : (column + 1) * 32] = wall_surface_v1(
            kind, "horizontal", column % 3 == 1, None
        )
    rect(image, 0, h - 32, 5, 32, tone(trim, -18))
    rect(image, w - 5, h - 32, 5, 32, tone(trim, -18))
    rect(image, 3, eaves, w - 6, 4, tone(trim, -13))
    rect(image, 4, eaves + 4, w - 8, 3, tone(plaster, -40))
    rect(image, 6, ridge - 3, w - 12, 3, tone(roof, 30))
    rect(image, 6, ridge, w - 12, 2, tone(roof, -28))
    if kind == "tavern":
        # Cross-gable breaks the inn's broad roof mass.
        cx = w // 2
        for yy in range(ridge + 5, eaves):
            half = min(35, (yy - ridge) // 2 + 2)
            rect(image, cx - half, yy, half * 2, 1, tone(roof, 22))
            rect(image, cx - half, yy, 2, 1, tone(trim, -12))
            rect(image, cx + half - 2, yy, 2, 1, tone(trim, -12))
        # Broad timber-framed dormer and twin inn windows.
        for yy in range(eaves - 32, eaves):
            half = min(35, (yy - (eaves - 32)) + 3)
            rect(image, cx - half, yy, half * 2, 1, plaster)
            rect(image, cx - half, yy, 2, 1, trim)
            rect(image, cx + half - 2, yy, 2, 1, trim)
        for xx in (cx - 18, cx + 7):
            rect(image, xx, eaves - 15, 12, 12, trim)
            rect(image, xx + 2, eaves - 13, 8, 8, (74, 107, 113))
        rect(image, cx - 36, eaves, 72, 5, trim)
    if kind == "blacksmith_shop":
        # Low industrial shed roof: one broad slope and a heavy lower beam.
        rect(image, 7, ridge - 3, w - 14, 5, tone(roof, -3))
        rect(image, 5, eaves - 5, w - 10, 6, (65, 49, 38))
    if kind == "bakery":
        # Cream-striped shop awning sits above the street-facing windows.
        for xx in range(34, w - 34, 8):
            rect(image, xx, eaves + 3, 8, 7, (218, 186, 128) if xx % 16 else (132, 62, 42))
    # Keep the actual entrance legible on whichever wall it was generated.
    ex, ey = entrance
    dx, dy = ex * 32, ey * 32
    image[max(0, dy) : min(h, dy + 32), max(0, dx) : min(w, dx + 32), 3] = 0
    return image


def roof_surface(kind, width, height, entrance, variant=None):
    from rendering.architecture_art import roof_surface as render_roof

    return render_roof(kind, width, height, entrance, variant)


def thermal_station(building):
    for role, coords in getattr(building, "work_zone_tiles", {}).items():
        if any(word in role.lower() for word in ("oven", "forge", "furnace")) and coords:
            return tuple(coords[0])
    return None


def station_is_working(world, building, station):
    from rendering.people_art import activity_for

    for actor in getattr(world, "village_npcs", []):
        if abs(actor.x - station[0]) + abs(actor.y - station[1]) <= 1:
            if activity_for(world, actor).kind in {"prepare", "hammer"}:
                return True
    return False


@lru_cache(maxsize=8)
def chimney_surface(kind):
    image = np.zeros((42, 28, 4), dtype=np.uint8)
    color = (128, 89, 67) if kind != "blacksmith_shop" else (90, 96, 102)
    rect(image, 5, 9, 18, 31, (54, 47, 39))
    rect(image, 5, 9, 12, 28, color)
    for yy in range(12, 37, 6):
        rect(image, 5, yy, 12, 1, tuple(c - 24 for c in color))
    rect(image, 2, 5, 24, 7, (168, 152, 124))
    rect(image, 5, 5, 18, 4, (35, 36, 31))
    rect(image, 3, 11, 21, 2, (98, 88, 70))
    return image


@lru_cache(maxsize=24)
def sign_surface(motif):
    image = np.zeros((24, 32, 4), dtype=np.uint8)
    rect(image, 0, 0, 3, 24, (63, 49, 34))
    rect(image, 0, 0, 31, 3, (89, 67, 41))
    rect(image, 10, 3, 2, 4, (49, 48, 38))
    rect(image, 26, 3, 2, 4, (49, 48, 38))
    rect(image, 7, 6, 24, 17, (61, 43, 29))
    rect(image, 8, 7, 22, 14, (147, 104, 53))
    gold = (236, 207, 133)
    if motif == "bread":
        rect(image, 12, 12, 15, 6, gold)
        rect(image, 14, 10, 11, 2, gold)
        for xx in (16, 20, 24):
            rect(image, xx, 11, 1, 4, (153, 103, 49))
    elif motif == "mug":
        rect(image, 13, 10, 10, 10, gold)
        rect(image, 23, 12, 5, 6, gold)
        rect(image, 24, 13, 2, 3, (147, 104, 53))
        rect(image, 12, 9, 12, 3, (244, 233, 193))
    elif motif == "anvil":
        rect(image, 11, 11, 17, 4, gold)
        rect(image, 16, 15, 6, 4, gold)
        rect(image, 13, 19, 13, 2, gold)
    elif motif == "cross":
        rect(image, 17, 9, 5, 12, gold)
        rect(image, 13, 13, 13, 4, gold)
    elif motif == "book":
        rect(image, 12, 10, 15, 10, gold)
        rect(image, 19, 10, 1, 10, (90, 59, 32))
    elif motif == "crate":
        rect(image, 12, 10, 15, 11, gold)
        rect(image, 14, 12, 11, 7, (147, 104, 53))
        for d in range(9):
            rect(image, 14 + d, 12 + d // 2, 2, 1, gold)
    elif motif == "timber":
        rect(image, 11, 16, 17, 4, gold)
        rect(image, 12, 10, 4, 4, gold)
        rect(image, 15, 11, 12, 2, gold)
        for x in range(16, 27, 3):
            rect(image, x, 13, 1, 2, gold)
    elif motif == "grain":
        for x in (15, 20, 25):
            rect(image, x, 11, 1, 10, gold)
            rect(image, x - 2, 11, 2, 2, gold)
            rect(image, x + 1, 9, 2, 2, gold)
        rect(image, 13, 17, 14, 1, (230, 182, 83))
    elif motif in {"badge", "civic"}:
        if motif == "badge":
            rect(image, 15, 10, 11, 8, gold)
            rect(image, 17, 18, 7, 2, gold)
            rect(image, 19, 20, 3, 1, gold)
            rect(image, 19, 12, 3, 5, (147, 104, 53))
        else:
            rect(image, 12, 11, 16, 2, gold)
            for x in (13, 19, 25):
                rect(image, x, 13, 2, 6, gold)
            rect(image, 11, 19, 18, 2, gold)
    elif motif == "bars":
        rect(image, 12, 9, 16, 2, gold)
        rect(image, 12, 19, 16, 2, gold)
        for x in (13, 19, 25):
            rect(image, x, 10, 2, 10, gold)
    elif motif == "cleaver":
        rect(image, 12, 10, 11, 8, gold)
        rect(image, 23, 12, 5, 3, (219, 179, 108))
        rect(image, 13, 11, 2, 2, (147, 104, 53))
    elif motif == "antler":
        for d in range(6):
            rect(image, 19 - d, 19 - d, 2, 2, gold)
            rect(image, 19 + d, 19 - d, 2, 2, gold)
        for x in (14, 18, 23):
            rect(image, x, 10, 1, 5, gold)
    else:
        for yy in (10, 14, 18):
            rect(image, 12, yy, 15, 3, gold)
    return image


def draw_buildings(console, world, camera_x, camera_y):
    if not pixels.enabled(world):
        return
    from rendering.console_renderer import _get_zoom_factor, is_visible

    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    tint = pixels.world_tint(world)
    for building in getattr(world, "buildings_by_id", {}).values():
        if building.building_type in {"farm", "mine"}:
            continue
        bx, by = building.global_origin_x, building.global_origin_y
        if (
            bx + building.width < camera_x
            or by + building.height < camera_y
            or bx > camera_x + 78 / zoom
            or by > camera_y + 50 / zoom
        ):
            continue
        mode = roof_mode(world, building)
        if mode == "unseen":
            continue
        entrance = building.interaction_points.get(
            "entrance", (bx + building.width // 2, by + building.height - 1)
        )
        local = (entrance[0] - bx, entrance[1] - by)
        # Seeing through an open doorway cuts only that sightline out of the
        # roof. Keep the rest of the building's exterior mass readable instead
        # of turning unseen rooms into a building-shaped black void. Once the
        # player enters, the whole roof disappears for interior play.
        partial = mode == "cutaway" and not building.contains_global_coords(
            world.player.x, world.player.y
        )
        roof_clip = None
        if partial:
            roof_clip = lambda x, y: not is_visible(
                world, camera_x + x // zoom, camera_y + y // zoom
            )
        if mode == "exterior" or partial:
            key = (
                building.building_type,
                building.width,
                building.height,
                local,
                getattr(building, "variant_id", None),
            )
            source = roof_surface(*key)
            image = pixels.scaled(
                source, building.width * unit, building.height * unit, token=("roof", key, zoom)
            )
            pixels.stamp(
                console,
                image,
                (bx - camera_x) * unit,
                (by - camera_y) * unit,
                token=("roof", key, zoom),
                tint=tint,
                clip=roof_clip,
            )
            station = thermal_station(building)
            if station and not (partial and is_visible(world, *station)):
                chimney = pixels.scaled(
                    chimney_surface(building.building_type),
                    unit * 7 // 8,
                    unit * 21 // 16,
                    token=("chimney32", building.building_type, zoom),
                )
                cx = (station[0] - camera_x) * unit
                cy = (station[1] - camera_y) * unit - unit // 2
                pixels.stamp(
                    console,
                    chimney,
                    cx,
                    cy,
                    token=("chimney32", building.building_type, zoom),
                    tint=tint,
                )
                if station_is_working(world, building, station):
                    phase = int(getattr(world, "game_time", 0) // 2) % 4
                    smoke = np.zeros((unit, unit, 4), dtype=np.uint8)
                    for i in range(3):
                        sx, sy = unit // 3 + (i + phase) % 4, unit - 8 - i * unit // 4
                        smoke[max(0, sy - 5) : sy + 2, sx : sx + 7] = (189, 189, 170, 135 - i * 30)
                    pixels.stamp(console, smoke, cx, cy - unit + 4, token=("smoke32", phase, zoom))
        from rendering import building_frontage

        building_frontage.draw(console, world, building, camera_x, camera_y)


def draw_trees(console, world, camera_x, camera_y):
    if not _trees or not pixels.enabled(world):
        return
    from rendering.console_renderer import _get_zoom_factor, _get_world_view_dimensions, is_visible

    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    vw, vh = _get_world_view_dimensions(world)
    for y in range(camera_y, camera_y + vh):
        for x in range(camera_x, camera_x + vw):
            if not is_visible(world, x, y):
                continue
            tile = world.get_tile_at(x, y)
            key = getattr(tile, "tree_type", None)
            if not key and getattr(tile, "name", None) == "Forest":
                key = "forest"
            if key not in {"forest", "oak", "pine", "birch", "apple", "pear"}:
                continue
            # Fruit is drawn only on the matching fruit-tree species.
            index = {"pine": 1, "apple": 2, "birch": 3}.get(key, 0)
            image = pixels.scaled(
                _trees[index], unit * 2, unit * 5 // 2, token=("tree32", index, zoom)
            )
            tint = pixels.world_tint(world, (x - camera_x) * zoom, (y - camera_y) * zoom)
            pixels.stamp(
                console,
                image,
                (x - camera_x) * unit - unit // 2,
                (y - camera_y + 1) * unit - image.shape[0],
                token=("tree32", index, zoom),
                tint=tint,
            )
