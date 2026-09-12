"""Trade and player-property signs mounted on real entrance walls."""

from functools import lru_cache
from config import MAP_WIDTH, MAP_HEIGHT
from runtime_compat import np
from rendering import pixel_scene as pixels
from rendering.village_art import rect, tone, style, sign_surface, STYLES, DEFAULT


def entrance_side(building):
    entrance = getattr(building, "interaction_points", {}).get("entrance")
    if entrance is None:
        return None
    x, y = entrance
    bx, by = building.global_origin_x, building.global_origin_y
    if not building.contains_global_coords(x, y):
        return None
    if y == by:
        return "north"
    if y == by + building.height - 1:
        return "south"
    if x == bx:
        return "west"
    if x == bx + building.width - 1:
        return "east"
    return None


def sign_mount(building):
    side = entrance_side(building)
    if side is None:
        return None
    x, y = building.interaction_points["entrance"]
    if side in {"north", "south"}:
        x += 1 if x + 1 < building.global_origin_x + building.width - 1 else -1
    else:
        y += 1 if y + 1 < building.global_origin_y + building.height - 1 else -1
    if building.contains_global_coords(x, y):
        return x, y
    return None


def is_players_property(world, building):
    player_id = getattr(getattr(world, "player", None), "id", None)
    return bool(
        getattr(building, "player_owned", False)
        or (player_id is not None and getattr(building, "owner_id", None) == player_id)
    )


def visible_entrance(world, building):
    from rendering.console_renderer import _get_tile_key, is_visible

    entrance = getattr(building, "interaction_points", {}).get("entrance")
    player = getattr(world, "player", None)
    if player is not None and building.contains_global_coords(player.x, player.y):
        return False  # Exterior-mounted art is not painted on the room-facing wall.
    if entrance_side(building) is None or not is_visible(world, *entrance):
        return False
    get_tile = getattr(world, "get_tile_at", None)
    if get_tile is None:
        return True
    tile = get_tile(*entrance)
    return bool(
        getattr(tile, "properties", {}).get("is_door") or "door" in (_get_tile_key(tile) or "")
    )


@lru_cache(maxsize=1)
def property_plaque():
    image = np.zeros((24, 32, 4), dtype=np.uint8)
    rect(image, 4, 4, 24, 17, (51, 61, 51))
    rect(image, 5, 5, 22, 15, (172, 141, 81))
    rect(image, 7, 7, 18, 11, (59, 76, 63))
    gold = (235, 209, 143)
    rect(image, 10, 9, 6, 6, gold)
    rect(image, 12, 11, 2, 2, (59, 76, 63))
    rect(image, 15, 11, 9, 2, gold)
    rect(image, 20, 12, 2, 4, gold)
    return image


@lru_cache(maxsize=6)
def canopy_surface(kind):
    roof, plaster, trim, _ = STYLES.get(kind, DEFAULT)
    image = np.zeros((20, 96, 4), dtype=np.uint8)
    for x in range(3, 93):
        stripe = plaster if (x // 9) % 2 == 0 else roof
        for y in range(3, 14):
            rect(image, x, y, 1, 1, tone(stripe, 9 - y))
        rect(image, x, 14, 1, 2 + (x // 9) % 2, tone(stripe, -23))
    rect(image, 2, 1, 92, 3, trim)
    rect(image, 1, 1, 3, 18, trim)
    rect(image, 92, 1, 3, 18, trim)
    return image


def sign_geometry(world, building, camera_x, camera_y):
    from rendering.console_renderer import _get_zoom_factor, is_visible

    if not pixels.enabled(world):
        return None
    mount = sign_mount(building)
    if mount is None:
        return None
    entrance = building.interaction_points["entrance"]
    if not visible_entrance(world, building) or not is_visible(world, *mount):
        return None
    # A missing/demolished entrance wall must not retain a floating sign.
    get_tile = getattr(world, "get_tile_at", None)
    if get_tile is not None:
        from rendering.console_renderer import _get_tile_key

        tile = get_tile(*mount)
        if "wall" not in (_get_tile_key(tile) or ""):
            return None
    owned = is_players_property(world, building)
    motif = style(building)[3]
    if not owned and not motif:
        return None
    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    source = property_plaque() if owned and motif is None else sign_surface(motif)
    token = ("frontage-sign", motif, owned and motif is None, zoom)
    image = pixels.scaled(source, unit, unit * 3 // 4, token=token)
    return image, (mount[0] - camera_x) * unit, (mount[1] - camera_y) * unit, token


def draw(console, world, building, camera_x, camera_y):
    from rendering.console_renderer import _get_zoom_factor, is_visible

    if not pixels.enabled(world):
        return
    entrance = getattr(building, "interaction_points", {}).get("entrance")
    if not visible_entrance(world, building):
        return
    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    clip = lambda x, y: is_visible(world, camera_x + x // zoom, camera_y + y // zoom)
    tint = pixels.world_tint(
        world, (entrance[0] - camera_x) * zoom, (entrance[1] - camera_y) * zoom
    )
    kind = building.building_type
    if (
        kind in {"bakery", "general_store", "butcher_shop"}
        and entrance_side(building) in {"north", "south"}
        and building.width >= 3
    ):
        start = max(
            building.global_origin_x,
            min(entrance[0] - 1, building.global_origin_x + building.width - 3),
        )
        image = pixels.scaled(
            canopy_surface(kind), unit * 3, unit * 5 // 8, token=("shop-canopy", kind, zoom)
        )

        # Canvas over the street-facing facade, not over visible interior tiles.
        def exterior_clip(cx, cy):
            wx, wy = camera_x + cx // zoom, camera_y + cy // zoom
            inside = (
                building.global_origin_x < wx < building.global_origin_x + building.width - 1
                and building.global_origin_y < wy < building.global_origin_y + building.height - 1
            )
            return not inside and clip(cx, cy)

        pixels.stamp(
            console,
            image,
            (start - camera_x) * unit,
            (entrance[1] - camera_y) * unit - unit // 4,
            token=("shop-canopy", kind, zoom),
            tint=tint,
            clip=exterior_clip,
        )
    geometry = sign_geometry(world, building, camera_x, camera_y)
    if geometry is not None:
        image, px, py, token = geometry
        pixels.stamp(console, image, px, py, token=token, tint=tint, clip=clip)


def hit_test(world, camera_x, camera_y, screen_x, screen_y):
    """Inspect a trade sign at its entrance; never changes movement targeting."""
    if not pixels.enabled(world) or not (0 <= screen_x < MAP_WIDTH and 3 <= screen_y < MAP_HEIGHT):
        return None
    for building in getattr(world, "buildings_by_id", {}).values():
        geometry = sign_geometry(world, building, camera_x, camera_y)
        if geometry is None:
            continue
        image, px, py, _ = geometry
        x, y = int(screen_x * 16 - px), int(screen_y * 16 - py)
        if x + 16 <= 0 or y + 16 <= 0 or x >= image.shape[1] or y >= image.shape[0]:
            continue
        if (image[max(0, y) : y + 16, max(0, x) : x + 16, 3] > 32).any():
            return tuple(building.interaction_points["entrance"])
    return None
