# Interaction Layer

This project utilizes a unified interaction layer to resolve standard spatial actions across all entity types, conforming to the `NO PLAYER MAGIC. NO NPC-ONLY MAGIC.` doctrine.

## Doctrine

1. NO PLAYER MAGIC.
2. NO NPC-ONLY MAGIC.
3. INPUT CHOOSES INTENT.
4. RESOLVER OWNS REALITY.

The player and NPCs use exactly the same intent shape (`ActionIntent`) mapped via the `InteractionResolver`. If an intent produces an effect, logs a trace, or fires a cue, it is invariant to whether a human user requested it, a procedural AI resolved it, or the headless sandbox dispatched it.

## Architecture

### ActionIntent
A stateless request to mutate the world. Contains `actor_id`, `action_type`, target properties, and `payload`. Player input controllers and NPC AI brains should be constructed to synthesize these rather than manually mutating world state.

### ActionResult
The final or partial outcome of an `ActionIntent`. It captures whether the action succeeded, why it failed, what animation cues (`cues_to_fire`) represent the effect visually, and traces for debugging logic (`traces_to_log`).

### ActiveInteraction
Persistent or multi-tick actions (e.g., `chop_tree`) are modeled as `ActiveInteraction`s. The `InteractionResolver` retains these and ticks them. They possess a rigorous contract:
- `can_start`: Evaluated immediately upon intention registration.
- `can_continue`: Evaluated tick-by-tick to aggressively enforce spatial constraints (e.g. target deleted, actor moved out of range).
- `advance_tick`: Performs intermediate progress logic, issuing partial cues/traces.
- `complete`: Emits final mutations (transforming the tree to a stump and dropping logs).
- `cancel`: Cleans up state when `can_continue` fails.

### InteractionResolver
The stateless engine layer that accepts intents, spins up active interactions, advances them, and logs consequences.

## Action Scope

This pass implements a small foundational set of actions:
* Instant: `open_door`, `pickup_item`, `sit_on_chair`, `sleep_in_bed`
* Persistent: `chop_tree`

## Implementation Steps Ahead

*   Future UI hooks will create intents rather than calling methods on `engine.py`.
*   Future NPC task implementations will synthesize intents at their execution boundary.
*   More intricate mechanics (e.g., combat, hauling) will migrate onto this pattern in due course.
