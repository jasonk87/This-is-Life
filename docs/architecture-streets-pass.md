# Architecture and street continuity — September 12, 2026

This pass continues the established village/world art direction. It extends the
native procedural architecture instead of adding a bitmap pack: roof geometry
must remain fitted to real, variable footprints and entrance positions. No new
image assets or purchases were needed. Existing generated people, furniture
and vegetation remain unchanged.

## Implemented

- Nine roof forms across 23 recognized building types: hipped houses,
  longhouses, timber sheds, cross-gabled inns, steep gables, raised workshop
  ventilation, broad shop roofs, civic pediments and stone parapets. Bakery,
  tavern, smithy, store, library, clinic, civic and residential palettes remain
  coherent. Constructed house variants, not a resident's current cash, select
  the richer/poorer residential form.
- More legible wall materials and facade details: timber bracing, masonry
  courses, workshop louvers, shop windows, arched surrounds and narrow barred
  civic windows. These are facade ornament, not additional functional openings
  or extra simulated rooms/floors. Actual door state stays authoritative.
  Room-facing plaster is quieter; exterior signs/awnings do not show inside.
- Entrance-mounted shop awnings and distinct trade symbols: bread, mug, anvil,
  timber/saw, grain, crate, book, clinic cross, civic columns, badge, bars,
  cleaver and antlers. No loose tools, products, machinery or stock is invented.
- Signs mount on the same real wall as the entrance, including side doors.
  Missing walls/doors suppress the sign. Hover/right-click resolves the visible
  sign to its actual entrance; left-click still targets the original ground
  coordinate. People and furniture retain picking precedence over signs.
- Your residential property receives a small key plaque from actual ownership
  state, and the field guide reports "Your property". Null owner IDs never
  match a missing player ID. NPC owner names, crests and private identities are
  not invented or revealed.
- Soft road shoulders, building-footing shadows, damp shoreline margins and a
  short patch of wear outside actual doors. These only modify visible outdoor
  ground appearance and require a visible neighboring feature. Grass/flowers,
  tree positions, roads, walkability, collision and ownership are unchanged.

## Boundaries preserved

The renderer never changes simulation randomness, schedules, inventories,
building data, FOV or exploration. Roof cutaways retain the previous behavior:
visible interiors are exposed along actual sightlines; roofs disappear when
the player is inside. Completely unseen buildings are not drawn. Art stays
within map/UI bounds at every zoom.

"Fenced yard size" in the generator is shared spacing, not a fence or an
exclusive lot. This pass does not convert that spacing into decorative barriers
or claim land for a resident. Black unexplored/unseen regions remain hidden.

This improves building recognition and continuity, not every remaining art
problem. Bespoke character action cycles, depth-sorted furniture/person
occlusion, occupied-bed poses, authentic placed exterior objects, and more
atmospheric lighting remain future work.

## Review and verification

```powershell
python tools/architecture_review.py --smoke
python tools/interior_review.py --output artifacts/architecture-interiors
python -m pytest tests/test_architecture_art.py tests/test_world_art.py tests/test_interiors_motion.py -q
```

All tools create disposable seeded worlds, disable remote dialogue and never
load or write saves. Street captures use normal FOV and actual entrances.
The roof sheets are clearly labeled controlled source-geometry reviews, not
screenshots that pretend to reveal hidden rooms. The property inspection image
uses the existing capture player's real property state.

- Previous captures: `artifacts/architecture-before/`
- Current streets and roof sheets: `artifacts/architecture-final/`
- Property inspection: `artifacts/architecture-final/property-inspection.png`
- Interior regression captures: `artifacts/architecture-interiors/`

121 targeted architecture tests pass, covering every form/entrance combination,
profile variation, sign placement, ownership truth, right/left-click semantics,
visibility, shoreline/threshold evidence, source purity, all zooms and UI bounds.
The native architecture smoke rendered 60 frames in 1.80 seconds (a smoke
timing, not a controlled performance benchmark).
The final combined UI/world regression run passed **568 tests and 1,320
subtests**, including the interior/exterior separation checks.

This pass is local and uncommitted. No GitHub push or simulation-code edits were
performed; preexisting unrelated changes in the checkout were preserved.
