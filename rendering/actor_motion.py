"""Presentation-only memory of observed movement, never written into a save."""

from dataclasses import dataclass


@dataclass
class Motion:
    actor: object
    position: tuple
    direction: str = "south"
    moving_until: int = -1


_world = None
_last_tick = -1
_records = {}


def reset():
    global _world, _last_tick
    _world, _last_tick = None, -1
    _records.clear()


def direction_from(dx, dy, default="south"):
    if not dx and not dy:
        return default
    if abs(dx) > abs(dy):
        return "east" if dx > 0 else "west"
    return "south" if dy > 0 else "north"


def observe(world, actor):
    global _world, _last_tick
    tick = int(getattr(world, "game_time", 0))
    if world is not _world or tick < _last_tick:
        reset()
        _world = world
    _last_tick = tick
    key = id(actor)
    position = (actor.x, actor.y)
    record = _records.get(key)
    if record is None or record.actor is not actor:
        if len(_records) >= 8192:
            _records.clear()
        record = _records[key] = Motion(actor, position)
    dx, dy = position[0] - record.position[0], position[1] - record.position[1]
    if 0 < max(abs(dx), abs(dy)) <= 1.5:
        record.direction = direction_from(dx, dy, record.direction)
        record.moving_until = tick + 4
    elif dx or dy:
        record.moving_until = -1  # Spawns/teleports are not walking.
    record.position = position
    # Interpolation is evidence of a real step, not merely a queued path.
    rx, ry = getattr(actor, "render_x", actor.x), getattr(actor, "render_y", actor.y)
    ix, iy = actor.x - rx, actor.y - ry
    interpolating = 0.01 < max(abs(ix), abs(iy)) <= 1.5
    if interpolating:
        record.direction = direction_from(ix, iy, record.direction)
    if actor is getattr(world, "player", None):
        state = getattr(actor, "state", None)
        record.direction = direction_from(
            getattr(state, "last_dx", 0), getattr(state, "last_dy", 0), record.direction
        )
    return record.direction, interpolating or tick < record.moving_until
