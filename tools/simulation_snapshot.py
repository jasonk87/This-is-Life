"""Lightweight AI-readable snapshot rendering for simulation sandbox runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import struct
import zlib

from data.dawnlike import (
    ANIMAL_SPRITES,
    HUMAN_SPRITES,
    ITEM_SPRITES,
    PROFESSION_SPRITES,
    WORLD_DECORATION_SPRITES,
    WORLD_TILE_SPRITES,
    get_entity_sprite,
)


DEFAULT_OVERLAYS = {"claims", "paths", "buildings", "npcs", "wildlife", "blueprints", "chunks", "items", "interactions", "labels"}
PNG_CELL_SIZE = 6
MAX_NPC_LABELS = 8


@dataclass
class SnapshotConfig:
    snapshot_path: str | None = None
    snapshot_every: int | None = None
    snapshot_dir: str | None = None
    overlays: set[str] = field(default_factory=lambda: set(DEFAULT_OVERLAYS))
    force_text: bool = False


class SnapshotCanvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.chars = [["." for _ in range(self.width)] for _ in range(self.height)]
        self.colors = [[(38, 66, 42) for _ in range(self.width)] for _ in range(self.height)]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def set(self, x: int, y: int, char: str, color: tuple[int, int, int]) -> None:
        if self.in_bounds(x, y):
            self.chars[y][x] = char[:1]
            self.colors[y][x] = color

    def rect(self, x: int, y: int, width: int, height: int, char: str, color: tuple[int, int, int]) -> None:
        for ty in range(y, y + max(0, height)):
            for tx in range(x, x + max(0, width)):
                self.set(tx, ty, char, color)

    def text(self) -> str:
        legend = (
            "Legend: . terrain, = road, # wall, _ floor, B building, C construction, c claim, "
            "N npc, W wildlife, i item, a anchor, x blocked, * path, |/- chunk, ! failure"
        )
        rows = ["".join(row) for row in self.chars]
        return legend + "\n" + "\n".join(rows) + "\n"


def parse_overlays(value: str | None) -> set[str]:
    if not value:
        return set(DEFAULT_OVERLAYS)
    overlays = {part.strip().lower() for part in value.split(",") if part.strip()}
    return overlays or set(DEFAULT_OVERLAYS)


def render_snapshot(
    world: Any,
    path: str | Path,
    *,
    overlays: Iterable[str] | None = None,
    trace: Any | None = None,
    force_text: bool = False,
) -> str:
    """Render a sandbox world snapshot to PNG, with text fallback.

    The renderer is intentionally independent of tcod and the game renderer. It
    writes a simple debug map suitable for agents and developers inspecting
    layout, ownership, pathing, and actor placement.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_set = set(DEFAULT_OVERLAYS if overlays is None else overlays)
    canvas = _build_canvas(world, overlay_set, trace=trace)

    if force_text or output_path.suffix.lower() not in {".png"}:
        output_path.write_text(canvas.text(), encoding="utf-8")
        return str(output_path)

    try:
        write_canvas_png(output_path, canvas)
    except Exception:
        output_path.write_text(canvas.text(), encoding="utf-8")
    return str(output_path)


def write_snapshot_artifact(
    world: Any,
    trace: Any,
    config: SnapshotConfig | None,
    path: str | Path,
    *,
    artifacts: dict[str, Any] | None = None,
    periodic: bool = False,
) -> str | None:
    if config is None:
        return None
    rendered_path = render_snapshot(world, path, overlays=config.overlays, trace=trace, force_text=config.force_text)
    if artifacts is not None:
        if periodic:
            artifacts.setdefault("snapshots", []).append(rendered_path)
        else:
            artifacts["snapshot"] = rendered_path
    return rendered_path


