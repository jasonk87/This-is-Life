"""One painter order for furniture, loose items and people; shared by picking."""

from dataclasses import dataclass

from config import MAP_HEIGHT, MAP_WIDTH
from rendering import furniture_occupancy as occupancy, interior_art, pixel_scene as pixels
from runtime_compat import np


@dataclass
class Entry:
    depth: tuple
    kind: str
    value: object


def entries(world, camera_x, camera_y, bounds=None):
    from rendering.console_renderer import _iter_render_entities, is_visible

    result = []
    for fixture in interior_art.visible_furniture(world, camera_x, camera_y, bounds):
        x, y, _, _ = fixture
        result.append(Entry((y, 0, x, 0, 0), "furniture", fixture))
    for (x, y), items in getattr(world, "items_on_map", {}).items():
        if items and is_visible(world, x, y):
            result.append(Entry((y, 1, x, 0, 0), "items", ((x, y), items)))
    seen = set()
    for i, actor in enumerate(_iter_render_entities(world)):
        if id(actor) in seen or not occupancy.present(world, actor):
            continue
        seen.add(id(actor))
        if not is_visible(world, actor.x, actor.y):
            continue
        x, y = occupancy.render_anchor(world, actor)
        order = getattr(getattr(actor, "render_order", None), "value", 0)
        result.append(Entry((y, 2, x, order, i), "actor", actor))
    return sorted(result, key=lambda entry: entry.depth)


def draw(console, world, camera_x, camera_y):
    from rendering.console_renderer import _draw_entities, _draw_items

    for entry in entries(world, camera_x, camera_y):
        if entry.kind == "furniture":
            interior_art.draw_object(console, world, camera_x, camera_y, entry.value)
        elif entry.kind == "items":
            _draw_items(console, world, camera_x, camera_y, piles=[entry.value])
        else:
            _draw_entities(console, world, camera_x, camera_y, entities=[entry.value])


def cell_alpha(image, px, py, screen_x, screen_y):
    """Alpha in exactly the hovered 16px cell; no rectangular ghost hitboxes."""
    result = np.zeros((16, 16), dtype=np.uint8)
    sx, sy = int(screen_x * 16 - px), int(screen_y * 16 - py)
    x0, y0 = max(0, sx), max(0, sy)
    x1, y1 = min(image.shape[1], sx + 16), min(image.shape[0], sy + 16)
    if x0 < x1 and y0 < y1:
        result[y0 - sy : y1 - sy, x0 - sx : x1 - sx] = image[y0:y1, x0:x1, 3]
    return result


def pick_person(world, camera_x, camera_y, screen_x, screen_y):
    from rendering import people_art as people
    from rendering.console_renderer import _get_zoom_factor, is_visible

    if not (0 <= screen_x < MAP_WIDTH and 3 <= screen_y < MAP_HEIGHT):
        return None
    zoom = int(_get_zoom_factor(world))
    wx, wy = camera_x + screen_x // zoom, camera_y + screen_y // zoom
    # Both the actor's actual origin and the visible pixels must be in FOV.
    if not is_visible(world, wx, wy):
        return None
    remaining = np.ones((16, 16), dtype=bool)
    nearby = entries(world, camera_x, camera_y, (wx - 1, wy - 1, wx + 2, wy + 2))
    for entry in reversed(nearby):
        if entry.kind == "furniture":
            x, y, key, _ = entry.value
            image, px, py = interior_art.placement(key, zoom, x, y, camera_x, camera_y)
            remaining &= cell_alpha(image, px, py, screen_x, screen_y) < 200
        elif entry.kind == "actor":
            actor = entry.value
            if not people.is_person(world, actor):
                continue
            image, _, _, px, py = people.placement(world, actor, zoom, camera_x, camera_y)
            attachment = occupancy.attachment_for(world, actor)
            if attachment:
                _, fx, fy = interior_art.placement(
                    attachment.key, zoom, attachment.x, attachment.y, camera_x, camera_y
                )
                cover = interior_art.foreground_pixels(attachment.key, zoom)
                remaining &= cell_alpha(cover, fx, fy, screen_x, screen_y) < 200
            if ((cell_alpha(image, px, py, screen_x, screen_y) > 32) & remaining).any():
                return actor
        if not remaining.any():
            break
    return None
