# Headless Simulation Sandbox

The simulation sandbox is a developer-only validation harness for running small,
deterministic slices of the game without opening a graphics window. It is meant
for Codex, Jules, and human developers who need to validate actual game behavior
across systems such as construction, hauling, hunting, and settlement growth.

It is **not** player-facing UI and it is **not** a replacement for unit tests.
Use it as a thin behavior trace layer over existing engine systems when a change
needs evidence that actors, resources, claims, and world state moved through the
expected causal chain.

## How to run

From the repository root:

```bash
python tools/run_simulation_sandbox.py --scenario construction_basic --ticks 500 --seed 123
```

Optional report and snapshot files:

```bash
python tools/run_simulation_sandbox.py \
  --scenario delivery_basic \
  --ticks 500 \
  --seed 123 \
  --report out/sim_reports/delivery_basic.json \
  --log out/sim_reports/delivery_basic.log

python tools/run_simulation_sandbox.py \
  --scenario construction_basic \
  --ticks 500 \
  --seed 123 \
  --snapshot out/sim_reports/construction_basic.png \
  --overlay claims,paths,buildings,npcs,blueprints,chunks,interactions
```

Use periodic snapshots when inspecting movement or layout transitions:

```bash
python tools/run_simulation_sandbox.py \
  --scenario delivery_basic \
  --ticks 500 \
  --seed 123 \
  --snapshot-every 100 \
  --snapshot-dir out/sim_reports/delivery_basic_snapshots \
  --report out/sim_reports/delivery_basic.json
```

The sandbox disables LLM/Ollama paths in scenario setup, uses deterministic
seeds, and does not require rendering.

## Available scenarios

- `construction_basic` — creates a deterministic village, places a workshop
  construction blueprint, provides materials, drives a laborer through hauling
  and construction work, and checks completion, dimensions, owner/requester,
  settlement, claim, variant, overlap, and chunk-boundary preservation.
- `delivery_basic` — creates a source building with goods, a destination
  workplace needing goods, posts a delivery task, has a laborer claim it, and
  verifies pickup, carrying, deposit, completion, and inventory timing.
- `hunting_food_chain` — creates regional deer population, manifests wildlife,
  assigns a hunter to reachable prey, verifies prey death, single ecology
  population decrement, meat carrying/deposit, and butcher processing when
  supported by existing systems.
- `settlement_growth` — creates housing pressure, asks the settlement growth
  planner to expand, and verifies land selection, claim creation, blueprint
  placement, no overlap, and no orphan claim.

## How to read output

The CLI prints a readable summary:

```text
SCENARIO: construction_basic
SEED: 123
TICKS: 500
RESULT: PASS

KEY EVENTS:
- tick 0: scenario started
- tick 0: construction site created
- tick 2: construction material deposited

FAILURES:
- none
```

When `--report` is provided, the JSON output has this shape:

```json
{
  "scenario": "construction_basic",
  "seed": 123,
  "ticks": 500,
  "result": "PASS",
  "assertions": [
    {"name": "blueprint_created", "passed": true}
  ],
  "events": [
    {"tick": 0, "event_type": "scenario_started"}
  ],
  "artifacts": {
    "snapshot": "out/sim_reports/construction_basic.png",
    "snapshots": ["out/sim_reports/construction_basic_snapshots/construction_basic_000100.png"]
  }
}
```

Events include the tick, event type, optional actor, location, target,
success/failure, reason, and metadata. Assertions are explicit pass/fail checks
with clear reasons. `artifacts` appears when snapshots are requested.


## Visual snapshots

Snapshots are lightweight top-down debug maps for developer and agent
observability. They are not the game renderer, do not use tcod, and do not open a
window. PNG output is written by the sandbox when possible; text snapshots are
available as a fallback by using a non-`.png` path or when PNG writing is not
available.

The renderer is asset-aware in a deliberately simplified way: it uses existing
DawnLike mapping tables (`HUMAN_SPRITES`, `PROFESSION_SPRITES`,
`ANIMAL_SPRITES`, `ITEM_SPRITES`, `WORLD_TILE_SPRITES`, and
`WORLD_DECORATION_SPRITES`) to choose stable colors, glyphs, and badges for
terrain, roads, walls/floors, furniture, blueprints, buildings, NPCs, animals,
and items/material piles. It does **not** attempt full game rendering, lighting,
FOV, animation, or camera work.

