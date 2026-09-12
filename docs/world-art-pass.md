# World readability pass — September 12, 2026

The UI's dark panels, ivory text and muted gold borders are retained. This pass
changes presentation, not the simulation: no jobs, motives, schedules, economy,
pathfinding, collision rules or save data were simplified.

## What is implemented

- Footprint-aware roof masses, timber/plaster facades, shutters, windows,
  foundation lines, bakery awnings and distinct residential/workshop palettes.
  Taverns have a cross-gable; homes use straw strokes; smithies have slate roofs.
- Bread, mug and anvil signs are mounted beside the building's actual entrance.
  Runtime open/closed doors stay aligned with their real clickable grid tile.
- Outside, roofs cut away along visible interior sightlines. Inside a building,
  the entire roof disappears. Exterior mass can extend over unseen parts of a
  known building, but never exposes its hidden floors, occupants or stock, or
  marks them explored. Completely unseen buildings are not stamped.
- 32 human outfit variants, including matching female profession outfits,
  normalized to 32×48 in memory. People stand 1.5 logical tiles high with their
  feet anchored to their actual tile. A small gold ground marker identifies the
  player. Children have reduced scale; equipment still comes from actual slots.
- Four larger tree silhouettes, connected road shoulders, quieter grass tufts
  and flowers. Species mappings do not put apples on pear trees.
- Initial work/life cues: walking, chopping, hammering, food preparation, eating,
  carrying, talking, sitting and sleeping. Four-phase work cues follow simulation
  time and freeze when time stops. These are simple gestures/overlays, not a full
  directional animation library.
- Chimneys require an actual oven/forge/furnace work zone. Smoke requires an
  actor doing real timed work there; merely being a baker does not generate smoke.
- Alpha compositing keeps the terrain beneath people and props. All four zooms
  retain the fixed 16px interface and existing mouse-to-world coordinate mapping.
  Hover/right-click inspection picks the taller visible body and resolves to the
  actor's actual tile; left-click movement still targets the ground grid. Animals
  are explicitly excluded from the human atlas despite inheriting NPC fields.
  Taller people and trees sample the existing local-light result, including
  firelight; roof exteriors use the same ambient/season palette.

## Truth rules for activity cues

An active interaction must belong to that actor and have remaining work. Timed
job cues require an active task timer and no movement. Carried goods require the
specific item in actual inventory and a delivery/stockpile/build-site hauling
phase; walking toward a source never shows goods already in hand. Talking needs
an unexpired real ambient-speech line. Profession chooses clothing, not behavior.

## Art provenance

The character and tree sources were made using the built-in image-generation
tool and copied into `assets/world32`. Full prompts, original filenames, atlas
mapping and the rejected opaque-background attempt are in
[the asset manifest](../assets/world32/README.md). No asset pack was purchased.

The source PNGs are preserved unchanged. Pixel normalization and animation are
runtime renderer operations. Architecture, signs and ground details are local
procedural pixel art based on real building/terrain metadata.

## Review

From the project root:

```powershell
python tools/street_review.py
python tools/visual_review.py --output artifacts/world32-final --smoke
python tools/visual_review.py --live
python -m pytest tests/test_world_art.py -q
```

`street_review.py` saves matching legacy/new captures at the real entrances of
the bakery, smithy, tavern and a house. It also saves clearly labeled activity
fixtures and a winter/night lighting fixture. Street captures use normal FOV.
Both tools create disposable seeded worlds, disable remote dialogue, and never
load or write saves. The live preview can be closed normally without saving.

Output locations:

- `artifacts/world32-streets`: real entrance comparisons and activity fixtures.
- `artifacts/world32-final`: world, zooms, menus, inventory and weather captures.

Native smoke improved from 60 frames in 3.16 seconds on the first implementation
to 1.71 seconds on the final smoke run after caching/resampling fixes on this machine.
This is a short paused-scene presentation check, not a full simulation benchmark.

Tests cover alpha blending, map/UI clipping, cache recycling, original atlas
transparency, all zooms, roof/FOV behavior, actual doors, no invented activities
or goods, local light, outfit mapping, and drawing a genuinely ticking world.
The larger regression run includes UI/input, inventory, camera, seasonal color,
appearance overlays, rendering stress, architecture and ambient speech tests.
Final result: **399 tests passed, plus 1,320 subtests**; this includes 60 dedicated
world-art tests. Existing warnings remain; this was the targeted regression run,
not the full long-running simulation suite. `git diff --check` passed.

## Remaining work

The world is more legible, but this is not the finished art catalog. Furniture,
animals, many workstations and some biome assets still use the older 16px art.
Directional walking/working cycles and full trait-accurate skin, hair and faces
need further work. Job outfits are representative, not a complete clothing
paper-doll system. Farm/mine structures have not received new roof silhouettes.
Weather and lighting were integrated with the new art, not replaced with a new
weather simulation. The physical village layout is unchanged.

For renderer comparisons, `world.world_art_style = "legacy"` selects the previous
world art; `"village32"` (the default) selects this pass. This is a developer
comparison hook, not a new player-facing setting. No new runtime dependency is
required. The optional formatter used during development lives only in ignored
`artifacts/format-tools`.
