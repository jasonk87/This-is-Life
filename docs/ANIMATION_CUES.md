# Animation Cues

## Purpose
The animation cue system provides a very lightweight, deterministic way to visually communicate actions in the headless sandbox, and acts as a foundation for future visual feedback. It is intentionally simple, supporting small actor offsets, state swaps, and overlays, rather than complex skeletal or frame-by-frame asset manipulation.

## Cue Structure
Each cue is defined in `simulation/animation_cues.py` as an `AnimationCue`.
It contains:
- `cue_id`: Unique identifier (e.g., 'open_door')
- `frame_count`: The number of frames
- `frame_duration`: Duration of each frame (in ticks or ms)
- `frames`: A list of `CueFrame` objects defining offsets and overlays
- `impact_frame`: Optional frame index when an action "hits"
- `state_change_frame`: Optional frame index when a target changes state
- `metadata`: Additional properties

Each `CueFrame` supports:
- `actor_offset`: (x, y) offset for the actor
- `target_offset`: (x, y) offset for the target
- `actor_overlay`: Character to display over the actor
- `target_overlay`: Character to display over the target
- `actor_state`: Descriptive state for the actor
- `target_state`: Descriptive state for the target

## Preview Tool
You can generate a frame strip preview of any registered cue without launching the full game:

```bash
python tools/asset_workbench.py --preview-animation open_door
python tools/asset_workbench.py --preview-animation chop_tree
python tools/asset_workbench.py --preview-animation build
```

This outputs a horizontal frame strip PNG and JSON metadata.

## Sandbox Trace Integration
In simulation scenarios, you can attach the `cue_id` to trace metadata to assert that an action fired:

```python
trace.event(
    tick=self.game_time,
    event_type="door_opened",
    actor=npc,
    metadata={"animation_cue": "open_door"}
)
```

## Limitations
- This is **not** a real-time playback system.
- This is **not** a full skeletal animation engine.
- Rendering relies on simple tile modifications and text overlays, prioritizing developer observability over player-facing polish.
