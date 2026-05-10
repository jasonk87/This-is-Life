"""Lightweight time-based activity state for actors.

This module intentionally keeps activities small and optional.  Callers can
attach ``current_activity`` and ``recent_completed_activities`` to any actor,
but the helpers also tolerate legacy actors that do not already have those
attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import itertools


_ACTIVITY_COUNTER = itertools.count(1)


@dataclass
class ActivityInstance:
    """A single in-progress or recently completed actor activity."""

    activity_id: str
    actor_id: int | str | None
    activity_type: str
    started_tick: int
    duration_ticks: int
    progress_ticks: int = 0
    location: tuple[int, int] | None = None
    anchor_coords: tuple[int, int] | None = None
    allows_conversation: bool = False
    allows_observation: bool = True
    allows_social_sharing: bool = False
    interruptible: bool = True
    completed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_ticks(self) -> int:
        return max(0, int(self.duration_ticks) - int(self.progress_ticks))


def ensure_activity_state(actor) -> None:
    """Attach optional activity attributes to legacy actors if missing."""
    if actor is None:
        return
    if not hasattr(actor, "current_activity"):
        actor.current_activity = None
    if not hasattr(actor, "recent_completed_activities"):
        actor.recent_completed_activities = []


def start_activity(
    actor,
    activity_type: str,
    duration_ticks: int,
    *,
    world=None,
    location: tuple[int, int] | None = None,
    anchor_coords: tuple[int, int] | None = None,
    allows_conversation: bool = False,
    allows_observation: bool = True,
    allows_social_sharing: bool = False,
    interruptible: bool = True,
    activity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ActivityInstance:
    """Start a timed activity for an actor and return the new instance."""
    ensure_activity_state(actor)
    current_tick = int(getattr(world, "game_time", 0)) if world is not None else 0
    if location is None and actor is not None and hasattr(actor, "x") and hasattr(actor, "y"):
        location = (int(actor.x), int(actor.y))
    instance = ActivityInstance(
        activity_id=activity_id or f"activity-{next(_ACTIVITY_COUNTER)}",
        actor_id=getattr(actor, "id", None),
        activity_type=str(activity_type),
        started_tick=current_tick,
        duration_ticks=max(0, int(duration_ticks)),
        location=location,
        anchor_coords=anchor_coords,
        allows_conversation=bool(allows_conversation),
        allows_observation=bool(allows_observation),
        allows_social_sharing=bool(allows_social_sharing),
        interruptible=bool(interruptible),
        metadata=dict(metadata or {}),
    )
    actor.current_activity = instance
    return instance


def advance_activity(actor, world=None) -> ActivityInstance | None:
    """Advance an actor's current activity by one tick, completing if done."""
    ensure_activity_state(actor)
    activity = getattr(actor, "current_activity", None)
    if activity is None:
        return None
    if activity.completed:
        complete_activity(actor, world)
        return None
    activity.progress_ticks += 1
    if activity.progress_ticks >= activity.duration_ticks:
        complete_activity(actor, world)
    return getattr(actor, "current_activity", None)


def complete_activity(actor, world=None) -> ActivityInstance | None:
    """Mark an activity complete, apply lightweight effects, and archive it."""
    ensure_activity_state(actor)
    activity = getattr(actor, "current_activity", None)
    if activity is None:
        return None
    activity.completed = True
    activity.progress_ticks = max(int(activity.progress_ticks), int(activity.duration_ticks))
    _apply_completion_effects(actor, activity, world)
    actor.current_activity = None
    recent = getattr(actor, "recent_completed_activities", None)
    if recent is None:
        actor.recent_completed_activities = []
        recent = actor.recent_completed_activities
    recent.append(activity)
    del recent[:-10]
    return activity


def is_actor_available_for_conversation(actor) -> bool:
    """Return whether the actor can participate in lightweight ambient talk."""
    ensure_activity_state(actor)
    if getattr(getattr(actor, "physical", None), "is_dead", False):
        return False
    activity = getattr(actor, "current_activity", None)
    if activity is None:
        return True
    return bool(getattr(activity, "allows_conversation", False))


def can_actor_observe_nearby_events(actor) -> bool:
    """Return whether an actor can notice nearby events during its activity."""
    ensure_activity_state(actor)
    if getattr(getattr(actor, "physical", None), "is_dead", False):
        return False
    activity = getattr(actor, "current_activity", None)
    if activity is None:
        return True
    return bool(getattr(activity, "allows_observation", True))


def _apply_completion_effects(actor, activity: ActivityInstance, world=None) -> None:
    metadata = getattr(activity, "metadata", {}) or {}
    physical = getattr(actor, "physical", None)
    if physical is not None:
        if not metadata.get("needs_already_applied"):
            if "reduces_hunger" in metadata:
                physical.hunger = max(0, int(getattr(physical, "hunger", 0)) - int(metadata.get("reduces_hunger") or 0))
            if "reduces_thirst" in metadata:
                physical.thirst = max(0, int(getattr(physical, "thirst", 0)) - int(metadata.get("reduces_thirst") or 0))
    if str(activity.activity_type).startswith("work:") and hasattr(actor, "sub_task_timer"):
        actor.sub_task_timer = 0
    if metadata.get("set_task_on_complete") and hasattr(getattr(actor, "schedule", None), "current_task"):
        actor.schedule.current_task = str(metadata["set_task_on_complete"])
    if activity.activity_type in {"resting", "sitting", "idle_social"} and metadata.get("clear_sitting_on_complete"):
        if hasattr(actor, "is_sitting"):
            actor.is_sitting = False
        if hasattr(actor, "sitting_on_object_at"):
            actor.sitting_on_object_at = None
        state = getattr(actor, "state", None)
        if state is not None:
            if hasattr(state, "is_sitting"):
                state.is_sitting = False
            if hasattr(state, "sitting_on_object_at"):
                state.sitting_on_object_at = None
