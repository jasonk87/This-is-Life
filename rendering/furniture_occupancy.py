"""Visual furniture attachments, derived from live state without moving actors.

Sitting intentionally keeps the actor's logical tile beside its chair. Sleeping
is also used by macro simulation: render_disabled actors are never bed occupants.
"""

from dataclasses import dataclass

from rendering import interior_art, pixel_scene as pixels


@dataclass(frozen=True)
class Attachment:
    kind: str
    key: str
    x: int
    y: int


def present(world, actor):
    if actor is None or getattr(actor, "render_disabled", False):
        return False
    if getattr(getattr(actor, "state", None), "is_riding", False):
        return False
    return not (
        actor is not getattr(world, "player", None)
        and getattr(actor, "is_sleeping", False)
        and not pixels.enabled(world)
    )


def attachment_for(world, actor):
    if not present(world, actor) or not interior_art.enabled(world):
        return None
    if getattr(actor, "animal_type", None):
        return None
    if getattr(getattr(actor, "physical", None), "is_dead", False):
        return None
    get_tile = getattr(world, "get_tile_at", None)
    if get_tile is None:
        return None
    from rendering.console_renderer import is_visible

    if not is_visible(world, actor.x, actor.y):
        return None
    state, schedule = getattr(actor, "state", None), getattr(actor, "schedule", None)
    if getattr(schedule, "current_path", None) or getattr(state, "current_path", None):
        return None
    sleeping = (
        getattr(actor, "is_sleeping", False)
        or getattr(state, "is_sleeping", False)
        or getattr(schedule, "current_task", None) == "sleeping"
    )
    if sleeping:
        # Bed interactions put the sleeper ON the bed. Do not borrow a nearby
        # bed merely because a schedule says sleep, or because one is unoccupied.
        key = interior_art.furniture_key(get_tile(actor.x, actor.y))
        if key in {"wooden_bed", "bed_simple"}:
            return Attachment("reclining", key, actor.x, actor.y)
        return None
    if not (getattr(actor, "is_sitting", False) or getattr(state, "is_sitting", False)):
        return None
    anchor = getattr(actor, "sitting_on_object_at", None) or getattr(
        state, "sitting_on_object_at", None
    )
    activity = getattr(actor, "current_activity", None)
    if getattr(activity, "activity_type", None) == "sitting":
        if getattr(activity, "completed", False):
            return None
        location = getattr(activity, "location", None)
        if location is not None and tuple(location) != (actor.x, actor.y):
            return None  # Stale sitting flag after the actor has moved away.
        anchor = anchor or getattr(activity, "anchor_coords", None)
    if not isinstance(anchor, (tuple, list)) or len(anchor) != 2:
        return None
    x, y = anchor
    if not isinstance(x, int) or not isinstance(y, int):
        return None
    if max(abs(x - actor.x), abs(y - actor.y)) > 1 or not is_visible(world, x, y):
        return None
    key = interior_art.furniture_key(get_tile(x, y))
    if key in {"wooden_chair", "wooden_stool"}:
        return Attachment("seated", key, x, y)
    return None


def render_anchor(world, actor):
    attachment = attachment_for(world, actor)
    if attachment:
        return attachment.x, attachment.y
    x, y = getattr(actor, "render_x", actor.x), getattr(actor, "render_y", actor.y)
    if abs(x - actor.x) > 1.5 or abs(y - actor.y) > 1.5:
        x, y = actor.x, actor.y
    return round(x), round(y)


def overlay_anchor(world, actor):
    return render_anchor(world, actor) if pixels.enabled(world) else (actor.x, actor.y)
