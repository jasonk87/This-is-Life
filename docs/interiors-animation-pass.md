# Interiors and basic directional animation — September 12, 2026

This continues the village art direction without changing the simulation. The
existing dark-panel/gold UI remains intact. No schedules, jobs, motives,
pathfinding, collision, ownership, stock or save formats were changed by this
pass. Existing unrelated simulation work in the checkout was left untouched.

## Implemented

- A coherent furniture atlas replaces recognized placed beds, tables, chairs,
  chests, shelves, bookcases, benches, forges, anvils, fireplaces, looms and
  noticeboards. Objects have recognizable tops, fronts and legs; quieter floor
  art shows through their transparent silhouettes.
- Furniture stays anchored to its original occupied tile. Hover/right-click
  on a protruding headboard resolves to that actual tile. Walking still uses
  the unchanged ground grid. Per-cell clipping respects FOV and map/UI bounds.
- Hearth sources are cold. Animated fire appears only when the placed tile's
  actual `is_lit` property is true. Surface items come only from positive loose
  map stock at that exact tile, never inferred from hidden building inventory.
- North/back and east/profile art for the existing 32 outfit variants, mirrored
  west profiles and retained south/front art. Profession outfits keep their
  identity across views. Existing equipment still reads actual equipment slots.
- Four-phase basic walking and work gestures, a slower idle shift, and carrying
  poses with direction-aware item placement. North-facing bodies occlude held
  items. Speech indicators sit above faces.
- Presentation-only motion history observes actual coordinate steps or render
  interpolation. A queued/blocked path alone cannot trigger walking. Teleports
  are not treated as steps; a short finishing-step interval then settles to
  idle. Player facing also respects actual directional input; work facing uses
  the active interaction target when available.
- Animation timing uses simulation ticks, not wall time; paused frames remain
  stable. Motion history is bounded, resets when worlds change/time rewinds,
  and never writes actor/save state or consumes simulation randomness.

## Deliberate boundaries

This is not a complete bespoke animation library. Basic limb shifts supplement
generated directional poses. Sleep/rest remain simple poses; bed-tucking,
chair-specific seating, elaborate work cycles, full trait-accurate faces and
directional paper-doll equipment still need further art work.

The atlas includes a cold oven, cupboard and stool for future matching placed
objects. It does not create them in the simulation. In this seeded world the
bakery has an oven work-zone standing tile but no matching placed oven fixture;
that standing tile is intentionally not filled with a fake oven. Room layouts,
wealth/ownership furnishings and physical object placement stay authoritative.

The black area outside current vision remains normal FOV, not an art defect
to conceal by revealing hidden rooms. Environment-edge and additional building
archetype work remain subsequent passes.

## Sources

The imagegen skill was used with the built-in image-generation tool. Five final
PNG sheets were checked for genuine alpha and copied unchanged into
`assets/world32`. No asset pack was purchased. The initial four directional
edits had opaque checkerboards and were rejected, then corrected through the
image tool. Full prompts, references, filenames and runtime mappings are in
[the source manifest](../assets/world32/INTERIORS-MOTION.md).

## Repeatable review

```powershell
python tools/interior_review.py --smoke
python tools/motion_review.py
python tools/visual_review.py --output artifacts/interiors-ui-check --smoke
python -m pytest tests/test_interiors_motion.py tests/test_world_art.py -q
```

Interior captures are real seeded house, tavern, smithy, bakery, library and
store rooms at zooms 3 and 4, with normal FOV. The disposable capture player is
positioned on a free floor tile. No save is loaded or written; remote dialogue
is disabled. `motion_review.py` captures the actual native renderer with clearly
labeled controlled actor states; it is not a recording of spontaneous village
events. Its GIF is a sequence of renderer captures, not edited source artwork.

- Before: `artifacts/interiors-before/`
- After: `artifacts/interiors-final/`
- Four-direction animated review: `artifacts/interiors-final/motion-preview.gif`
- UI regression captures: `artifacts/interiors-ui-check/`

Both native 60-frame smoke runs completed: interior 0.89s, general/UI scene
2.02s. These are smoke timings, not a controlled performance benchmark.
The final targeted UI/world regression run passed **447 tests and 1,320
subtests** (48 tests specifically covering this interior/motion pass).
Targeted coverage includes all four zooms, source alpha, gutter-safe atlas
extraction, FOV, UI clipping, hit testing, real stock/fire state, motion/teleport
semantics, pause stability, cache/source immutability and simulation RNG.

Development switches remain available on the in-memory world for comparison:
`world.interior_art_enabled = False`, `world.directional_art_enabled = False`,
or `world.world_art_style = "legacy"`. They are not new player UI settings.

Changes remain local and uncommitted; nothing was pushed during this pass.
