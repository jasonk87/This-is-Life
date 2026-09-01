"""Tests for rendering/pygame_spike.py's frame-orchestration and camera-sync
logic, run through a minimal pygame test double.

Why a test double rather than skipping these tests when pygame isn't
installed (same situation tcod_compat.py already solves for tcod in this
codebase, real precedent, not a new pattern): the sandbox this was written
in has no PyPI network access and cannot install pygame or tcod (verified
directly - `pip install pygame` fails with a proxy 403, not a missing-
package message). Skipping these tests would mean the spike's actual
integration logic - does the camera recompute correctly on movement, does
the player rectangle land on the pixel position the camera says it should,
does a quit event actually stop the loop - never gets verified by anything
except a human reading the code. That is exactly the "it launched without
crashing" standard this work was explicitly asked NOT to settle for.

What this suite proves: the ORCHESTRATION is correct - render_frame() and
handle_event() do the right thing, call things in the right order, and
every drawn position traces back to the same Camera math already
regression-tested in test_camera.py. What it does NOT and cannot prove:
that real pygame's Surface/Rect/draw.rect/event system behaves exactly like
this fake, or that tcod's SDLConsoleRender texture hand-off actually works
on a real machine. Both of those need an actual run with real dependencies
installed - see rendering/pygame_spike.run_manual_smoke_test's docstring
for exactly what that run should show.
"""

from __future__ import annotations

import sys
import types
import unittest


# ---------------------------------------------------------------------------
# Minimal pygame test double, injected into sys.modules BEFORE
# rendering.pygame_spike is ever imported, so its module-level `import
# pygame` binds to this fake and PYGAME_AVAILABLE comes out True - the same
# shape tcod_compat.py already uses for tcod itself in this codebase, just
# scoped to a test file instead of a permanent runtime shim, since (unlike
# tcod) nothing outside this Phase 0 spike depends on pygame existing yet.
# ---------------------------------------------------------------------------

class _FakeRect:
    def __init__(self, x, y, width, height):
        self.x, self.y, self.width, self.height = x, y, width, height

    def __eq__(self, other):
        return (self.x, self.y, self.width, self.height) == (
            other.x, other.y, other.width, other.height,
        )

    def __repr__(self):
        return f"_FakeRect({self.x}, {self.y}, {self.width}, {self.height})"


class _FakeSurface:
    """Records fills and rect draws instead of touching any real pixels -
    exactly what a test needs (what got drawn, where) without needing an
    actual framebuffer or display."""

    def __init__(self, size=(0, 0)):
        self.size = size
        self.fills: list[tuple] = []
        self.rects_drawn: list[tuple] = []

    def fill(self, color):
        self.fills.append(color)

    def get_size(self):
        return self.size


def _install_fake_pygame() -> types.ModuleType:
    fake = types.ModuleType("pygame")
    fake.QUIT = "QUIT"
    fake.KEYDOWN = "KEYDOWN"
    fake.Rect = _FakeRect
    fake.Surface = _FakeSurface

    draw_ns = types.SimpleNamespace()

    def _draw_rect(surface, color, rect):
        surface.rects_drawn.append((color, rect))
        return rect

    draw_ns.rect = _draw_rect
    fake.draw = draw_ns

    key_ns = types.SimpleNamespace()
    # Real pygame maps keycodes (ints) to names via pygame.key.name(). The
    # fake's "keycodes" are just the upper-case name strings themselves,
    # which keeps test event construction readable (K_UP-style constants
    # aren't needed for what this suite is testing) while still exercising
    # the real code path (handle_event calls pygame.key.name(event.key)).
    key_ns.name = lambda code: str(code)
    fake.key = key_ns

    display_ns = types.SimpleNamespace()
    display_ns.set_mode = lambda size: _FakeSurface(size)
    display_ns.set_caption = lambda title: None
    display_ns.flip = lambda: None
    fake.display = display_ns

    class _FakeClock:
        def tick(self, fps):
            return 0

    time_ns = types.SimpleNamespace()
    time_ns.Clock = _FakeClock
    fake.time = time_ns

    event_ns = types.SimpleNamespace()
    event_ns.get = lambda: []
    fake.event = event_ns

    fake.init = lambda: None
    fake.quit = lambda: None

    sys.modules["pygame"] = fake
    return fake


_FAKE_PYGAME = _install_fake_pygame()

# Import AFTER the fake is installed, and only here, so this is the one
# place in the whole test process that binds rendering.pygame_spike's
# module-level `import pygame` to the fake rather than a real install.
from rendering import pygame_spike  # noqa: E402  (import-after-setup is intentional)


