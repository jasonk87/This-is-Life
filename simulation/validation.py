"""Lightweight validation and warning aggregation for autonomous simulation systems."""

from __future__ import annotations

from typing import Any

DEFAULT_WARNING_COOLDOWN_TICKS = 120
MAX_STORED_VALIDATION_WARNINGS = 500

# The interaction trace log is the third diagnostic buffer on the world, and the
# only one that was never bounded. Warnings stop at 500 and decision explanations
# at 400; traces grew forever, at roughly 550 entries a tick with ninety villagers
# on the map. Measured over 6000 ticks - under half a game day - the log reached
# 3.28 million entries and the process 1.99 GB, both climbing in a straight line.
# A day of play would not fit in memory, and the log is pickled into saves, so
# every save carried the whole history with it.
#
# Nothing in the game reads it: it feeds build_world_debug_snapshot, which only
# ever takes a tail slice, and the sandbox scenarios, which assert across a whole
# run and set their own limit (see tools/simulation_scenarios._create_headless_world).
MAX_STORED_INTERACTION_TRACES = 20000


def _stable_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return dict(metadata or {})


# Floating text, projectiles, hit flashes. World.update_animations expires them
# against a real-seconds dt, and is only called from the render loop - so headless
# runs never prune at all and the list climbs forever (0.07/tick, dead straight).
# No player sees this; sandbox soaks and tests do. The cap is far above anything a
# rendering game reaches.
MAX_TRANSIENT_VISUAL_EFFECTS = 200


def trim_visual_effects(world: Any) -> None:
    """Bound the transient visual effect list. Call once a tick."""
    effects = getattr(world, "visual_effects", None)
    if not isinstance(effects, list) or len(effects) <= MAX_TRANSIENT_VISUAL_EFFECTS:
        return
    del effects[: len(effects) - MAX_TRANSIENT_VISUAL_EFFECTS]


def trim_interaction_traces(world: Any) -> None:
    """Bound the interaction trace log. Call once a tick.

    Done here rather than at the nine append sites: one call on a known cadence
    is easier to reason about than nine independently-maintained bounds, and it
    costs a length check per tick.

    `world.interaction_trace_log_limit` overrides the default, and a limit of
    zero or less means unbounded - which is what the sandbox wants, because its
    scenarios assert on traces emitted thousands of ticks earlier.
    """
    trace_log = getattr(world, "interaction_trace_log", None)
    if not isinstance(trace_log, list):
        return
    limit = getattr(world, "interaction_trace_log_limit", MAX_STORED_INTERACTION_TRACES)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = MAX_STORED_INTERACTION_TRACES
    if limit <= 0 or len(trace_log) <= limit:
        return
    del trace_log[: len(trace_log) - limit]


def emit_validation_warning(
    world: Any,
    warning_type: str,
    key: tuple[Any, ...] | str,
    message: str,
    *,
    cooldown_ticks: int = DEFAULT_WARNING_COOLDOWN_TICKS,
    actor: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Record a structured validation warning with deterministic debounce.

    Returns True when a new visible warning was emitted, and False when the
    warning was counted but suppressed by cooldown.
    """
    current_tick = int(getattr(world, "game_time", 0) or 0)
    warning_key = (warning_type, key)

    counts = getattr(world, "validation_warning_counts", None)
    if counts is None:
        counts = {}
        setattr(world, "validation_warning_counts", counts)
    counts[warning_key] = counts.get(warning_key, 0) + 1

    last_emitted = getattr(world, "validation_warning_last_emitted", None)
    if last_emitted is None:
        last_emitted = {}
        setattr(world, "validation_warning_last_emitted", last_emitted)

    should_emit = current_tick - last_emitted.get(warning_key, -cooldown_ticks - 1) >= cooldown_ticks
    if not should_emit:
        return False

    last_emitted[warning_key] = current_tick
    payload = {
        "tick": current_tick,
        "warning_type": warning_type,
        "key": repr(warning_key),
        "message": message,
        "actor_id": getattr(actor, "id", None),
        "actor_name": getattr(actor, "name", None),
        "count": counts[warning_key],
        "metadata": _stable_metadata(metadata),
    }

    warnings = getattr(world, "validation_warnings", None)
    if warnings is None:
        warnings = []
        setattr(world, "validation_warnings", warnings)
    warnings.append(payload)
    if len(warnings) > MAX_STORED_VALIDATION_WARNINGS:
        del warnings[:len(warnings) - MAX_STORED_VALIDATION_WARNINGS]

    trace_log = getattr(world, "interaction_trace_log", None)
    if trace_log is None:
        trace_log = []
        setattr(world, "interaction_trace_log", trace_log)
    trace_log.append({
        "tick": current_tick,
        "interaction_id": None,
        "actor_id": getattr(actor, "id", None),
        "action_type": "simulation_validation",
        "trace_type": warning_type,
        "metadata": payload,
    })

    return True
