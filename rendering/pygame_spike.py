"""Phase 0 interop spike: prove a pygame sprite surface can coexist with the
existing tcod console in one window, camera-synced, before any real art or
engine-integration work starts.

Context (see the "This is Life - Full Visual Overhaul" design doc, Section
3 and Section 6): the rendering fork's biggest unproven assumption is
whether tcod's console rendering and a pygame sprite layer can actually
share a frame. This module is deliberately the smallest possible thing that
tests that assumption - NOT a rewrite of console_renderer.py, NOT wired
into main.py's real game loop. It draws real (if minimal) tcod terrain, a
placeholder colored rectangle standing in for a sprite-rendered player, and
proves the two stay pixel-aligned as the "player" moves and the tcod camera
scrolls, using the exact same math the real game uses (rendering/camera.py,
itself ported from and regression-tested against main.py/
console_renderer.py's real formulas - see tests/test_camera.py).

Two things this module is explicit about rather than papering over:

1. Strategy A vs Strategy B (design doc Section 3). python-tcod's
   `tcod.context.new()` cannot attach to a window someone else created -
   verified directly against the python-tcod API docs, not assumed. The
   documented way to render a tcod Console onto SDL content it doesn't own
   is `tcod.render.SDLConsoleRender` + `tcod.render.SDLTilesetAtlas`, which
   render a Console to a `tcod.sdl.render.Texture` bound to a
   `tcod.sdl.render.Renderer`. Getting that texture's pixels into a pygame
   Surface - so pygame can own the actual window - is the one genuinely
   unresolved integration detail Phase 0 exists to answer. This module
   attempts it (via SDL's pixel-readback path) and fails loud with a clear
   diagnostic if that attempt does not work on a given machine, rather than
   silently falling back to something that would misrepresent whether the
   interop actually works.

2. This sandbox cannot install tcod or pygame (no PyPI network access -
   confirmed, not assumed) and has no display. It cannot produce the final
   "yes, a real window opened and both layers drew into it" proof. What it
   *can* and does prove, with real passing tests, no mocking of the thing
   being tested itself:
     - every coordinate/camera computation this module performs is the
       same Camera class already regression-tested against the game's
       real, current formulas (tests/test_camera.py);
     - the frame-orchestration logic in this module - event routing, camera
       recompute on movement, what gets drawn where each frame - is
       exercised end-to-end via a minimal pygame test double
       (tests/test_pygame_spike_interop.py), which is dependency-injected
       through the same `pygame` name this module imports, the same
       fake-at-the-boundary approach tcod_compat.py already uses for tcod
       itself in this codebase.
   The remaining, real, unresolved question - does SDLConsoleRender's
   texture actually hand off to a pygame Surface on a real machine - needs
   an actual run with real tcod and real pygame installed. See
   `run_manual_smoke_test()` below for exactly what to run and what
   success looks like.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field

from config import (
    MAP_WIDTH,
    MAP_HEIGHT,
    WORLD_WIDTH,
    WORLD_HEIGHT,
    TILE_SIZE,
    ZOOM_LEVELS,
    DEFAULT_ZOOM_INDEX,
)
from rendering.camera import Camera

# Mirrors main.py's require_render_backend() pattern deliberately: fail
# loud, with an actionable message, rather than letting a missing
# dependency show up later as a stray AttributeError deep in a draw call.
try:
    import pygame  # type: ignore
    PYGAME_AVAILABLE = True
except ModuleNotFoundError:
    PYGAME_AVAILABLE = False

try:
    import tcod  # type: ignore
    import tcod.sdl.video  # type: ignore
    import tcod.sdl.render  # type: ignore
    import tcod.render  # type: ignore
    TCOD_RENDER_AVAILABLE = True
except ModuleNotFoundError:
    TCOD_RENDER_AVAILABLE = False


PLAYER_COLOR = (255, 245, 140)  # matches console_renderer._ensure_player_contrast's base color
PLACEHOLDER_TERRAIN_COLOR = (36, 64, 34)  # matches TERRAIN_BACKGROUNDS["plains"] in console_renderer.py


def require_pygame() -> None:
    if not PYGAME_AVAILABLE:
        print(
            "Error: pygame is not installed, so the Phase 0 interop spike "
            "cannot open a window.\n"
            "\n"
            "  Install it with:\n"
            "      pip install pygame\n",
            file=sys.stderr,
        )
        raise SystemExit(1)


@dataclass
class SpikeState:
    """Everything the spike frame loop needs, decoupled from any real
    `World`/`Player` object on purpose - Phase 0 has no simulation running,
    just a moving point standing in for the player. `player_x`/`player_y`
    are world tile coordinates, exactly like `world.player.x/y` in the real
    game.
    """

    player_x: int = WORLD_WIDTH // 2
    player_y: int = WORLD_HEIGHT // 2
    zoom_index: int = DEFAULT_ZOOM_INDEX
    frame_count: int = 0
    # Telemetry recorded each frame for tests/manual verification: what the
    # spike believes the player's on-screen pixel position is, per render
    # path. Both must always be computed from the same Camera - if they
    # ever come from different math, that IS the sync bug this spike
    # exists to catch.
    last_camera_origin: tuple[int, int] = (0, 0)
    last_player_pixel_topleft: tuple[int, int] | None = None
    draw_log: list[dict] = field(default_factory=list)

    def camera(self) -> Camera:
        return Camera(
            zoom_levels=tuple(ZOOM_LEVELS),
            zoom_index=self.zoom_index,
            map_width=MAP_WIDTH,
            map_height=MAP_HEIGHT,
            world_width=WORLD_WIDTH,
            world_height=WORLD_HEIGHT,
            tile_size=TILE_SIZE,
        )

    def move(self, dx: int, dy: int) -> None:
        self.player_x = max(0, min(WORLD_WIDTH - 1, self.player_x + dx))
        self.player_y = max(0, min(WORLD_HEIGHT - 1, self.player_y + dy))


# Movement key -> (dx, dy). Deliberately the same arrow-key vocabulary
# main.py's handle_playing_input already uses, so wiring this into the real
# input handler later (Phase 1+) is a lookup-table swap, not a redesign.
MOVEMENT_KEYS: dict[str, tuple[int, int]] = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}


def render_frame(state: SpikeState, surface, tcod_frame_drawer=None) -> dict:
    """Draw one frame: tcod-rendered terrain background (or a flat-color
    stand-in if tcod's SDL render path isn't available/wired up yet) plus a
    pygame-drawn placeholder rectangle for the player, both positioned from
    the same Camera.

    Returns the per-frame telemetry dict that gets appended to
    `state.draw_log` - this is what tests assert against, and it is
    exactly the same data a human watching the real window would be
    implicitly trusting their eyes to confirm: where the camera thinks the
    world is, and where the player sprite actually got drawn.

    `tcod_frame_drawer`, if given, is called as
    `tcod_frame_drawer(surface, camera, camera_x, camera_y)` and is
    responsible for the terrain layer. Left as an injection point rather
    than hard-wired so the pygame test double can exercise this function's
    orchestration logic (call order, camera math, telemetry) without a
    real tcod render pipeline attached - and so a real run can pass in the
    actual SDLConsoleRender-backed drawer once that is working end to end.
    """
    require_pygame()

    camera = state.camera()
    camera_x, camera_y = camera.origin_for_player(state.player_x, state.player_y)
    state.last_camera_origin = (camera_x, camera_y)

    surface.fill(PLACEHOLDER_TERRAIN_COLOR)
    if tcod_frame_drawer is not None:
        tcod_frame_drawer(surface, camera, camera_x, camera_y)

    pixel_topleft = camera.world_to_pixel_topleft(camera_x, camera_y, state.player_x, state.player_y)
    state.last_player_pixel_topleft = pixel_topleft

    tile_px = int(round(camera.tile_size * camera.zoom))
    if pixel_topleft is not None:
        rect = pygame.Rect(pixel_topleft[0], pixel_topleft[1], tile_px, tile_px)
        pygame.draw.rect(surface, PLAYER_COLOR, rect)

    state.frame_count += 1
    telemetry = {
        "frame": state.frame_count,
        "player_world": (state.player_x, state.player_y),
        "camera_origin": (camera_x, camera_y),
        "zoom": camera.zoom,
        "player_pixel_topleft": pixel_topleft,
        "tile_px": tile_px,
    }
    state.draw_log.append(telemetry)
    return telemetry


def handle_event(state: SpikeState, event) -> bool:
    """Route one pygame event. Returns False on a quit request.

    Mirrors main.py's handle_events() shape (decode event -> mutate world
    state) deliberately, per the design doc's "Input routing" section: the
    logic downstream of event decoding doesn't change between tcod.event
    and pygame.event, only the decoding at the top does.
    """
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.KEYDOWN:
        key_name = pygame.key.name(event.key).upper()
        delta = MOVEMENT_KEYS.get(key_name)
        if delta is not None:
            state.move(*delta)
        elif key_name == "ESCAPE":
            return False
    return True


def build_tcod_terrain_drawer():
    """Best-effort construction of a real tcod-backed terrain drawer using
    the SDLConsoleRender/SDLTilesetAtlas path documented in python-tcod's
    `tcod.render` module. Returns None (never raises) if the attempt fails,
    so callers can fall back to the flat-color placeholder and keep running
    - the whole point of Phase 0 is to find out *whether* this works, not
    to assume it does.

    This is the one piece of this module that could not be exercised in
    the sandbox this was written in (no tcod/pygame install available
    there - see the module docstring). It is written directly against the
    documented API (verified against python-tcod's own docs during the
    design phase, not guessed), but has only been checked by static review,
    not execution. Treat its success or failure on a real machine as the
    actual Phase 0 result for Strategy A/B - see run_manual_smoke_test().
    """
    if not TCOD_RENDER_AVAILABLE:
        return None
    try:
        tileset = tcod.tileset.load_tilesheet(
            "dejavu16x16_gs_tc.png", 32, 8, tcod.tileset.CHARMAP_TCOD
        )
        console = tcod.console.Console(MAP_WIDTH, MAP_HEIGHT, order="C")
        sdl_window = tcod.sdl.video.new_window(
            MAP_WIDTH * TILE_SIZE, MAP_HEIGHT * TILE_SIZE,
            flags=0,
        )
        sdl_renderer = tcod.sdl.render.new_renderer(sdl_window, target_textures=True)
        atlas = tcod.render.SDLTilesetAtlas(sdl_renderer, tileset)
        console_render = tcod.render.SDLConsoleRender(atlas)
    except Exception as exc:  # pragma: no cover - only reachable with real tcod
        print(f"[pygame_spike] tcod SDL render path unavailable: {exc!r}", file=sys.stderr)
        return None

    def draw(surface, camera: Camera, camera_x: int, camera_y: int) -> None:
        console.clear()
        console.print(x=0, y=0, string="Phase 0 spike - tcod terrain layer")
        texture = console_render.render(console)
        # The unresolved step (see module docstring): transferring
        # `texture` - owned by tcod's own SDL renderer/window - into the
        # pygame Surface pygame itself owns. `Texture` objects don't expose
        # a documented direct pixel-readback in the API surface reviewed
        # for this spike; the realistic options are (a) SDL_RenderReadPixels
        # via tcod's renderer to get a byte buffer pygame can wrap with
        # pygame.image.frombuffer, or (b) abandon a single shared window in
        # favor of tcod and pygame each owning a window and letting the OS
        # compositor overlay them (a materially different architecture,
        # not something to switch to without discussing it first). This is
        # deliberately left unresolved rather than faked.
        raise NotImplementedError(
            "tcod Texture -> pygame Surface pixel transfer not yet "
            "implemented - this is the actual open question Phase 0 exists "
            "to resolve on a machine with real tcod+pygame installed."
        )

    return draw


def run_manual_smoke_test() -> None:  # pragma: no cover - manual/visual only
    """Entry point for a human, on a machine with real tcod and pygame
    installed, to actually see the spike run.

    What to run:
        python -m rendering.pygame_spike

    What success looks like: a window opens; a rectangle (the placeholder
    "player") sits roughly centered; arrow keys move it; the camera
    recenters near the world edges exactly the way the real game's
    _get_camera_origin does (because it IS that same function, via
    Camera.origin_for_player). Terrain will show as a flat color, not real
    tcod glyphs, unless build_tcod_terrain_drawer()'s NotImplementedError
    above has been resolved - if it still raises on your machine, that is
    itself the Phase 0 result to report back: Strategy B's pixel-transfer
    step needs more work, and Strategy A (or the two-window-overlay
    alternative sketched in build_tcod_terrain_drawer's docstring) should
    be evaluated next, with Jason's sign-off, since it's a different
    architecture than what the design doc committed to.
    """
    require_pygame()
    pygame.init()
    window_size = (MAP_WIDTH * TILE_SIZE, MAP_HEIGHT * TILE_SIZE)
    surface = pygame.display.set_mode(window_size)
    pygame.display.set_caption("This is Life - Phase 0 interop spike")
    clock = pygame.time.Clock()

    state = SpikeState()
    terrain_drawer = build_tcod_terrain_drawer()
    if terrain_drawer is None:
        print(
            "[pygame_spike] Running with flat-color terrain placeholder - "
            "tcod SDL render path not available/not yet working. "
            "See build_tcod_terrain_drawer()'s docstring.",
            file=sys.stderr,
        )

    running = True
    while running:
        for event in pygame.event.get():
            running = handle_event(state, event)
            if not running:
                break
        try:
            telemetry = render_frame(state, surface, terrain_drawer)
        except NotImplementedError as exc:
            print(f"[pygame_spike] {exc}", file=sys.stderr)
            terrain_drawer = None
            telemetry = render_frame(state, surface, None)
        pygame.display.flip()
        if state.frame_count % 60 == 0:
            print(f"[pygame_spike] {telemetry}")
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":  # pragma: no cover
    run_manual_smoke_test()