Snapshot options:

- `--snapshot PATH` writes the final world state at the end of the run.
- `--snapshot-every N` writes periodic snapshots every `N` ticks.
- `--snapshot-dir DIR` is required with `--snapshot-every` and receives periodic
  files named like `construction_basic_000100.png`.
- `--overlay claims,paths,buildings,npcs,wildlife,blueprints,chunks,items,interactions,labels`
  selects the layers to render. If omitted, all default overlays are enabled.

Overlay legend:

- `.` terrain/background
- `=` roads
- `B` buildings
- `C` construction blueprints and footprint edges
- `c` land claims/reservations
- `N` NPC positions
- `W` wildlife positions
- `i` item/material pile
- `a` anchor/interact/workstation tile
- `x` blocked interaction/door marker
- `*` delivery/construction paths and destinations
- `|` / `-` chunk boundaries
- `!` path-failed or assertion-failed markers when a location is known

Codex/Jules should attach or inspect snapshots when investigating placement,
pathing, construction, claim, chunk-boundary, delivery, or actor-location bugs.
Snapshots are especially useful alongside JSON reports because the report says
what assertions passed or failed while the image/text map shows where the
relevant actors and world objects were.

### NPC readability rules

Snapshots improve NPC readability through compact metadata rather than layered
character composition. Body color/shape primarily communicates adult/child and
male/female where that metadata exists. Profession identity comes from
whole-body profession sprite mappings when available, a small role badge, a
short name label for a limited number of important/early NPCs, and a carried
item/tool indicator when practical.

To avoid label soup in taverns and crowded interiors, the renderer caps compact
labels and always keeps crowded scenes readable through positions and badges.
Future metadata can add relationship, social class, faction, injury,
fame/notoriety, and focus/hover detail without requiring a full composition
system.

### Blueprint and interaction inspection

Use the `blueprints`, `claims`, and `interactions` overlays together when
checking layout bugs. They show blueprint footprints, construction reservations,
anchor/interact/workstation tiles, and blocked doors/interactions where that
state is present in the world model. This is useful for validating room
usability, construction placement, chunk-boundary safety, and unreachable
stations.

## Asset preview workbench

Use `tools/asset_workbench.py` to export focused preview PNGs and print metadata
without launching the game:

```bash
python tools/asset_workbench.py --preview-character --gender female --profession Blacksmith
python tools/asset_workbench.py --preview-blueprint butcher_shop
python tools/asset_workbench.py --preview-animal deer
```

Each command writes a PNG (defaulting to `out/asset_previews/...`) and prints a
JSON metadata summary with the asset keys/codepoints used. Use `--output` to
choose a specific path.

Current limitations: the game does not have true layered character composition.
The workbench and sandbox previews do not compose hair, beards, armor, held
weapons, animation, lighting, or FOV. Future work can add richer metadata
badges, focus panels, or real layered sprites after the underlying game renderer
supports those concepts.

## How Codex/Jules should use it

1. Read [`docs/SIMULATION_DOCTRINE.md`](SIMULATION_DOCTRINE.md) before changing
   simulation behavior.
2. Run focused unit tests for the code you changed.
3. Run the scenario most closely related to the changed behavior.
4. Save a JSON report for non-trivial behavior changes, for example:
   `--report out/sim_reports/<scenario>.json`.
5. Add `--snapshot` or `--snapshot-every` when visual placement/pathing/layout
   evidence would make the behavior easier to inspect.
6. Treat a failed assertion as useful evidence. Do not fake success; either fix
   the underlying system or report clearly why the existing system could not be
   driven in that scenario.

## How to add a scenario

1. Add a `run_<scenario_name>(seed: int, ticks: int) -> ScenarioResult` function
   in `tools/simulation_scenarios.py`.
2. Use `_create_headless_world()` and `_create_village()` where possible so the
   setup remains deterministic and headless.
3. Drive existing engine methods instead of rewriting the system under test.
4. Emit `SimulationTrace.event(...)` calls for important state transitions.
5. Add explicit `trace.assert_check(...)` checks for success and failure
   reasons.
6. Register the scenario in `SCENARIOS`.
7. Add focused tests in `tests/test_simulation_sandbox.py`.

Keep scenarios small and honest. If an existing system is too hard to drive,
record the failed assertion and reason instead of synthesizing a passing state.
