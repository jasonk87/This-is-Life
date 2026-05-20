"""Lightweight validation and warning aggregation for autonomous simulation systems."""

from __future__ import annotations

from typing import Any

DEFAULT_WARNING_COOLDOWN_TICKS = 120
MAX_STORED_VALIDATION_WARNINGS = 500


def _stable_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    return dict(metadata or {})


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
