"""Soft street shoulders and door wear on existing visible outdoor ground.

No new paths, fences, lots or collision objects are placed. Shared spacing
between buildings is not depicted as an exclusive private garden.
"""

from functools import lru_cache
from runtime_compat import np
from rendering import pixel_scene as pixels

DIRECTIONS = ((1, 0, -1), (2, 1, 0), (4, 0, 1), (8, -1, 0))
ELIGIBLE = {"plains", "tall_grass", "flower"}


@lru_cache(maxsize=256)
def edge_surface(roads, walls, doors, water, variant):
    image = np.zeros((32, 32, 4), dtype=np.uint8)
    yy, xx = np.indices((32, 32))
    for bit, dx, dy in DIRECTIONS:
        distance = yy if dy == -1 else 31 - yy if dy == 1 else xx if dx == -1 else 31 - xx
        across = xx if dy else yy
        grain = (xx * 17 + yy * 11 + variant * 7) % 5
        if roads & bit:
            mask = (distance < 4 + (across // 5 + variant) % 3) & (across > 1) & (across < 30)
            image[mask] = (116, 101, 75, 130)
            image[mask & (distance < 2)] = (116, 101, 75, 190)
        if walls & bit:
            mask = distance < 2 + (across // 7) % 2
            image[mask] = (44, 49, 34, 95)
        if water & bit:
            mask = distance < 3 + (across // 4 + variant) % 3
            image[mask] = (63, 74, 58, 170)
            image[mask & (distance < 2)] = (129, 125, 89, 160)
        if doors & bit:
            # Taper one tile out from the actual doorway; no road is invented.
            mask = (distance < 27) & (abs(across - 16) < 13 - distance // 3) & (grain > 0)
            image[mask] = (111, 96, 69, 150)
            image[mask & (distance < 5)] = (131, 118, 88, 210)
    return image


def draw(console, world, camera_x, camera_y, x, y, key):
    if not pixels.enabled(world) or key not in ELIGIBLE:
        return False
    from rendering.console_renderer import _get_tile_key, _get_zoom_factor, is_visible

    if not is_visible(world, x, y):
        return False
    get_building = getattr(world, "get_building_at", lambda *_: None)
    if get_building(x, y) is not None:
        return False
    roads = walls = doors = water = 0
    for bit, dx, dy in DIRECTIONS:
        nx, ny = x + dx, y + dy
        if not is_visible(world, nx, ny):
            continue
        tile = world.get_tile_at(nx, ny)
        other = _get_tile_key(tile)
        if other == "road":
            roads |= bit
        if other in {"water", "deep_water"}:
            water |= bit
        building = get_building(nx, ny)
        if building is not None:
            if "wall" in (other or ""):
                walls |= bit
            if getattr(building, "interaction_points", {}).get("entrance") == (nx, ny) and (
                getattr(tile, "properties", {}).get("is_door") or "door" in (other or "")
            ):
                doors |= bit
    if not (roads or walls or doors or water):
        return False
    zoom = int(_get_zoom_factor(world))
    unit = zoom * 16
    variant = (x * 3 + y * 7) % 4
    token = ("street-edge", roads, walls, doors, water, variant, zoom)
    image = pixels.scaled(
        edge_surface(roads, walls, doors, water, variant), unit, unit, token=token
    )
    return pixels.stamp(console, image, (x - camera_x) * unit, (y - camera_y) * unit, token=token)
