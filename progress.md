# This is Life: Architecture Status

Last updated: 2026-03-22
Workspace: `C:\Users\Owner\Desktop\This is Life`

## Project Direction

The game is being shifted away from large-file, string-heavy, ad hoc logic and toward modular simulation systems.

The target architecture is:

- `data/`: declarative definitions and content catalogs
- `entities/`: actor state and class-owned identity/career behavior
- `simulation/`: world rules, progression, records, geography, and other systems
- `presentation/`: text formatting and player-facing interpretation
- `engine.py`: orchestration layer that wires systems together instead of owning all policy

The long-term goal is Dwarf Fortress style growth:

- deeper systemic simulation
- fewer hardcoded strings and one-off checks
- new features added as modules instead of by searching giant files
- future systems like anatomy, armor, childbirth, weather effects, memory, law, religion, magic, and social edge cases plugging into stable foundations

## Major Work Completed

### 1. DawnLike Sprite Foundation

The rendering pipeline was moved toward the DawnLike sheet and away from opaque glyph routing.

Completed areas:

- centralized sprite catalog in `data/dawnlike.py`
- terrain, decorations, items, animals, weather, and human sprite mappings
- renderer now uses sprite-backed map output instead of the old terrain ASCII override
- remaining gameplay-facing placeholders like corpses, traps, thicket, rotten food, and weather were pushed into named sprite mappings

Key related files:

- `data/dawnlike.py`
- `data/tiles.py`
- `data/decorations.py`
- `data/items.py`
- `data/environment.py`
- `rendering/console_renderer.py`
- `tests/test_dawnlike_mapping.py`

### 2. Entity Identity and Display Foundation

NPC/player-facing naming started moving out of scattered string assembly and into entity-owned behavior.

Completed areas:

- `NPC.get_display_name(...)`
- relationship-aware labels
- profession/title-aware labels
- family placeholder naming support
- broader use of shared display formatting in dialogue and world logs

Key related files:

- `entities/base.py`
- `engine.py`
- `tests/test_ui.py`

### 3. Presentation Layer Started

Game text is starting to move into a presentation class instead of being handwritten inside systems.

Completed areas:

- `presentation/text_formatter.py`
- initial formatter coverage for:
  - season changes
  - weather changes
  - attacks
  - deaths
  - arrests
  - grazing
  - crime reporting
  - fishing

Key related files:

- `presentation/text_formatter.py`
- `tests/test_text_formatter.py`

### 4. Career / Profession Foundation

Human job identity is no longer only raw strings floating around `engine.py`.

Completed areas:

- `simulation/careers.py`
- career tracks
- role levels
- profession normalization
- building-to-role resolution
- capability checks
- role history
- tenure tracking
- shared profession assignment path via `set_entity_profession(...)`

Entities now carry `career` state, and important spawn/job assignment logic routes through shared helpers.

Key related files:

- `simulation/careers.py`
- `entities/base.py`
- `entities/animal.py`
- `engine.py`
- `tests/test_npc_careers.py`

### 5. World / Region / History Foundation

This is the newest architectural extraction and the current foundation for future worldbuilding systems.

Completed areas:

- `simulation/history.py`
  - `Book`
  - `Event`
  - `HistoryLedger`
- `simulation/world_model.py`
  - `Building`
  - `Village`
  - `Ruin`
  - `Region`
  - `Chunk`
  - `WorldAtlas`
- `engine.py` now creates:
  - `self.history`
  - `self.atlas`
- world chunks are assigned region IDs during initialization
- village and ruin creation routes through the atlas
- building registration routes through the atlas
- authored books route through the history ledger
- helper accessors added for region and history lookups

Key related files:

- `simulation/history.py`
- `simulation/world_model.py`
- `engine.py`
- `tests/test_world_foundations.py`

## Current Architecture Snapshot

### New System Modules Present

- `presentation/text_formatter.py`
- `simulation/careers.py`
- `simulation/history.py`
- `simulation/world_model.py`

### Engine State Now Delegates To

- `self.text` -> `WorldTextFormatter`
- `self.history` -> `HistoryLedger`
- `self.atlas` -> `WorldAtlas`

Aliased engine-facing collections still exist for compatibility:

- `self.global_events = self.history.events`
- `self.books = self.history.books`
- `self.villages = self.atlas.villages`
- `self.buildings_by_id = self.atlas.buildings_by_id`
- `self.regions_by_id = self.atlas.regions_by_id`