def maybe_write_periodic_snapshot(
    world: Any,
    trace: Any,
    config: SnapshotConfig | None,
    scenario: str,
    tick: int,
    artifacts: dict[str, Any],
) -> None:
    if config is None or not config.snapshot_every or not config.snapshot_dir:
        return
    if tick <= 0 or tick % config.snapshot_every != 0:
        return
    suffix = ".txt" if config.force_text else ".png"
    path = Path(config.snapshot_dir) / f"{scenario}_{tick:06d}{suffix}"
    write_snapshot_artifact(world, trace, config, path, artifacts=artifacts, periodic=True)


def finalize_snapshot_artifacts(
    world: Any,
    trace: Any,
    config: SnapshotConfig | None,
    scenario: str,
    ticks: int,
    artifacts: dict[str, Any],
) -> None:
    if config is None:
        return
    if config.snapshot_every and config.snapshot_dir:
        for tick in range(config.snapshot_every, ticks + 1, config.snapshot_every):
            suffix = ".txt" if config.force_text else ".png"
            path = Path(config.snapshot_dir) / f"{scenario}_{tick:06d}{suffix}"
            rendered = str(path)
            if rendered not in artifacts.get("snapshots", []):
                write_snapshot_artifact(world, trace, config, path, artifacts=artifacts, periodic=True)
    if config.snapshot_path:
        write_snapshot_artifact(world, trace, config, config.snapshot_path, artifacts=artifacts, periodic=False)


def _build_canvas(world: Any, overlays: set[str], *, trace: Any | None = None) -> SnapshotCanvas:
    width, height = _world_dimensions(world)
    canvas = SnapshotCanvas(width, height)
    _draw_terrain(canvas, world)
    if "items" in overlays:
        _draw_items(canvas, world)
    if "claims" in overlays:
        _draw_claims(canvas, world)
    if "chunks" in overlays:
        _draw_chunks(canvas, world)
    if "paths" in overlays:
        _draw_paths(canvas, world)
    if "buildings" in overlays:
        _draw_buildings(canvas, world)
    if "blueprints" in overlays:
        _draw_blueprints(canvas, world)
    if "interactions" in overlays:
        _draw_interactions(canvas, world)
    if "npcs" in overlays or "wildlife" in overlays:
        _draw_actors(canvas, world, overlays)
    _draw_failures(canvas, trace)
    return canvas


def _world_dimensions(world: Any) -> tuple[int, int]:
    try:
        import engine

        chunk_size = int(engine.CHUNK_SIZE)
    except Exception:
        chunk_size = 80
    return max(1, int(getattr(world, "chunk_width", 1)) * chunk_size), max(1, int(getattr(world, "chunk_height", 1)) * chunk_size)


def _draw_terrain(canvas: SnapshotCanvas, world: Any) -> None:
    try:
        import engine

        chunk_size = int(engine.CHUNK_SIZE)
    except Exception:
        chunk_size = 80
    chunks = getattr(world, "chunks", []) or []
    for chunk_y, row in enumerate(chunks):
        for chunk_x, chunk in enumerate(row):
            tiles = getattr(chunk, "tiles", None) or []
            for local_y, tile_row in enumerate(tiles[:chunk_size]):
                for local_x, tile in enumerate(tile_row[:chunk_size]):
                    x = chunk_x * chunk_size + local_x
                    y = chunk_y * chunk_size + local_y
                    tile_key = _tile_asset_key(tile)
                    color = _asset_color(WORLD_TILE_SPRITES.get(tile_key))
                    char = _tile_char(tile_key)
                    canvas.set(x, y, char, color)
                    _draw_tile_decoration(canvas, tile, x, y)


def _draw_claims(canvas: SnapshotCanvas, world: Any) -> None:
    for claim in getattr(world, "land_claims_by_id", {}).values():
        if not getattr(claim, "active", True):
            continue
        tiles = set(getattr(claim, "claimed_tiles", set())) | set(getattr(claim, "reserved_tiles", set()))
        for x, y in tiles:
            canvas.set(int(x), int(y), "c", (50, 95, 210))