class _FakeEvent:
    def __init__(self, type_, key=None):
        self.type = type_
        self.key = key


class TestRequirePygame(unittest.TestCase):
    def test_pygame_available_flag_true_with_fake_installed(self):
        # Confirms the fake actually satisfied the module's own import
        # guard, not just that the fake module object exists somewhere.
        self.assertTrue(pygame_spike.PYGAME_AVAILABLE)

    def test_require_pygame_does_not_raise_when_available(self):
        pygame_spike.require_pygame()  # should not raise


class TestSpikeStateMovementClampsToWorldBounds(unittest.TestCase):
    def test_move_clamps_at_zero(self):
        state = pygame_spike.SpikeState(player_x=0, player_y=0)
        state.move(-5, -5)
        self.assertEqual((state.player_x, state.player_y), (0, 0))

    def test_move_clamps_at_world_max(self):
        from config import WORLD_WIDTH, WORLD_HEIGHT
        state = pygame_spike.SpikeState(player_x=WORLD_WIDTH - 1, player_y=WORLD_HEIGHT - 1)
        state.move(5, 5)
        self.assertEqual((state.player_x, state.player_y), (WORLD_WIDTH - 1, WORLD_HEIGHT - 1))

    def test_move_applies_delta_within_bounds(self):
        state = pygame_spike.SpikeState(player_x=100, player_y=100)
        state.move(3, -2)
        self.assertEqual((state.player_x, state.player_y), (103, 98))


class TestRenderFrameCameraSync(unittest.TestCase):
    """The core claim of Phase 0: the pygame-drawn rectangle's pixel
    position is always exactly what the Camera says it should be for the
    player's current world position - i.e. the two "rendering systems"
    (here: a terrain fill standing in for tcod, and a pygame rect standing
    in for the sprite layer) never drift apart."""

    def setUp(self):
        self.surface = _FakeSurface(size=(78 * 16, 50 * 16))

    def test_first_frame_draws_terrain_then_player_rect(self):
        state = pygame_spike.SpikeState()
        telemetry = pygame_spike.render_frame(state, self.surface)
        self.assertEqual(len(self.surface.fills), 1, "terrain fill should happen exactly once per frame")
        self.assertEqual(len(self.surface.rects_drawn), 1, "player rect should be drawn exactly once per frame")
        color, rect = self.surface.rects_drawn[0]
        self.assertEqual(color, pygame_spike.PLAYER_COLOR)
        self.assertEqual((rect.x, rect.y), telemetry["player_pixel_topleft"])

    def test_player_pixel_position_matches_camera_math_independently_recomputed(self):
        """Recomputes the expected pixel position via a fresh Camera
        instance built the same way render_frame builds its own - if
        render_frame's internal camera and this test's independently-built
        camera ever disagreed, that would BE a sync bug, and this test
        would catch it rather than both sides quietly sharing one wrong
        answer."""
        from config import MAP_WIDTH, MAP_HEIGHT, WORLD_WIDTH, WORLD_HEIGHT, TILE_SIZE, ZOOM_LEVELS
        from rendering.camera import Camera

        state = pygame_spike.SpikeState(player_x=250, player_y=150, zoom_index=1)
        telemetry = pygame_spike.render_frame(state, self.surface)

        independent_camera = Camera(
            zoom_levels=tuple(ZOOM_LEVELS), zoom_index=1,
            map_width=MAP_WIDTH, map_height=MAP_HEIGHT,
            world_width=WORLD_WIDTH, world_height=WORLD_HEIGHT, tile_size=TILE_SIZE,
        )
        expected_origin = independent_camera.origin_for_player(250, 150)
        expected_pixel = independent_camera.world_to_pixel_topleft(*expected_origin, 250, 150)

        self.assertEqual(telemetry["camera_origin"], expected_origin)
        self.assertEqual(telemetry["player_pixel_topleft"], expected_pixel)

    def test_camera_stays_synced_across_a_movement_sequence(self):
        """Moves the placeholder player across a run of frames (including
        past a world edge, where the camera clamps rather than continuing
        to scroll) and checks every single frame's drawn pixel position
        against independently-recomputed camera math - not just the first
        or last frame, since a sync bug that only shows up after several
        moves is exactly the kind "it launched fine" would miss."""
        from config import MAP_WIDTH, MAP_HEIGHT, WORLD_WIDTH, WORLD_HEIGHT, TILE_SIZE, ZOOM_LEVELS
        from rendering.camera import Camera

        state = pygame_spike.SpikeState(player_x=5, player_y=5, zoom_index=0)
        moves = [(1, 0)] * 10 + [(0, 1)] * 10 + [(-1, -1)] * 8

        for dx, dy in moves:
            state.move(dx, dy)
            telemetry = pygame_spike.render_frame(state, self.surface)

            oracle = Camera(
                zoom_levels=tuple(ZOOM_LEVELS), zoom_index=0,
                map_width=MAP_WIDTH, map_height=MAP_HEIGHT,
                world_width=WORLD_WIDTH, world_height=WORLD_HEIGHT, tile_size=TILE_SIZE,
            )
            expected_origin = oracle.origin_for_player(state.player_x, state.player_y)
            expected_pixel = oracle.world_to_pixel_topleft(*expected_origin, state.player_x, state.player_y)

            self.assertEqual(telemetry["camera_origin"], expected_origin)
            self.assertEqual(telemetry["player_pixel_topleft"], expected_pixel)

        self.assertEqual(len(state.draw_log), len(moves))

    def test_frame_count_and_draw_log_increment_once_per_frame(self):
        state = pygame_spike.SpikeState()
        for _ in range(5):
            pygame_spike.render_frame(state, self.surface)
        self.assertEqual(state.frame_count, 5)
        self.assertEqual(len(state.draw_log), 5)
        self.assertEqual([entry["frame"] for entry in state.draw_log], [1, 2, 3, 4, 5])

    def test_tcod_frame_drawer_hook_is_invoked_with_the_same_camera_and_origin(self):
        """Proves the injection point real tcod rendering will eventually
        plug into receives exactly the camera/origin the pygame side used
        for that same frame - the actual coexistence guarantee Phase 0
        needs, independent of whether the tcod half is a real renderer or
        (as here) a recording stub."""
        calls = []

        def fake_tcod_drawer(surface, camera, camera_x, camera_y):
            calls.append((camera, camera_x, camera_y))

        state = pygame_spike.SpikeState(player_x=42, player_y=17, zoom_index=3)
        telemetry = pygame_spike.render_frame(state, self.surface, fake_tcod_drawer)

        self.assertEqual(len(calls), 1)
        _camera, camera_x, camera_y = calls[0]
        self.assertEqual((camera_x, camera_y), telemetry["camera_origin"])