This compatibility layer is intentional for now. It keeps existing game logic working while modules are extracted in stages.

## Verification Status

Passed locally in this workspace:

- `python -m compileall simulation\history.py simulation\world_model.py engine.py tests\test_world_foundations.py`
- `python -m pytest tests\test_world_foundations.py tests\test_dawnlike_mapping.py -q`

Current pass count from latest targeted run:

- 8 tests passed

Known environment issue:

- some test files are still blocked by an existing import problem in `runtime_compat.py`
- specifically, `from google import genai` can fail in this local environment
- this is an environment/setup problem, not a direct result of the architecture work

## Important Files To Read First

If a new agent picks this up, these are the best entry points:

- `engine.py`
- `entities/base.py`
- `presentation/text_formatter.py`
- `simulation/careers.py`
- `simulation/history.py`
- `simulation/world_model.py`
- `tests/test_npc_careers.py`
- `tests/test_text_formatter.py`
- `tests/test_world_foundations.py`
- `tests/test_dawnlike_mapping.py`

## What Still Needs System Extraction

These are the next major subsystems that still need to move out of `engine.py` and become authoritative modules.

### 1. Typed History Records

Current status:

- history exists, but events are still mostly generic

Needed next:

- typed records for:
  - births
  - deaths
  - marriages
  - migrations
  - crimes
  - hires/fires
  - wars
  - discoveries
  - weather/disaster records

Goal:

- stop treating world history as only loose event strings
- give future books, lore, memory, rumors, and chronicles structured data to build from

### 2. Region / Biome / Settlement Simulation

Current status:

- regions exist, but they are still light containers

Needed next:

- region climate profiles
- biome/resource tagging
- settlement-to-region links used by simulation
- travel/network relationships
- regional identity and lore accumulation

Goal:

- make world geography a real simulation surface instead of background map metadata

### 3. Records / Knowledge / Chronicle Layer

Current status:

- books and events exist
- NPC knowledge still works largely off event sharing inside engine logic

Needed next:

- `simulation/records.py` or equivalent
- census records
- family records
- village chronicles
- region histories
- record lookup APIs
- cleaner bridges between history facts and written artifacts

Goal:

- make “what the world remembers” a real system

### 4. Presentation Expansion

Current status:

- formatter exists, but only a subset of text uses it

Needed next:

- move more engine log/dialogue strings into `presentation/text_formatter.py`
- eventually split larger surfaces into dedicated presentation classes if needed

Goal:

- no more scattered string assembly for player-facing simulation output

### 5. Anatomy / Equipment / Needs

These are not started as proper modules yet, but they are major future pillars.

Needed systems:

- anatomy/body parts
- injury/wound handling
- armor/equipment layers
- temperature/wetness/fatigue/intoxication/contamination

Reason:

- these are required for long-term depth like dismemberment, armor coverage, pregnancy later, survival effects, and simulation-heavy edge cases

## Recommended Next Build Order

This is the recommended sequence from here:

1. Expand `simulation/history.py` into typed world records
2. Deepen `simulation/world_model.py` with richer region/settlement metadata and helpers
3. Add `simulation/records.py` for books, chronicles, census, and historical lookup surfaces
4. Keep moving event narration into `presentation/text_formatter.py`
5. Start anatomy/body system
6. Build equipment/armor layering on top of anatomy
7. Build needs/physiology system
8. Extract combat into its own rules module
9. Extract social/memory/law/reputation as formal systems
10. Build advanced systems like childbirth, religion, magic, and emergent environmental effects on top of those foundations

## Guidance For The Next Agent

Do not take shortcuts.

The user explicitly wants:

- modular systems
- deep work
- fewer giant-file edits over time
- class-based/system-based ownership
- future-proof simulation design

Preferred working style:

- take larger architectural slices
- complete them end-to-end
- keep compatibility shims when useful
- add focused tests for each new subsystem
- avoid scattering new rules back into `engine.py` unless the engine is only orchestrating

When adding a feature, ask:

- which system owns this truth?
- which module should expose it?
- how should presentation consume it?

Do not default to:

- raw strings in engine logic
- new one-off dictionaries in unrelated files
- repeated profession/name/event checks across multiple code paths

## Handoff Summary

The project is no longer only in “feature patch” mode.

It now has the beginnings of a real architecture:

- sprite catalog
- presentation formatter
- career system
- history ledger
- world atlas

The next phase is turning history, geography, and records into fully systemic foundations so future features can grow cleanly.
