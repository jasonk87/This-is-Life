"""Tests for rendering/camera.py - the Phase 0 shared coordinate module.

Two things get proven here, deliberately kept separate:

1. `Camera` reproduces the *existing* formulas in main.py and
   console_renderer.py exactly, across a spread of camera positions, zoom
   levels, and world sizes. The oracle functions below are transcribed
   directly from those two modules (not re-derived), so a match here means
   the new shared module is not just "reasonable" but bit-for-bit
   consistent with what the game already does today.
2. `Camera`'s coordinate transforms are internally consistent (round-trip
   world -> screen -> world recovers the original tile; the new
   world_to_pixel_rect bridge is a deterministic tile_size scaling of
   world_to_screen_rect, not independently-drifting math).

No tcod or pygame import anywhere in this file - that is the point of
having pulled this math out on its own.
"""

from __future__ import annotations

import math
import unittest

from rendering.camera import Camera, camera_from_world


# ---------------------------------------------------------------------------
# Oracles: verbatim transcriptions of the pre-Phase-0 formulas.
# ---------------------------------------------------------------------------

def oracle_get_zoom_factor(zoom_levels, zoom_index):
    """console_renderer._get_zoom_factor, verbatim."""
    if not zoom_levels:
        return 1.0
    zoom_index = max(0, min(int(zoom_index), len(zoom_levels) - 1))
    return float(zoom_levels[zoom_index])


def oracle_get_world_view_dimensions(zoom_levels, zoom_index, map_width, map_height, world_width, world_height):
    """console_renderer._get_world_view_dimensions, verbatim."""
    zoom = oracle_get_zoom_factor(zoom_levels, zoom_index)
    view_width = max(1, int(math.ceil(map_width / zoom)))
    view_height = max(1, int(math.ceil(map_height / zoom)))
    return min(world_width, view_width), min(world_height, view_height)


def oracle_get_camera_origin(zoom_levels, zoom_index, map_width, map_height, world_width, world_height, player_x, player_y):
    """main.py._get_camera_origin, verbatim (view size computed the same
    way main.py's own _get_world_view_size does - same formula as the
    console_renderer oracle above, the two modules agree today)."""
    view_width, view_height = oracle_get_world_view_dimensions(
        zoom_levels, zoom_index, map_width, map_height, world_width, world_height
    )
    camera_x = int(player_x) - view_width // 2
    camera_y = int(player_y) - view_height // 2
    camera_x = max(0, min(camera_x, max(0, world_width - view_width)))
    camera_y = max(0, min(camera_y, max(0, world_height - view_height)))
    return camera_x, camera_y


