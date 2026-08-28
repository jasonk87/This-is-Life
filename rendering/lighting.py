"""Light sources and the per-cell light map for the world view.

The renderer used to have no concept of a light *source*. It dimmed every
visible cell by its distance from the player and washed the result with a
time-of-day tint, so a midnight street and a midnight room with a roaring
hearth looked identical - the hearth was just an orange glyph in the same
uniform gloom. Torch items have carried a `light_radius` in their data since
long before this module existed; nothing ever read it.

Here, anything that emits light contributes to a light map: the player's
torch, lit campfires, and light-emitting tiles and decorations in view.
Cells near a source are brighter *and* warmer, which is what makes a fire
read as a fire at night.

Everything is computed with whole-array numpy operations over the console's
map area. The previous implementation ran a Python double loop over ~3,900
cells every frame, calling `_screen_to_world` and `world.get_tile_at` for
each one; adding per-source math on top of that shape would have made the
frame cost several times worse rather than better.
"""

from __future__ import annotations

from typing import NamedTuple

from runtime_compat import np

from data.tiles import TILE_DEFINITIONS
from data.decorations import DECORATION_ITEM_DEFINITIONS
from data.items import ITEM_DEFINITIONS

# How much of full brightness the world sits at with no local light, keyed
# by world.current_light_level_name. DAY is 1.0: daylight needs no help, so
# the source pass can be skipped entirely.
AMBIENT_BY_LIGHT_LEVEL = {
    "DAY": 1.0,
    "DAWN": 0.62,
    "DUSK": 0.56,
    "NIGHT": 0.34,
    "PITCH BLACK": 0.22,
}
DEFAULT_AMBIENT = 1.0

# The player can always make out their immediate surroundings, torch or not.
PLAYER_EYES_RADIUS = 3

FIRELIGHT = (255, 172, 92)
TORCHLIGHT = (255, 198, 126)
NEUTRAL = (255, 255, 255)

# Cap on how far out of the camera view a source can be and still be
# collected. Sources beyond this can't reach any visible cell.
MAX_LIGHT_RADIUS = 16


class LightSource(NamedTuple):
    """A point of light in the world.

    `tints` separates "this brightens the area" from "this recolors it".
    Dark-adapted eyes let the player make out their immediate surroundings,
    but they don't cast a color - only flames do. Without the distinction,
    the player's own presence would wash the time-of-day tint out of every
    cell around them.
    """

    x: int
    y: int
    radius: float
    color: tuple
    intensity: float = 1.0
    tints: bool = True


def ambient_for_light_level(light_level_name):
    return AMBIENT_BY_LIGHT_LEVEL.get(light_level_name, DEFAULT_AMBIENT)


def _build_light_emitting_names():
    """Map display name -> light radius for every definition that emits light.

    Keyed by display name rather than definition key because that is what a
    placed tile actually carries at runtime; resolving a tile back to its
    definition key means a linear scan of the whole tile table per tile.
    """
    emitters = {}
    for table in (TILE_DEFINITIONS, DECORATION_ITEM_DEFINITIONS):
        for definition in table.values():
            radius = definition.get("properties", {}).get("light_radius")
            name = definition.get("name")
            if radius and name:
                emitters[name] = float(radius)
    return emitters


LIGHT_EMITTING_TILE_NAMES = _build_light_emitting_names()


def _flicker(game_time, seed, *, amount=0.12, speed=3.7):
    """A small deterministic wobble so flames don't sit perfectly still.

    Derived from the tick and the source's position, so every fire has its
    own phase without any per-source state to store or save.
    """
    phase = ((int(game_time) * speed) + (seed % 17)) % 360
    # Cheap triangle wave in place of a trig call per source per frame.
    wave = abs((phase / 180.0) - 1.0)
    return 1.0 - amount + (amount * 2.0 * wave)


def _personal_light_radius(entity):
    equipment = getattr(entity, "equipment", None)
    if equipment is None:
        return 0.0
    if not getattr(equipment, "equipped_light_item_key", None):
        return 0.0
    radius = getattr(equipment, "current_personal_light_radius", 0) or 0
    if radius:
        return float(radius)
    # Fall back to the item definition if the runtime radius wasn't set.
    definition = ITEM_DEFINITIONS.get(equipment.equipped_light_item_key, {})
    return float(definition.get("properties", {}).get("light_radius", 0) or 0)


