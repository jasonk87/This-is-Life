# Occupied furniture and room depth

## Delivered

- Four matching pose atlases: 32 seated and 32 reclining outfit variants, preserving the existing people-art identity/order. The imagegen workflow supplied identity-preserving pose edits and a separate verified alpha extraction; no asset-pack purchase. Full prompts, original/final filenames and mode are in [the asset manifest](../assets/world32/OCCUPANCY-POSES.md).
- Furniture, real loose map items and actors share a row-depth painter order. Nearby surface stock travels with the actual table/shelf layer, rather than floating above every actor. Duplicate actor references in overlapping NPC collections render once.
- Sitting artwork uses the simulation's recorded chair anchor. Actor coordinates, spatial indexing, paths, collision, ownership, timers and saves are not changed. Real player/NPC sit handlers are covered by tests, including returning to standing.
- Sleeping NPCs on actual beds use reclining artwork. The original bed's blanket/footboard is composited over the body; no new bed or blanket object is invented. The straw pallet has its own pillow alignment.
- Attached equipment scales with the body and stays beneath the relevant furniture foreground. Seated talking/eating retains the seated body while the real speech/action determines its cue.
- Person picking follows the same furniture ordering and alpha masks, then targets the actor's unchanged logical coordinates for inspection. Fully furniture-covered body pixels no longer act as invisible hitboxes. At 1x, a face and blanket can share one 16px input cell; any visible face pixels keep that cell inspectable.
- Seated names/health bars follow the actual head. Visible physical sleepers appear in Nearby; render-disabled macro-suspended NPCs are not drawn, labeled or picked as sleepers.

## Evidence and captures

`python tools/occupancy_review.py` produces native tcod-rendered images in `artifacts/occupancy-final/`:

- `occupied-furniture-sheet.png`: explicitly staged real-action fixtures, not claimed emergent village events.
- `furniture-depth-sheet.png`: behind/beside/in-front static renderer fixtures.
- `tavern-before-sitting.png` and `tavern-player-seated.png`: disposable seeded world, normal player sit handler, unclaimed existing chair and normal FOV.
- `house-bed-action-fixture.png`: explicitly staged NPC sleep interaction on a real placed house bed, normal FOV. The capture's log labels this as a test.

`python tools/interior_review.py --output artifacts/occupancy-final/rooms --smoke` captures six unchanged seeded room layouts at 3x and 4x and exercises the real Direct3D11/tcod presentation context. The seeded tavern already contains a sitting NPC; that ordinary room capture is not staged. The 60-frame smoke completed in 0.90s on this machine (a smoke result, not a general gameplay FPS benchmark).

Baseline room images remain in `artifacts/occupancy-before/`. Captures never load/write a user save and disable remote dialogue connections.

Validation: 620 tests plus 1,320 subtests passed in the broad rendering/UI/action regression run. After the final head-label adjustment, 285 targeted tests passed, including the new label test. Compilation and `git diff --check` passed; existing tcod compatibility warnings and Git LF/CRLF notices remain.

## Boundaries and remaining work

- This is a presentation pass. No simulation source, seating rules, schedules, entity positions or saved game were modified by the implementation. Existing unrelated simulation edits were preserved.
- Player sleep currently advances the clock synchronously and clears its sleep flag before returning. A prolonged player bed animation would require a separate gameplay/time-flow change; this pass deliberately does not introduce one.
- The existing sit handler permits multiple actors to claim a chair. This renderer does not invent a reservation rule or displace/hide a claimant. The review harness now chooses an unclaimed chair; seat-contention behavior remains a simulation issue for a separate scoped change.
- The furniture atlas faces south. Furniture rotation/directional furniture poses remain future work.
- Existing floating event text records the event's world position, not an actor-linked attachment. For example, the pre-simulated tavern's `*resting*` effect can remain at its historical location while paused; this pass does not relocate history to the nearest person.
- All changes remain local and uncommitted/unpushed on the existing branch.
