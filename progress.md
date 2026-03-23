# This is Life: Architecture Status

Last updated: 2026-03-23
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

## Architectural Rules For Emergent Systems

This section is the most important design guidance going forward.

If the game is going to support long-running, highly interdependent, emergent simulation, then every new feature should be placed into one of five ownership layers instead of being added directly to the engine.

### The Five Ownership Layers

#### 1. Definitions (`data/`)

Owns static authored content:

- species definitions
- item definitions
- profession catalogs
- terrain/decor data
- biome/resource templates
- relationship role labels
- building archetypes

Rules:

- definitions should be declarative whenever possible
- definitions should not contain runtime world state
- definitions should not directly narrate outcomes

#### 2. Entity State (`entities/`)

Owns identity and per-actor state:

- name
- ancestry/family links
- body/physical state
- social state
- economic state
- knowledge state
- career state
- equipment state
- long-term traits and capabilities

Rules:

- entities should own “who/what am I?” state
- entities may expose narrow helper methods around their own state
- entities should not become giant rule processors

#### 3. Simulation Systems (`simulation/`)

Owns world rules and progression:

- history
- geography
- careers
- records
- social propagation
- law/reputation
- ecology
- physiology
- combat resolution
- settlement economics

Rules:

- a system owns the truth for one domain
- systems should produce structured outcomes, not only strings
- systems should expose APIs that the engine orchestrates

#### 4. Presentation (`presentation/`)

Owns player-facing interpretation:

- log text
- UI labels
- summaries
- book text assembly
- reputation descriptions
- history/chronicle formatting

Rules:

- presentation should consume structured state/results
- presentation should not be the place where rules are decided
- avoid hand-writing strings inside systems when a formatter can own them

#### 5. Orchestration (`engine.py`)

Owns sequencing and integration:

- tick order
- calling systems
- compatibility shims
- save/load coordination hooks
- player input integration points

Rules:

- the engine should ask systems to do work
- the engine should not become the permanent home of domain rules
- when a subsystem grows, extract it instead of adding another hundred lines to engine code

### Emergence Rule Of Thumb

Emergent behavior should come from system interaction, not special-case scripts.

Preferred pattern:

1. geography creates constraints/resources
2. ecology/economy convert those into pressures/opportunities
3. entity goals/needs react to those pressures
4. social/knowledge systems spread consequences
5. history/records preserve what happened
6. presentation interprets the results for the player

Bad pattern:

- “if this exact story beat happens, print this exact line and manually assign three unrelated effects”

Good pattern:

- “a drought lowers crop yield; low crop yield raises prices and hunger; hunger increases theft risk; theft affects law, reputation, rumor, injury, and future records”

That is the level of causality the architecture should support.

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

## Target System Map

This is the recommended medium-term module layout for the simulation layer.

Not every file has to be created immediately, but new work should aim toward this structure instead of deepening the monolith.

### World Structure

- `simulation/world_model.py`
  - `WorldAtlas`
  - `Region`
  - `SettlementNetwork`
  - `Village`
  - `Ruin`
  - `Building`
  - `TravelRoute`

Purpose:

- authoritative geography, settlement, and connectivity model

### Historical Truth

- `simulation/history.py`
  - `HistoryLedger`
  - typed event/record classes
  - historical indexing by entity, settlement, region, and era

Purpose:

- authoritative truth of what happened

### Cultural / Written Memory

- `simulation/records.py`
  - `ChronicleArchive`
  - `CensusLedger`
  - `BookCompiler`
  - rumor/book/chronicle generation inputs

Purpose:

- bridge structured history into what societies preserve, distort, or forget

### Social Causality

- `simulation/social_model.py`
  - relationships
  - obligations
  - trust/fear/respect
  - factions/households
  - role expectations

Purpose:

- model why people help, betray, marry, accuse, obey, gossip, and retaliate

### Knowledge / Information Flow

- `simulation/knowledge.py`
  - witnessed facts
  - rumor propagation
  - certainty/confidence
  - source tracking
  - forgetting/distortion

Purpose:

- separate “what happened” from “who believes what happened”

### Law / Reputation / Justice

- `simulation/law.py`
  - crimes
  - accusations
  - evidence
  - punishment
  - reputation consequences

Purpose:

- convert actions and knowledge into institutional/social response

