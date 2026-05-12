"""Lightweight reusable animation cue system for readable world actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass
class CueFrame:
    """Represents a single frame in an animation cue."""
    actor_offset: tuple[int, int] = (0, 0)
    target_offset: tuple[int, int] = (0, 0)
    actor_overlay: str | None = None
    target_overlay: str | None = None
    actor_state: str | None = None
    target_state: str | None = None

@dataclass
class AnimationCue:
    """Defines a tiny readable action cue for visual feedback."""
    cue_id: str
    frame_count: int
    frame_duration: int  # in ms or ticks
    frames: list[CueFrame] = field(default_factory=list)
    impact_frame: int | None = None
    state_change_frame: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.frames:
            self.frames = [CueFrame() for _ in range(self.frame_count)]
        if len(self.frames) != self.frame_count:
            raise ValueError(f"Cue {self.cue_id} frames length ({len(self.frames)}) does not match frame_count ({self.frame_count}).")

ANIMATION_CUES: dict[str, AnimationCue] = {}

def register_cue(cue: AnimationCue) -> None:
    ANIMATION_CUES[cue.cue_id] = cue

def get_cue(cue_id: str) -> AnimationCue | None:
    return ANIMATION_CUES.get(cue_id)

# Initialize standard cues

register_cue(AnimationCue(
    cue_id="open_door",
    frame_count=3,
    frame_duration=10,
    frames=[
        CueFrame(actor_offset=(0, 0)),
        CueFrame(actor_offset=(1, 0), target_state="open"),
        CueFrame(actor_offset=(0, 0), target_state="open"),
    ],
    state_change_frame=1,
))

register_cue(AnimationCue(
    cue_id="chop_tree",
    frame_count=4,
    frame_duration=8,
    frames=[
        CueFrame(actor_offset=(0, 0)),
        CueFrame(actor_offset=(-1, 0)),
        CueFrame(actor_offset=(1, 0), target_overlay="*"),
        CueFrame(actor_offset=(0, 0), target_state="stump"),
    ],
    impact_frame=2,
    state_change_frame=3,
))

register_cue(AnimationCue(
    cue_id="build",
    frame_count=4,
    frame_duration=5,
    frames=[
        CueFrame(actor_offset=(0, 0)),
        CueFrame(actor_offset=(0, -1), actor_overlay="*"),
        CueFrame(actor_offset=(0, 0), actor_overlay="+"),
        CueFrame(actor_offset=(0, 0)),
    ],
    impact_frame=2,
))

register_cue(AnimationCue(
    cue_id="attack_lunge",
    frame_count=4,
    frame_duration=3,
    frames=[
        CueFrame(actor_offset=(0, 0)),
        CueFrame(actor_offset=(1, 0)),
        CueFrame(actor_offset=(2, 0), target_overlay="!"),
        CueFrame(actor_offset=(0, 0)),
    ],
    impact_frame=2,
))

register_cue(AnimationCue(
    cue_id="butcher_work",
    frame_count=4,
    frame_duration=10,
    frames=[
        CueFrame(actor_offset=(0, 0)),
        CueFrame(actor_offset=(0, 0), actor_overlay="/"),
        CueFrame(actor_offset=(0, 0), actor_overlay="-"),
        CueFrame(actor_offset=(0, 0)),
    ],
    impact_frame=2,
))

register_cue(AnimationCue(
    cue_id="haul_carry",
    frame_count=2,
    frame_duration=20,
    frames=[
        CueFrame(actor_offset=(0, 0), actor_overlay="i"),
        CueFrame(actor_offset=(0, -1), actor_overlay="i"),
    ],
))

register_cue(AnimationCue(
    cue_id="drink_or_eat",
    frame_count=3,
    frame_duration=10,
    frames=[
        CueFrame(actor_offset=(0, 0)),
        CueFrame(actor_offset=(0, 0), actor_overlay="d"),
        CueFrame(actor_offset=(0, 0)),
    ],
))

register_cue(AnimationCue(
    cue_id="forge_hammer",
    frame_count=4,
    frame_duration=6,
    frames=[
        CueFrame(actor_offset=(0, 0)),
        CueFrame(actor_offset=(0, -1)),
        CueFrame(actor_offset=(0, 0), target_overlay="*"),
        CueFrame(actor_offset=(0, 0)),
    ],
    impact_frame=2,
))