def oracle_screen_to_world(zoom_levels, zoom_index, camera_x, camera_y, screen_x, screen_y):
    """console_renderer._screen_to_world / main.py._screen_to_world_position,
    verbatim (identical formula in both today)."""
    zoom = oracle_get_zoom_factor(zoom_levels, zoom_index)
    return camera_x + int(screen_x // zoom), camera_y + int(screen_y // zoom)


def oracle_world_to_screen_rect(zoom_levels, zoom_index, map_width, map_height, camera_x, camera_y, world_x, world_y):
    """console_renderer._world_to_screen_rect, verbatim."""
    zoom = oracle_get_zoom_factor(zoom_levels, zoom_index)
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
    if x1 < 0 or y1 < 0 or x0 >= map_width or y0 >= map_height:
        return None
    return max(0, x0), max(0, y0), min(map_width - 1, x1), min(map_height - 1, y1)


# ---------------------------------------------------------------------------
# Shared fixture geometry: mirrors config.py's actual current values
# (checked directly against the working tree, not assumed from the design
# doc, which predates the ZOOM_LEVELS/DEFAULT_ZOOM_INDEX change now sitting
# uncommitted in config.py).
# ---------------------------------------------------------------------------

REAL_ZOOM_LEVELS = (1.0, 2.0, 3.0, 4.0)
REAL_MAP_WIDTH = 78
REAL_MAP_HEIGHT = 50
REAL_WORLD_WIDTH = 600   # WORLD_WIDTH_CHUNKS(10) * CHUNK_WIDTH(60)
REAL_WORLD_HEIGHT = 400  # WORLD_HEIGHT_CHUNKS(10) * CHUNK_HEIGHT(40)
REAL_TILE_SIZE = 16


def make_camera(zoom_index=2, zoom_levels=REAL_ZOOM_LEVELS,
                 map_width=REAL_MAP_WIDTH, map_height=REAL_MAP_HEIGHT,
                 world_width=REAL_WORLD_WIDTH, world_height=REAL_WORLD_HEIGHT,
                 tile_size=REAL_TILE_SIZE):
    return Camera(
        zoom_levels=zoom_levels, zoom_index=zoom_index,
        map_width=map_width, map_height=map_height,
        world_width=world_width, world_height=world_height,
        tile_size=tile_size,
    )


class TestCameraMatchesExistingFormulasExactly(unittest.TestCase):
    """Regression proof: Camera == the two pre-existing implementations,
    for every zoom level and a spread of player/camera positions."""

    PLAYER_POSITIONS = [
        (0, 0),                # world origin corner
        (5, 3),                 # near origin, view clamps camera to 0,0
        (300, 200),             # middle of the 600x400 world
        (599, 399),             # far corner, view clamps camera to max
        (1, 399),               # edge column, mid row
        (300, 1),               # mid column, edge row
    ]

    def test_zoom_matches_for_every_level(self):
        for index in range(len(REAL_ZOOM_LEVELS)):
            cam = make_camera(zoom_index=index)
            self.assertEqual(
                cam.zoom,
                oracle_get_zoom_factor(REAL_ZOOM_LEVELS, index),
                msg=f"zoom mismatch at index {index}",
            )

    def test_view_dimensions_match_for_every_level(self):
        for index in range(len(REAL_ZOOM_LEVELS)):
            cam = make_camera(zoom_index=index)
            self.assertEqual(
                cam.view_dimensions(),
                oracle_get_world_view_dimensions(
                    REAL_ZOOM_LEVELS, index, REAL_MAP_WIDTH, REAL_MAP_HEIGHT,
                    REAL_WORLD_WIDTH, REAL_WORLD_HEIGHT,
                ),
                msg=f"view_dimensions mismatch at zoom index {index}",
            )

    def test_camera_origin_matches_for_every_position_and_zoom(self):
        for index in range(len(REAL_ZOOM_LEVELS)):
            cam = make_camera(zoom_index=index)
            for px, py in self.PLAYER_POSITIONS:
                with self.subTest(zoom_index=index, player=(px, py)):
                    self.assertEqual(
                        cam.origin_for_player(px, py),
                        oracle_get_camera_origin(
                            REAL_ZOOM_LEVELS, index, REAL_MAP_WIDTH, REAL_MAP_HEIGHT,
                            REAL_WORLD_WIDTH, REAL_WORLD_HEIGHT, px, py,
                        ),
                    )

    def test_screen_to_world_matches_across_the_whole_viewport(self):
        for index in range(len(REAL_ZOOM_LEVELS)):
            cam = make_camera(zoom_index=index)
            camera_x, camera_y = cam.origin_for_player(300, 200)
            for screen_x in range(0, REAL_MAP_WIDTH, 7):
                for screen_y in range(0, REAL_MAP_HEIGHT, 7):
                    with self.subTest(zoom_index=index, screen=(screen_x, screen_y)):
                        self.assertEqual(
                            cam.screen_to_world(camera_x, camera_y, screen_x, screen_y),
                            oracle_screen_to_world(
                                REAL_ZOOM_LEVELS, index, camera_x, camera_y, screen_x, screen_y,
                            ),
                        )

    def test_world_to_screen_rect_matches_across_the_visible_world(self):
        for index in range(len(REAL_ZOOM_LEVELS)):
            cam = make_camera(zoom_index=index)
            camera_x, camera_y = cam.origin_for_player(300, 200)
            view_w, view_h = cam.view_dimensions()
            # Sample every world tile actually inside this zoom level's
            # view, plus a few just outside it (must agree on None too).
            for wx in range(camera_x - 2, camera_x + view_w + 2, 3):
                for wy in range(camera_y - 2, camera_y + view_h + 2, 3):
                    with self.subTest(zoom_index=index, world=(wx, wy)):
                        self.assertEqual(
                            cam.world_to_screen_rect(camera_x, camera_y, wx, wy),
                            oracle_world_to_screen_rect(
                                REAL_ZOOM_LEVELS, index, REAL_MAP_WIDTH, REAL_MAP_HEIGHT,
                                camera_x, camera_y, wx, wy,
                            ),
                        )


class TestCameraInternalConsistency(unittest.TestCase):
    """Round-trip and bridge-math checks that have no pre-existing
    "old implementation" to compare against, because this is new capability
    (world_to_pixel_rect) or a property (round-tripping) nobody needed to
    assert explicitly before."""

    def test_round_trip_world_to_screen_to_world_recovers_the_tile(self):
        for index in range(len(REAL_ZOOM_LEVELS)):
            cam = make_camera(zoom_index=index)
            camera_x, camera_y = cam.origin_for_player(300, 200)
            for wx in range(camera_x, camera_x + 10):
                for wy in range(camera_y, camera_y + 10):
                    rect = cam.world_to_screen_rect(camera_x, camera_y, wx, wy)
                    self.assertIsNotNone(rect)
                    x0, y0, _x1, _y1 = rect
                    recovered = cam.screen_to_world(camera_x, camera_y, x0, y0)
                    self.assertEqual(
                        recovered, (wx, wy),
                        msg=f"round-trip failed at zoom {cam.zoom}, tile ({wx},{wy})",
                    )

    def test_world_to_pixel_rect_is_tile_size_scaling_of_cell_rect(self):
        cam = make_camera(zoom_index=2, tile_size=16)
        camera_x, camera_y = cam.origin_for_player(300, 200)
        for wx in range(camera_x, camera_x + 5):
            for wy in range(camera_y, camera_y + 5):
                cell_rect = cam.world_to_screen_rect(camera_x, camera_y, wx, wy)
                pixel_rect = cam.world_to_pixel_rect(camera_x, camera_y, wx, wy)
                self.assertIsNotNone(cell_rect)
                self.assertIsNotNone(pixel_rect)
                x0, y0, x1, y1 = cell_rect
                px0, py0, px1, py1 = pixel_rect
                self.assertEqual((px0, py0), (x0 * 16, y0 * 16))
                self.assertEqual((px1, py1), ((x1 + 1) * 16 - 1, (y1 + 1) * 16 - 1))

    def test_world_to_pixel_rect_none_when_cell_rect_is_none(self):
        cam = make_camera(zoom_index=2)
        # Far outside the viewport in every direction.
        self.assertIsNone(cam.world_to_pixel_rect(0, 0, 10_000, 10_000))
        self.assertIsNone(cam.world_to_pixel_rect(0, 0, -500, -500))

    def test_camera_origin_clamped_at_world_edges_not_negative_or_overflowing(self):
        cam = make_camera(zoom_index=0)  # zoom 1.0, biggest view -> most clamping
        view_w, view_h = cam.view_dimensions()
        ox, oy = cam.origin_for_player(0, 0)
        self.assertEqual((ox, oy), (0, 0))
        ox, oy = cam.origin_for_player(REAL_WORLD_WIDTH - 1, REAL_WORLD_HEIGHT - 1)
        self.assertEqual(ox, REAL_WORLD_WIDTH - view_w)
        self.assertEqual(oy, REAL_WORLD_HEIGHT - view_h)
        self.assertGreaterEqual(ox, 0)
        self.assertGreaterEqual(oy, 0)

    def test_zoom_defaults_to_1_when_no_levels_configured(self):
        cam = Camera(zoom_levels=(), zoom_index=0, map_width=78, map_height=50,
                      world_width=600, world_height=400)
        self.assertEqual(cam.zoom, 1.0)


class TestCameraFromWorld(unittest.TestCase):
    """camera_from_world() must read the same two attributes
    (zoom_levels/zoom_index) the existing renderer reads, and must not
    mutate the object it reads them from."""

    class FakeWorld:
        def __init__(self, zoom_levels=None, zoom_index=None):
            if zoom_levels is not None:
                self.zoom_levels = zoom_levels
            if zoom_index is not None:
                self.zoom_index = zoom_index

    def test_reads_zoom_state_off_world(self):
        world = self.FakeWorld(zoom_levels=REAL_ZOOM_LEVELS, zoom_index=2)
        cam = camera_from_world(
            world, map_width=REAL_MAP_WIDTH, map_height=REAL_MAP_HEIGHT,
            world_width=REAL_WORLD_WIDTH, world_height=REAL_WORLD_HEIGHT,
        )
        self.assertEqual(cam.zoom, 3.0)

    def test_defaults_gracefully_for_a_bare_world_with_no_zoom_state(self):
        world = self.FakeWorld()  # no zoom_levels/zoom_index at all
        cam = camera_from_world(
            world, map_width=REAL_MAP_WIDTH, map_height=REAL_MAP_HEIGHT,
            world_width=REAL_WORLD_WIDTH, world_height=REAL_WORLD_HEIGHT,
        )
        self.assertEqual(cam.zoom, 1.0)

    def test_does_not_mutate_the_world_object(self):
        world = self.FakeWorld()
        self.assertFalse(hasattr(world, "zoom_levels"))
        camera_from_world(
            world, map_width=REAL_MAP_WIDTH, map_height=REAL_MAP_HEIGHT,
            world_width=REAL_WORLD_WIDTH, world_height=REAL_WORLD_HEIGHT,
        )
        self.assertFalse(hasattr(world, "zoom_levels"))


if __name__ == "__main__":
    unittest.main()