### Economy / Production

- `simulation/economy.py`
  - production chains
  - inventories at settlement scale
  - prices/scarcity
  - labor demand
  - trade routes

Purpose:

- make resources and jobs matter as systemic pressures

### Ecology / Environment

- `simulation/ecology.py`
  - animal populations
  - foraging pressure
  - seasonal food availability
  - predator/prey pressure
  - biome resource regeneration

Purpose:

- make the map a living resource system, not a static backdrop

### Physiology / Anatomy

- `simulation/anatomy.py`
  - body parts
  - wound sites
  - organ/material tags
  - pregnancy-capable anatomy later

- `simulation/physiology.py`
  - temperature
  - wetness
  - pain
  - fatigue
  - hunger/thirst
  - infection/intoxication

Purpose:

- support survival depth and meaningful physical consequences

### Equipment / Armor / Damage Resolution

- `simulation/equipment.py`
  - clothing layers
  - armor coverage
  - carried/worn item interactions

- `simulation/combat_rules.py`
  - attacks
  - hit resolution
  - wound generation
  - weapon/material effects

Purpose:

- make gear and injuries interact with anatomy instead of raw HP-only abstractions

## System Interaction Contracts

To keep these modules composable, future work should prefer these contracts:

### Systems should return structured results

Examples:

- `DamageResult`
- `CrimeReport`
- `BirthRecord`
- `MigrationOutcome`
- `TradeTransaction`
- `RumorSpreadResult`

Why:

- the same outcome can feed history, knowledge, presentation, achievements, AI reaction, and save data without re-deriving it from strings

### Systems should consume IDs/references, not fragile text labels

Prefer:

- entity IDs
- settlement IDs
- building IDs
- region IDs
- typed enums/constants where appropriate

Avoid:

- comparing loose display strings to decide world rules

### Time should be explicit

Every important systemic event should carry:

- tick/time
- location
- participants
- causal tags

This is necessary for:

- memory decay
- chronicle generation
- legal evidence windows
- pregnancy/illness/injury progression
- migration/travel reconstruction

### Cross-system bridges should be one-way where possible

Recommended flow:

- systems generate structured results
- history stores results
- knowledge ingests selected results
- presentation formats results

Avoid:

- presentation code mutating core simulation
- history code hardcoding UI behavior
- entity classes directly managing unrelated world systems

## Concrete Next Extraction Sequence

If continuing this architecture work in implementation order, the highest-value path is:

### Phase A: Typed historical records

Build:

- `BirthRecord`
- `DeathRecord`
- `MarriageRecord`
- `CrimeRecord`
- `MigrationRecord`
- `EmploymentRecord`

Why first:

- nearly every future system benefits from structured world facts

### Phase B: Records/knowledge bridge

Build:

- `simulation/records.py`
- APIs that turn historical facts into chronicles/census/book inputs
- shared lookup surfaces for “what is known,” “what is recorded,” and “what is rumored”

Why second:

- this is the backbone for lore, books, gossip, reputation, and future AI memory work

### Phase C: Social and knowledge formalization

Build:

- relationship and household ownership in a social module
- witness/rumor/certainty ownership in a knowledge module

Why third:

- emergent drama depends on information moving differently than truth

### Phase D: Anatomy + physiology foundation

Build:

- body-part model
- needs/status progression
- structured injury/wound outcomes

Why fourth:

- this unlocks deep combat, medicine, childbirth, equipment layering, and survival simulation

### Phase E: Economy/ecology coupling

Build:

- regional resources
- production/consumption chains
- scarcity-driven profession and travel pressures

Why fifth:

- this is where the world starts producing large-scale emergent behavior without handcrafted events

## Engine Reduction Checklist

When touching `engine.py`, prefer to reduce these responsibilities over time:

- direct event string assembly
- profession/business rule ownership
- region/settlement truth ownership
- knowledge propagation details
- anatomy/needs/combat internals
- ad hoc inventories/economic balancing logic
- raw dict event payload construction when a typed result object would work

The engine should eventually read more like:

1. advance time
2. update environment/ecology
3. update settlements/economy
4. update actors/needs/goals
5. resolve interactions/combat/law
6. persist facts to history/records
7. emit presentation-ready outputs

That sequencing is the desired end state.

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