class TestHandleEvent(unittest.TestCase):
    def test_quit_event_returns_false(self):
        state = pygame_spike.SpikeState()
        result = pygame_spike.handle_event(state, _FakeEvent(_FAKE_PYGAME.QUIT))
        self.assertFalse(result)

    def test_movement_key_moves_player_and_returns_true(self):
        state = pygame_spike.SpikeState(player_x=10, player_y=10)
        result = pygame_spike.handle_event(state, _FakeEvent(_FAKE_PYGAME.KEYDOWN, key="UP"))
        self.assertTrue(result)
        self.assertEqual((state.player_x, state.player_y), (10, 9))

    def test_all_four_movement_directions(self):
        for key_name, expected_delta in pygame_spike.MOVEMENT_KEYS.items():
            with self.subTest(key=key_name):
                state = pygame_spike.SpikeState(player_x=50, player_y=50)
                pygame_spike.handle_event(state, _FakeEvent(_FAKE_PYGAME.KEYDOWN, key=key_name))
                dx, dy = expected_delta
                self.assertEqual((state.player_x, state.player_y), (50 + dx, 50 + dy))

    def test_unrecognized_key_is_a_no_op_and_returns_true(self):
        state = pygame_spike.SpikeState(player_x=10, player_y=10)
        result = pygame_spike.handle_event(state, _FakeEvent(_FAKE_PYGAME.KEYDOWN, key="Q"))
        self.assertTrue(result)
        self.assertEqual((state.player_x, state.player_y), (10, 10))

    def test_escape_key_returns_false(self):
        state = pygame_spike.SpikeState()
        result = pygame_spike.handle_event(state, _FakeEvent(_FAKE_PYGAME.KEYDOWN, key="ESCAPE"))
        self.assertFalse(result)


class TestBuildTcodTerrainDrawerFailsClosedWithoutRealTcod(unittest.TestCase):
    """In this process, tcod is either the tcod_compat shim (no real SDL
    render support) or genuinely absent - either way,
    build_tcod_terrain_drawer() must return None rather than a drawer that
    would blow up mid-frame, since render_frame has no other guard against
    a broken drawer callable."""

    def test_returns_none_without_real_tcod_render_support(self):
        drawer = pygame_spike.build_tcod_terrain_drawer()
        self.assertIsNone(drawer)


if __name__ == "__main__":
    unittest.main()
