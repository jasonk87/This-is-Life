"""Single source of truth for camera/zoom/coordinate math.

Phase 0 of the visual-overhaul design doc (see
docs/ — "This is Life — Full Visual Overhaul" design doc, Section 3,
"Coordinate system & camera sync") flagged that this math already exists in
two separate, hand-kept-in-sync copies:

  - main.py:            _get_zoom, _get_world_view_size, _get_camera_origin,
                         _screen_to_world_position
  - console_renderer.py: _get_zoom_factor, _get_world_view_dimensions,
                         _world_to_screen_rect, _screen_to_world

Both copies currently agree (verified by tests/test_camera.py, which ports
each old formula verbatim and asserts this module produces identical
output). This module is the new shared implementation. It intentionally
does NOT depend on `World`, `tcod`, or `pygame` - it is pure arithmetic over
plain ints/floats, so it can be imported and unit-tested with zero
third-party dependencies, and so the same object can drive both the tcod
console path (console-cell coordinates) and the new pygame sprite path
(pixel coordinates), which is the whole point: one camera, two renderers,
no drift between them.

Existing call sites (main.py, console_renderer.py) are NOT migrated to use
this module yet - that migration is Phase 1+ scope, once the pygame sprite
layer actually exists and there is a real second caller to keep in sync
with. Phase 0 only needs this module to exist and be provably correct.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Camera:
    """Camera/viewport state plus the coordinate transforms derived from it.

    All of `zoom_levels`, `zoom_index`, `map_width`, `map_height`,
    `world_width`, `world_height` mirror the exact fields the existing code
    reads off `world` (`world.zoom_levels`, `world.zoom_index`) and off
    `config` (`MAP_WIDTH`, `MAP_HEIGHT`, `WORLD_WIDTH`, `WORLD_HEIGHT`).
    `tile_size` is new: it is `config.TILE_SIZE`, the pixel size of one
    console cell in the base (unzoomed) tileset, and is what lets this
    module additionally answer in *pixels* - something neither existing
    implementation needed to do, since tcod only ever draws to console
    cells. The pygame sprite layer draws to pixels, so this is the bridge.
    """

    zoom_levels: tuple[float, ...]
    zoom_index: int
    map_width: int
    map_height: int
    world_width: int
    world_height: int
    tile_size: int = 16

    # -- zoom -----------------------------------------------------------
    #
    # Ported verbatim from console_renderer._get_zoom_factor /
    # main.py._get_zoom: clamp the index into range, default to 1.0 if no
    # zoom levels are configured at all (matches console_renderer's
    # behavior for a bare/fake world in tests; main.py's _get_zoom instead
    # calls _ensure_zoom_state first so it never sees an empty tuple - both
    # end up at the same effective default in practice).
    @property
    def zoom(self) -> float:
        if not self.zoom_levels:
            return 1.0
        index = max(0, min(int(self.zoom_index), len(self.zoom_levels) - 1))
        return float(self.zoom_levels[index])

    # -- viewport size in world tiles -----------------------------------
    #
    # Ported verbatim from console_renderer._get_world_view_dimensions /
    # main.py._get_world_view_size.
    def view_dimensions(self) -> tuple[int, int]:
        zoom = self.zoom
        view_width = max(1, int(math.ceil(self.map_width / zoom)))
        view_height = max(1, int(math.ceil(self.map_height / zoom)))
        return min(self.world_width, view_width), min(self.world_height, view_height)

    # -- camera origin (top-left world tile currently in view) ----------
    #
    # Ported verbatim from main.py._get_camera_origin. console_renderer.py
    # does not compute this itself - it is handed camera_x/camera_y as
    # arguments by main.py's render loop - so there is only one existing
    # implementation to port here, not two.
    def origin_for_player(self, player_x: int, player_y: int) -> tuple[int, int]:
        view_width, view_height = self.view_dimensions()
        camera_x = int(player_x) - view_width // 2
        camera_y = int(player_y) - view_height // 2
        camera_x = max(0, min(camera_x, max(0, self.world_width - view_width)))
        camera_y = max(0, min(camera_y, max(0, self.world_height - view_height)))
        return camera_x, camera_y

    # -- world <-> console-cell screen coordinates -----------------------
    #
    # Ported verbatim from console_renderer._screen_to_world /
    # main.py._screen_to_world_position (identical formula in both).
    def screen_to_world(
        self, camera_x: int, camera_y: int, screen_x: int, screen_y: int
    ) -> tuple[int, int]:
        zoom = self.zoom
        return camera_x + int(screen_x // zoom), camera_y + int(screen_y // zoom)

    # Ported verbatim from console_renderer._world_to_screen_rect. Returns
    # the inclusive (x0, y0, x1, y1) block of console cells one world tile
    # occupies at the current zoom, clipped to the MAP_WIDTH x MAP_HEIGHT
    # viewport, or None if the tile is entirely outside it.
    def world_to_screen_rect(
        self, camera_x: int, camera_y: int, world_x: int, world_y: int
    ) -> tuple[int, int, int, int] | None:
        zoom = self.zoom
        rel_x = world_x - camera_x
        rel_y = world_y - camera_y
        x0 = int(math.floor(rel_x * zoom))
        y0 = int(math.floor(rel_y * zoom))
        x1 = int(math.floor((rel_x + 1) * zoom) - 1)
        y1 = int(math.floor((rel_y + 1) * zoom) - 1)
        if x1 < x0:
            x1 = x0
        if y1 < y0:
            y1 = y0
        if x1 < 0 or y1 < 0 or x0 >= self.map_width or y0 >= self.map_height:
            return None
        return (
            max(0, x0),
            max(0, y0),
            min(self.map_width - 1, x1),
            min(self.map_height - 1, y1),
        )

    # -- world <-> pixel coordinates (new: the tcod/pygame bridge) ------
    #
    # Not a port of anything - neither existing implementation needed
    # pixels, since tcod only draws to console cells. This is the one new
    # piece of math Phase 0 actually needed: given the console-cell rect a
    # world tile occupies (above), scale it by `tile_size` to get the pixel
    # rect the SAME tile occupies in the shared window. Both renderers are
    # drawing into a window sized SCREEN_WIDTH*TILE_SIZE x
    # SCREEN_HEIGHT*TILE_SIZE (see config.WINDOW_WIDTH/WINDOW_HEIGHT), so a
    # console cell at (x0, y0) is unambiguously pixel (x0*TILE_SIZE,
    # y0*TILE_SIZE) regardless of which library put it there.
    def world_to_pixel_rect(
        self, camera_x: int, camera_y: int, world_x: int, world_y: int
    ) -> tuple[int, int, int, int] | None:
        cell_rect = self.world_to_screen_rect(camera_x, camera_y, world_x, world_y)
        if cell_rect is None:
            return None
        x0, y0, x1, y1 = cell_rect
        ts = self.tile_size
        # Pixel rect spans from the top-left of cell (x0, y0) to the
        # bottom-right of cell (x1, y1), inclusive of the full size of the
        # last cell - mirrors how the cell rect itself is inclusive.
        return (x0 * ts, y0 * ts, (x1 + 1) * ts - 1, (y1 + 1) * ts - 1)

    def world_to_pixel_topleft(
        self, camera_x: int, camera_y: int, world_x: int, world_y: int
    ) -> tuple[int, int] | None:
        """Convenience wrapper: just the top-left pixel of a world tile's
        rect, which is what a pygame.Rect/blit call actually wants."""
        rect = self.world_to_pixel_rect(camera_x, camera_y, world_x, world_y)
        if rect is None:
            return None
        return rect[0], rect[1]


def camera_from_world(world, *, map_width: int, map_height: int, world_width: int, world_height: int, tile_size: int = 16) -> Camera:
    """Build a Camera from a `World`-like object the way main.py/
    console_renderer.py currently read zoom state directly off `world`.

    Mirrors console_renderer._get_zoom_factor's defensive getattr use (a
    bare/fake world with no zoom_levels set behaves like zoom=1.0) rather
    than main.py's _ensure_zoom_state, which mutates the world object.
    This function deliberately never mutates its argument.
    """
    zoom_levels = tuple(getattr(world, "zoom_levels", None) or ())
    zoom_index = int(getattr(world, "zoom_index", 0) or 0)
    return Camera(
        zoom_levels=zoom_levels,
        zoom_index=zoom_index,
        map_width=map_width,
        map_height=map_height,
        world_width=world_width,
        world_height=world_height,
        tile_size=tile_size,
    )
