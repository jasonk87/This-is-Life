# Refactor Follow-Up Status

## Purpose

This document tracks the follow-up work needed after the large runtime compatibility / entity-state / NPC-work / UI-queue refactor.

The goal is to turn review feedback and architecture discussions into a concrete, staged execution plan instead of leaving them buried in PR threads.

---

## Current State

### What landed

- Runtime compatibility adapters for optional dependencies.
- Nested entity state objects (`social`, `economic`, `schedule`, `combat`, `physical`, `knowledge`).
- Command-based work sub-task execution.
- Incremental occupancy/spatial indexing.
- Simulation-driven UI request queueing.
- Save/load hardening around generator noise pickling.

### What is working

- The refactor is test-covered and the headless compatibility path is functioning.
- Save/load works in the compatibility environment.
- UI request flows now close trade text input consistently.

### What still needs follow-up

The refactor improved behavior, but it also concentrated too many responsibilities in a few large files:

- `engine.py` remains a monolith and now owns simulation, work sub-task commands, world generation, UI request emission, and many integration boundaries.
- `main.py` still owns the concrete application of queued UI requests and several interaction helpers.
- `save_manager.py` still relies on broad pickle-based persistence.
- `tests/test_main.py` is carrying too many unrelated concerns.

---

## Current Risks

### 1. Large-file coupling

`engine.py` is still the highest-risk file for regressions and merge conflicts.

### 2. UI request boundary compatibility

The UI queue now uses typed request objects in the shared dispatcher. A small compatibility shim still accepts older queued dictionary payloads at the boundary so existing saves or tests do not break abruptly.

### 3. Persistence remains implicit

Save/load currently works, but the system still depends on pickling a large runtime object graph with limited structure or migration strategy.

### 4. Compatibility layer creep

`runtime_compat.py` and `tcod_compat.py` should stay narrow adapters, not grow into partial reimplementations of third-party libraries.

### 5. Test concentration

`tests/test_main.py` is oversized and mixes multiple subsystems, which makes failures harder to reason about.

---

## Follow-Up Roadmap

## Phase 1: Extract boundaries without behavior changes

### Goal

Reduce the size and blast radius of `engine.py` without changing gameplay behavior.

### Tasks

- [x] Extract completed work sub-task command classes into a dedicated module.
- [x] Extract `WorldGenerator` and related generation helpers into a dedicated module.
- [x] Extract UI request types/helpers into a dedicated module shared by engine and main-loop code.
- [ ] Keep `engine.py` focused on world orchestration instead of adapter and command definitions.

### Exit criteria

- No gameplay behavior changes.
- Existing tests continue to pass unchanged or with only import-path updates.
- `engine.py` shrinks materially.

---

## Phase 2: Type and formalize UI requests

### Goal

Replace ad-hoc UI request dictionaries with explicit request objects.

### Tasks

- [x] Introduce typed request objects (e.g. `OpenDialogueRequest`, `CloseDialogueRequest`, `OpenTradeRequest`, `CloseTradeRequest`).
- [x] Update `World` request emitters to construct typed requests.
- [x] Update `main.apply_ui_requests` to dispatch on typed request objects instead of raw strings.
- [x] Add focused tests for request application and invalid request handling.

### Exit criteria

- No raw `"type"`-based request dispatch remains in the core typed dispatch path. Legacy dictionary payloads are normalized once at the UI boundary.
- Engine/UI boundary is easier to refactor safely.

---

## Phase 3: Harden persistence

### Goal

Move from "pickle the whole world" toward a clearer persistence boundary.

### Tasks

- [x] Add explicit save format version metadata.
- [ ] Centralize serialization exclusions for runtime-only objects.
- [ ] Decide whether the short-term path remains pickle-based or moves toward an explicit save model.
- [ ] Add regression coverage for versioning and migration behavior.

### Exit criteria

- Save/load no longer depends on implicit runtime object behavior alone for version detection.
- Persistence changes are testable in isolation.

---

## Phase 4: Split the oversized tests

### Goal

Make tests map more clearly to subsystems.

### Tasks

- [ ] Split `tests/test_main.py` into subsystem-focused test modules.
- [ ] Separate UI request tests, save/load tests, trade flow tests, occupancy/pathing tests, and interaction tests.
- [ ] Keep `test_main.py` only for genuinely top-level integration coverage.

### Exit criteria

- Failures point to a subsystem instead of a catch-all file.
- Follow-up work can be reviewed in smaller pieces.

---

## Near-Term Recommendation

If only one follow-up slice is started immediately, do this:

1. Extract `WorldGenerator`.
2. Extract the work sub-task command registry/classes.
3. Add a dedicated UI request module.
4. Split out save/load and UI request tests from `tests/test_main.py`.

This is the highest-leverage path because it reduces future review friction without forcing more gameplay behavior changes.

---

## Working Agreement for Future PRs

- Prefer extraction and boundary cleanup over adding more behavior to the existing monolith.
- Keep compatibility adapters intentionally narrow.
- Avoid expanding raw dict-based contracts when typed boundaries are feasible.
- Land follow-up work in small slices with subsystem-specific tests.

---

## Status

### Current recommendation

**Current extraction progress:** `WorldGenerator`, shared UI request helpers, and work sub-task commands now live in dedicated modules. UI requests now use typed request objects in the shared dispatcher; the next actionable slice is persistence hardening or further `engine.py` boundary extraction.

### Owner

Open follow-up work.

### Last updated

March 19, 2026.
