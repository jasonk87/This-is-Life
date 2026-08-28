"""Compatibility shim for environments where `tcod` is unavailable."""

from __future__ import annotations

import math
import sys
import types
from collections import deque

from runtime_compat import np

# Whether the real tcod is installed. The shim below is good enough for
# headless simulation and tests, but it cannot render: its Console discards
# every draw call and its event queue is always empty. Callers that need an
# actual window must check this rather than discovering it as a stray
# AttributeError deep inside tileset loading.
TCOD_AVAILABLE = True

try:
    import tcod as _tcod  # type: ignore
    from tcod import libtcodpy as _libtcodpy  # type: ignore

    tcod = _tcod
    libtcodpy = _libtcodpy
except ModuleNotFoundError:
    TCOD_AVAILABLE = False
    class _KeySym:
        UP = "UP"
        DOWN = "DOWN"
        LEFT = "LEFT"
        RIGHT = "RIGHT"
        RETURN = "RETURN"
        ESCAPE = "ESCAPE"
        E = "E"
        T = "T"
        C = "C"
        B = "B"
        I = "I"
        Q = "Q"
        QUESTION = "QUESTION"
        SLASH = "SLASH"
        TAB = "TAB"
        BACKSPACE = "BACKSPACE"
        LCTRL = "LCTRL"
        RCTRL = "RCTRL"
        PAGEUP = "PAGEUP"
        PAGEDOWN = "PAGEDOWN"

    class _MouseButton:
        LEFT = 1
        RIGHT = 3

    class _BaseEvent:
        def __init__(self, *args, **kwargs):
            self.__dict__.update(kwargs)

    for _letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        setattr(_KeySym, _letter, _letter)

    class _KeyDown(_BaseEvent):
        def __init__(self, scancode=0, sym=None, mod=0, repeat=False, **kwargs):
            super().__init__(
                scancode=scancode,
                sym=sym,
                mod=mod,
                repeat=repeat,
                **kwargs,
            )

    class _Quit(_BaseEvent):
        pass

    class _MouseMotion(_BaseEvent):
        pass

    class _MouseButtonDown(_BaseEvent):
        pass

    class _TextInput(_BaseEvent):
        pass

    class _MouseWheel(_BaseEvent):
        pass

    def _bresenham(start: tuple[int, int], end: tuple[int, int]):
        x0, y0 = start
        x1, y1 = end
        points = []
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            points.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
        return points

    def _compute_fov(transparency_map, origin, radius, algorithm=None):
        origin_y, origin_x = origin
        height, width = transparency_map.shape
        visible = np.zeros((height, width), dtype=bool)
        for y in range(height):
            for x in range(width):
                if (x - origin_x) ** 2 + (y - origin_y) ** 2 <= radius ** 2:
                    visible[y, x] = True
        return visible

    class _AStar:
        def __init__(self, cost, diagonal=1.41):
            self.cost = cost
            self.height, self.width = cost.shape
            self.allow_diagonal = diagonal is not None

        def get_path(self, start_x, start_y, end_x, end_y):
            start = (start_y, start_x)
            goal = (end_y, end_x)
            directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
            if self.allow_diagonal:
                directions += [(-1, -1), (-1, 1), (1, -1), (1, 1)]

            frontier = deque([start])
            came_from = {start: None}

            while frontier:
                current = frontier.popleft()
                if current == goal:
                    break
                for dy, dx in directions:
                    ny, nx = current[0] + dy, current[1] + dx
                    if not (0 <= ny < self.height and 0 <= nx < self.width):
                        continue
                    if self.cost[ny, nx] <= 0:
                        continue
                    neighbor = (ny, nx)
                    if neighbor in came_from:
                        continue
                    came_from[neighbor] = current
                    frontier.append(neighbor)

            if goal not in came_from:
                return []

            path = []
            current = goal
            while current is not None:
                path.append(current)
                current = came_from[current]
            path.reverse()
            return path

    class _Noise:
        class Algorithm:
            SIMPLEX = "SIMPLEX"

        class Implementation:
            SIMPLE = "SIMPLE"

        def __init__(self, *args, **kwargs):
            pass

        def __getitem__(self, key):
            return np.array(0.0, dtype=np.float32)

    class _Console:
        def __init__(self, width, height, order="F"):
            self.width = width
            self.height = height

        def clear(self):
            pass

        def print(self, *args, **kwargs):
            pass

        def print_box(self, *args, **kwargs):
            pass

        def draw_frame(self, *args, **kwargs):
            pass

    class _TilesetModule(types.SimpleNamespace):
        CHARMAP_TCOD = 0

        @staticmethod
        def load_tilesheet(*args, **kwargs):
            return object()

    class _ContextManager:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def present(self, console):
            pass

        def convert_event(self, event):
            return event

        def start_text_input(self):
            pass

        def stop_text_input(self):
            pass

    tcod = types.ModuleType("tcod")
    tcod.CENTER = 0
    tcod.noise = types.SimpleNamespace(
        Noise=_Noise,
        Algorithm=_Noise.Algorithm,
        Implementation=_Noise.Implementation,
    )
    tcod.los = types.SimpleNamespace(bresenham=_bresenham)
    tcod.map = types.SimpleNamespace(compute_fov=_compute_fov)
    tcod.path = types.SimpleNamespace(AStar=_AStar)
    tcod.console = types.SimpleNamespace(Console=_Console)
    tcod.tileset = _TilesetModule()
    tcod.context = types.SimpleNamespace(new=lambda **kwargs: _ContextManager())
    tcod.event = types.SimpleNamespace(
        KeySym=_KeySym,
        MouseButton=_MouseButton,
        KeyDown=_KeyDown,
        Quit=_Quit,
        MouseMotion=_MouseMotion,
        MouseButtonDown=_MouseButtonDown,
        TextInput=_TextInput,
        MouseWheel=_MouseWheel,
        get=lambda: [],
        wait=lambda timeout=None: [],
    )

    libtcodpy = types.SimpleNamespace(CENTER=0, FOV_SYMMETRIC_SHADOWCAST=0)

    sys.modules.setdefault("tcod", tcod)
    sys.modules.setdefault("tcod.event", tcod.event)
    sys.modules.setdefault("tcod.console", tcod.console)
    sys.modules.setdefault("tcod.tileset", tcod.tileset)
    sys.modules.setdefault("tcod.context", tcod.context)
    sys.modules.setdefault("tcod.noise", tcod.noise)
    sys.modules.setdefault("tcod.map", tcod.map)
    sys.modules.setdefault("tcod.path", tcod.path)
    sys.modules.setdefault("tcod.los", tcod.los)
