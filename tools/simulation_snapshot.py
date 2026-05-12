"""Lightweight AI-readable snapshot rendering for simulation sandbox runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import struct
import zlib


DEFAULT_OVERLAYS = {"claims", "paths", "buildings", "npcs", "wildlife", "blueprints", "chunks"}
PNG_CELL_SIZE = 6


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
            "Legend: . terrain, = road, B building, C construction, c claim, "
            "N npc, W wildlife, * path, |/- chunk, ! failure"
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
        _write_png(output_path, canvas)
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
                    name = str(getattr(tile, "name", "") or "").lower()
                    if "road" in name:
                        canvas.set(x, y, "=", (120, 120, 120))
                    elif "water" in name or "river" in name:
                        canvas.set(x, y, "~", (40, 80, 150))
                    elif "forest" in name or "tree" in name:
                        canvas.set(x, y, "^", (28, 90, 34))
                    else:
                        canvas.set(x, y, ".", (38, 66, 42))


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
        canvas.rect(
            int(getattr(building, "global_origin_x", getattr(building, "x", 0))),
            int(getattr(building, "global_origin_y", getattr(building, "y", 0))),
            int(getattr(building, "width", 1)),
            int(getattr(building, "height", 1)),
            "B",
            (70, 58, 48),
        )


def _draw_blueprints(canvas: SnapshotCanvas, world: Any) -> None:
    for blueprint in getattr(world, "blueprints_by_id", {}).values():
        canvas.rect(
            int(getattr(blueprint, "x", 0)),
            int(getattr(blueprint, "y", 0)),
            int(getattr(blueprint, "width", 1)),
            int(getattr(blueprint, "height", 1)),
            "C",
            (220, 190, 45),
        )


def _draw_actors(canvas: SnapshotCanvas, world: Any, overlays: set[str]) -> None:
    for actor in _all_actors(world):
        is_wildlife = getattr(actor, "animal_type", None) is not None
        if is_wildlife and "wildlife" not in overlays:
            continue
        if not is_wildlife and "npcs" not in overlays:
            continue
        canvas.set(
            int(getattr(actor, "x", 0)),
            int(getattr(actor, "y", 0)),
            "W" if is_wildlife else "N",
            (170, 70, 210) if is_wildlife else (245, 245, 245),
        )


def _draw_failures(canvas: SnapshotCanvas, trace: Any | None) -> None:
    if trace is None:
        return
    for event in getattr(trace, "events", []):
        if getattr(event, "event_type", None) not in {"path_failed", "assertion_failed"}:
            continue
        location = getattr(event, "location", None)
        if location and len(location) >= 2:
            canvas.set(int(location[0]), int(location[1]), "!", (230, 35, 35))


def _all_actors(world: Any) -> list[Any]:
    return list(getattr(world, "village_npcs", []) or []) + list(getattr(world, "npcs", []) or [])


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