def collect_light_sources(world, view_bounds):
    """Every light source that can reach the current view.

    `view_bounds` is (min_x, min_y, max_x, max_y) in world coordinates,
    already padded by MAX_LIGHT_RADIUS by the caller.
    """
    min_x, min_y, max_x, max_y = view_bounds
    game_time = getattr(world, "game_time", 0)
    sources = []

    def in_view(x, y):
        return min_x <= x <= max_x and min_y <= y <= max_y

    player = getattr(world, "player", None)
    if player is not None:
        torch_radius = _personal_light_radius(player)
        radius = max(PLAYER_EYES_RADIUS, torch_radius)
        sources.append(LightSource(
            x=int(getattr(player, "x", 0)),
            y=int(getattr(player, "y", 0)),
            radius=min(radius, MAX_LIGHT_RADIUS),
            color=TORCHLIGHT if torch_radius else NEUTRAL,
            intensity=1.0 if torch_radius else 0.55,
            tints=bool(torch_radius),
        ))

    for campfire in (getattr(world, "campfires_by_id", None) or {}).values():
        if not getattr(campfire, "lit", False):
            continue
        cx, cy = int(getattr(campfire, "x", 0)), int(getattr(campfire, "y", 0))
        if not in_view(cx, cy):
            continue
        radius = float(getattr(campfire, "warmth_radius", 4) or 4) + 2.0
        sources.append(LightSource(
            x=cx, y=cy,
            radius=min(radius, MAX_LIGHT_RADIUS),
            color=FIRELIGHT,
            intensity=_flicker(game_time, cx * 31 + cy),
        ))

    # NPCs carrying a lit torch light their own surroundings, which is what
    # makes a night watch visible as moving points of light.
    for npc in (getattr(world, "all_npcs", None) or []):
        if getattr(getattr(npc, "physical", None), "is_dead", False):
            continue
        radius = _personal_light_radius(npc)
        if not radius:
            continue
        nx, ny = int(getattr(npc, "x", 0)), int(getattr(npc, "y", 0))
        if not in_view(nx, ny):
            continue
        sources.append(LightSource(
            x=nx, y=ny,
            radius=min(radius, MAX_LIGHT_RADIUS),
            color=TORCHLIGHT,
            intensity=_flicker(game_time, nx * 17 + ny, amount=0.08),
        ))

    return sources


def collect_tile_light_sources(world, view_bounds, *, get_tile_at, limit=24):
    """Light-emitting tiles and decorations inside the view.

    Capped by `limit` because this walks the view rect: a hall lined with
    braziers should light the room, not cost a scan proportional to how
    many of them the player can see at once.
    """
    if not LIGHT_EMITTING_TILE_NAMES:
        return []

    min_x, min_y, max_x, max_y = view_bounds
    game_time = getattr(world, "game_time", 0)
    sources = []
    for world_y in range(min_y, max_y + 1):
        for world_x in range(min_x, max_x + 1):
            tile = get_tile_at(world_x, world_y)
            if tile is None:
                continue
            radius = LIGHT_EMITTING_TILE_NAMES.get(getattr(tile, "name", None))
            if not radius:
                continue
            sources.append(LightSource(
                x=world_x, y=world_y,
                radius=min(radius, MAX_LIGHT_RADIUS),
                color=FIRELIGHT,
                intensity=_flicker(game_time, world_x * 13 + world_y),
            ))
            if len(sources) >= limit:
                return sources
    return sources


def build_light_map(sources, map_x, map_y, ambient):
    """Per-cell light strength and warm-tint weight for the view.

    `map_x`/`map_y` are the world coordinate of every console column and
    row (shape (W,) and (H,)); the returned arrays are (H, W).

    Strength combines with ambient so a source can only ever brighten a
    cell, never darken one. Sources are combined with a maximum rather than
    a sum: two torches side by side should light a room like a bright
    torch, not like daylight.
    """
    height = len(map_y)
    width = len(map_x)
    strength = np.zeros((height, width), dtype=np.float32)
    warm = np.zeros((height, width), dtype=np.float32)
    tint = np.zeros((height, width, 3), dtype=np.float32)

    if not sources or ambient >= 1.0:
        return strength, warm, tint

    # Chebyshev distance, matching how the rest of the renderer measures
    # tile distance (a diagonal step costs the same as an orthogonal one).
    world_x = map_x[np.newaxis, :].astype(np.float32)
    world_y = map_y[:, np.newaxis].astype(np.float32)

    for source in sources:
        radius = max(1.0, float(source.radius))
        distance = np.maximum(
            np.abs(world_x - float(source.x)),
            np.abs(world_y - float(source.y)),
        )
        falloff = np.clip(1.0 - (distance / radius), 0.0, 1.0)
        # Square the falloff so light pools near the source and fades out
        # gently, instead of forming a hard linear cone.
        contribution = (falloff ** 2) * float(source.intensity)
        np.maximum(strength, contribution, out=strength)

        if not source.tints:
            continue
        source_color = np.asarray(source.color, dtype=np.float32)
        stronger = contribution > warm
        warm = np.where(stronger, contribution, warm)
        tint[stronger] = source_color

    return strength, warm, tint