def _draw_chunks(canvas: SnapshotCanvas, world: Any) -> None:
    try:
        import engine

        chunk_size = int(engine.CHUNK_SIZE)
    except Exception:
        chunk_size = 80
    for x in range(0, canvas.width, chunk_size):
        for y in range(canvas.height):
            canvas.set(x, y, "|", (88, 88, 88))
    for y in range(0, canvas.height, chunk_size):
        for x in range(canvas.width):
            canvas.set(x, y, "-", (88, 88, 88))


def _draw_paths(canvas: SnapshotCanvas, world: Any) -> None:
    for actor in _all_actors(world):
        schedule = getattr(actor, "schedule", None)
        path = list(getattr(schedule, "current_path", []) or [])
        destination = getattr(schedule, "current_destination_coords", None)
        for point in path:
            if len(point) >= 2:
                canvas.set(int(point[0]), int(point[1]), "*", (230, 145, 35))
        if destination and len(destination) >= 2:
            canvas.set(int(destination[0]), int(destination[1]), "*", (230, 145, 35))


def _draw_buildings(canvas: SnapshotCanvas, world: Any) -> None:
    for building in getattr(world, "buildings_by_id", {}).values():
        x = int(getattr(building, "global_origin_x", getattr(building, "x", 0)))
        y = int(getattr(building, "global_origin_y", getattr(building, "y", 0)))
        width = int(getattr(building, "width", 1))
        height = int(getattr(building, "height", 1))
        wall_color = _asset_color(WORLD_TILE_SPRITES.get(_building_wall_key(building)))
        floor_color = _asset_color(WORLD_TILE_SPRITES.get("wood_floor"))
        canvas.rect(x, y, width, height, "B", wall_color)
        if width > 2 and height > 2:
            canvas.rect(x + 1, y + 1, width - 2, height - 2, "_", floor_color)
        canvas.set(x + width // 2, y + height - 1, "+", _asset_color(WORLD_DECORATION_SPRITES.get("wooden_door_closed")))


def _draw_blueprints(canvas: SnapshotCanvas, world: Any) -> None:
    for blueprint in getattr(world, "blueprints_by_id", {}).values():
        x = int(getattr(blueprint, "x", 0))
        y = int(getattr(blueprint, "y", 0))
        width = int(getattr(blueprint, "width", 1))
        height = int(getattr(blueprint, "height", 1))
        color = _asset_color(ITEM_SPRITES.get(next(iter(getattr(blueprint, "required_materials", {}) or {}), "raw_log")))
        canvas.rect(x, y, width, height, "C", color)
        # Make the footprint edges clear for layout inspection.
        for tx in range(x, x + width):
            canvas.set(tx, y, "C", (245, 220, 75))
            canvas.set(tx, y + height - 1, "C", (245, 220, 75))
        for ty in range(y, y + height):
            canvas.set(x, ty, "C", (245, 220, 75))
            canvas.set(x + width - 1, ty, "C", (245, 220, 75))


def _draw_actors(canvas: SnapshotCanvas, world: Any, overlays: set[str]) -> None:
    actors = _all_actors(world)
    label_budget = MAX_NPC_LABELS if len([actor for actor in actors if getattr(actor, "animal_type", None) is None]) <= 20 else 3
    labels_used = 0
    for actor in actors:
        is_wildlife = getattr(actor, "animal_type", None) is not None
        if is_wildlife and "wildlife" not in overlays:
            continue
        if not is_wildlife and "npcs" not in overlays:
            continue
        x = int(getattr(actor, "x", 0))
        y = int(getattr(actor, "y", 0))
        sprite = _safe_entity_sprite(actor)
        color = _asset_color(sprite)
        canvas.set(x, y, "W" if is_wildlife else "N", color)
        if is_wildlife:
            continue
        profession = str(getattr(getattr(actor, "economic", None), "profession", "") or "")
        badge = _profession_badge(profession)
        canvas.set(x + 1, y, badge, _asset_color(PROFESSION_SPRITES.get(profession)))
        carried = _first_inventory_key(getattr(getattr(actor, "economic", None), "npc_inventory", None))
        if carried:
            canvas.set(x, y + 1, "t", _asset_color(ITEM_SPRITES.get(carried)))
        important = getattr(actor, "task_context", None) in {"delivery", "construction", "hunting"}
        if "labels" in overlays and labels_used < label_budget and (important or labels_used < 3):
            _draw_compact_label(canvas, x + 2, y, _actor_label(actor, important=important))
            labels_used += 1


def _draw_failures(canvas: SnapshotCanvas, trace: Any | None) -> None:
    if trace is None:
        return
    for event in getattr(trace, "events", []):
        if getattr(event, "event_type", None) not in {"path_failed", "assertion_failed"}:
            continue
        location = getattr(event, "location", None)
        if location and len(location) >= 2:
            canvas.set(int(location[0]), int(location[1]), "!", (230, 35, 35))


def _draw_items(canvas: SnapshotCanvas, world: Any) -> None:
    for (x, y), inventory in (getattr(world, "items_on_map", {}) or {}).items():
        item_key = _first_inventory_key(inventory)
        if item_key:
            canvas.set(int(x), int(y), "i", _asset_color(ITEM_SPRITES.get(item_key)))


def _draw_interactions(canvas: SnapshotCanvas, world: Any) -> None:
    for building in getattr(world, "buildings_by_id", {}).values():
        for anchor in getattr(building, "anchors", []) or []:
            x = anchor.get("x")
            y = anchor.get("y")
            if x is not None and y is not None:
                canvas.set(int(x), int(y), "a", (90, 220, 240))
        for coords in (getattr(building, "interaction_points", {}) or {}).values():
            for x, y in _iter_coords(coords):
                canvas.set(int(x), int(y), "a", (90, 220, 240))
        for coords in (getattr(building, "work_zone_tiles", {}) or {}).values():
            for x, y in _iter_coords(coords):
                canvas.set(int(x), int(y), "a", (90, 220, 240))
    _draw_blocked_tiles(canvas, world)


def _iter_coords(coords: Any):
    if not coords:
        return
    if isinstance(coords, tuple) and len(coords) == 2 and all(isinstance(value, int) for value in coords):
        yield coords
        return
    for candidate in coords:
        if isinstance(candidate, tuple) and len(candidate) == 2:
            yield candidate


def _draw_blocked_tiles(canvas: SnapshotCanvas, world: Any) -> None:
    chunks = getattr(world, "chunks", []) or []
    try:
        import engine

        chunk_size = int(engine.CHUNK_SIZE)
    except Exception:
        chunk_size = 80
    for chunk_y, row in enumerate(chunks):
        for chunk_x, chunk in enumerate(row):
            for local_y, tile_row in enumerate((getattr(chunk, "tiles", None) or [])[:chunk_size]):
                for local_x, tile in enumerate(tile_row[:chunk_size]):
                    props = getattr(tile, "properties", {}) or {}
                    name = str(getattr(tile, "name", "") or "").lower()
                    if props.get("door_state") == "blocked" or props.get("blocked_interaction") or ("door" in name and not getattr(tile, "passable", True)):
                        canvas.set(chunk_x * chunk_size + local_x, chunk_y * chunk_size + local_y, "x", (225, 40, 40))


def _tile_asset_key(tile: Any) -> str:
    props = getattr(tile, "properties", {}) or {}
    for key in (props.get("tile_key"), props.get("sprite_key"), props.get("item_key")):
        normalized = _normalize_key(key)
        if normalized in WORLD_TILE_SPRITES:
            return normalized
    name = _normalize_key(getattr(tile, "name", None))
    if name in WORLD_TILE_SPRITES:
        return name
    if "road" in name:
        return "road"
    if "water" in name or "river" in name:
        return "water"
    if "wall" in name:
        return "wood_wall"
    if "floor" in name:
        return "wood_floor"
    if "grass" in name:
        return "tall_grass"
    if "tree" in name or "forest" in name:
        return "tree_generic"
    if "door" in name:
        return "door"
    return "plains"


def _draw_tile_decoration(canvas: SnapshotCanvas, tile: Any, x: int, y: int) -> None:
    props = getattr(tile, "properties", {}) or {}
    candidates = [props.get("decoration_key"), props.get("item_key"), _normalize_key(getattr(tile, "name", None))]
    for candidate in candidates:
        key = _normalize_key(candidate)
        if key in WORLD_DECORATION_SPRITES:
            canvas.set(x, y, _decoration_char(key), _asset_color(WORLD_DECORATION_SPRITES[key]))
            return


def _tile_char(tile_key: str) -> str:
    if "road" in tile_key:
        return "="
    if "wall" in tile_key:
        return "#"
    if "floor" in tile_key:
        return "_"
    if "water" in tile_key:
        return "~"
    if "tree" in tile_key or "forest" in tile_key:
        return "^"
    if "door" in tile_key:
        return "+"
    return "."


def _decoration_char(key: str) -> str:
    if "door" in key:
        return "+"
    if "bed" in key:
        return "b"
    if "chair" in key:
        return "h"
    if "table" in key or "desk" in key or "counter" in key:
        return "T"
    if "forge" in key or "fire" in key:
        return "f"
    if "corpse" in key:
        return "%"
    return "d"


def _building_wall_key(building: Any) -> str:
    building_type = _normalize_key(getattr(building, "building_type", None))
    if "jail" in building_type:
        return "jail_bars"
    if "sheriff" in building_type:
        return "sheriff_office_wall"
    if "capital" in building_type:
        return "capital_hall_wall"
    return "wood_wall"


def _safe_entity_sprite(actor: Any) -> int | None:
    try:
        profession = getattr(getattr(actor, "economic", None), "profession", None)
        if profession in PROFESSION_SPRITES:
            return PROFESSION_SPRITES[profession]
        return get_entity_sprite(actor)
    except Exception:
        return HUMAN_SPRITES.get("unemployed")


def _asset_color(codepoint: int | None, fallback: tuple[int, int, int] = (160, 160, 160)) -> tuple[int, int, int]:
    if codepoint is None:
        return fallback
    value = int(codepoint)
    return (70 + (value * 37) % 170, 70 + (value * 53) % 170, 70 + (value * 97) % 170)


def _profession_badge(profession: str) -> str:
    return (profession[:1] or "?").upper()


def _actor_label(actor: Any, *, important: bool) -> str:
    name = str(getattr(actor, "name", "NPC") or "NPC").split()[0][:6]
    if not important:
        return name
    profession = str(getattr(getattr(actor, "economic", None), "profession", "") or "")[:4]
    task = str(getattr(getattr(actor, "schedule", None), "current_task", "") or "")[:4]
    return ":".join(part for part in (name, profession, task) if part)


def _draw_compact_label(canvas: SnapshotCanvas, x: int, y: int, label: str) -> None:
    for offset, char in enumerate(label[:12]):
        canvas.set(x + offset, y, char, (235, 235, 235))


def _first_inventory_key(inventory: Any) -> str | None:
    if not inventory:
        return None
    if hasattr(inventory, "items"):
        for key, quantity in inventory.items():
            if int(quantity) > 0:
                return str(key)
    if isinstance(inventory, dict):
        for key, quantity in inventory.items():
            if int(quantity) > 0:
                return str(key)
    return None


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _all_actors(world: Any) -> list[Any]:
    return list(getattr(world, "village_npcs", []) or []) + list(getattr(world, "npcs", []) or [])


def write_canvas_png(path: Path | str, canvas: SnapshotCanvas) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_png(output_path, canvas)


def _write_png(path: Path, canvas: SnapshotCanvas) -> None:
    width = canvas.width * PNG_CELL_SIZE
    height = canvas.height * PNG_CELL_SIZE
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # no filter
        cell_y = y // PNG_CELL_SIZE
        for x in range(width):
            cell_x = x // PNG_CELL_SIZE
            r, g, b = canvas.colors[cell_y][cell_x]
            raw.extend((r, g, b, 255))

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
    png.extend(chunk(b"IDAT", zlib.compress(bytes(raw))))
    png.extend(chunk(b"IEND", b""))
    path.write_bytes(bytes(png))
