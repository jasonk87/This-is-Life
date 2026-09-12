# Embodied characters — joint poses and furniture contact

## Implemented

The existing modular person now uses a joint rig for shoulders, elbows, hands,
hips, knees and ankles. Clothing textures follow those joints. There are no new
profession costumes or replacement sleeper identities, and no new source PNGs.

- Standing and observed-movement walking retain the same body/face scale.
- Sitting bends thighs and shins; the waist meets the chair's seat surface.
  Sitting does not shrink the entire character or alter their logical position.
- Bed rest has a dedicated foreshortened supine layout, folded arms, closed eyes,
  pillow contact and the bed's original blanket/footboard over the lower body.
  Floor rest rotates the supine layout, not a standing sprite.
- Carrying uses both hand sockets and the actual carried item's catalog art.
  Gait and action intent are independent: walking no longer erases the grip.
- Chopping, hammering, preparing, eating, fighting and talking articulate wrists
  and elbows. A sitting person can talk/eat without standing or drifting off-seat.
- Equipped weapons mount at a hand, or at the belt while hands are occupied.
  An actually equipped stone axe supplies its own chopping art. Where the current
  action has no concrete tool item, its existing schematic tool cue is retained;
  it never creates/equips a tool. No imaginary food is drawn for eating gestures.
- Cloak torso, shoulder mantle and undergarment sleeves use separate mounts,
  avoiding a second pair of static sleeves during activity.
- One shared face/hair/beard/headwear composer serves every pose. All garment,
  carried-item and equipped-weapon choices participate in the frame cache key.
- The inventory preview keeps the new rig's aspect ratio.

The renderer remains read-only with respect to actors, inventory, schedules, RNG,
growth clocks, map coordinates and FOV. Drawing/picking share the same body image,
placement and furniture cover. Macro-suspended actors remain hidden. Old sprite
and overlay rendering remains available when dynamic characters are disabled.

A real transition regression was fixed: the short movement-animation grace period
could mask a seated NPC's live speech. A valid furniture attachment now prevents
that stale walking cue from outranking seated talking.

## Reproduce and inspect

Run from the repository root:

```powershell
python tools/pose_review.py --sequence
python tools/occupancy_review.py --output artifacts/embodied-characters/rooms
python tools/interior_review.py --output artifacts/embodied-characters/native-smoke --smoke
```

Outputs under `artifacts/embodied-characters/`:

- `same-person-poses-0.png` through `same-person-poses-3.png`: four animation
  phases, seven poses and four views of Elias in the same actual wool outfit.
- `same-person-poses-1-armor.png`, `same-person-poses-1-cloak.png`: the same
  identity with real owned/equipped outfit and weapon changes. Furniture stays
  front-facing because those are the orientations of the existing furniture art.
- `action-01-standing.png` through `action-08-sleeping.png`: one NPC driven through
  production movement, tree interaction, log production, source-to-stockpile haul,
  sitting, live ambient speech, activity completion/standing, and bed-rest handlers.
  The identity and equipment signature is asserted unchanged at every capture.
- `rooms/`: real sit/stand/bed actions in seeded village rooms with normal FOV,
  plus clearly labelled furniture fixtures.

The action sequence deliberately places a test clearing/tree/furniture and
relocates one NPC in a disposable seed-123 world. It then drives real handlers,
including hauling the log created by the completed tree interaction. It is a
scripted integration scenario, not a recording of spontaneous NPC decisions.
No user saves are loaded/written, and remote dialogue services are disabled.
All captures come from the native tcod renderer, not painted mockups.

## Verification

`tests/test_character_poses.py` covers unchanged identity and real equipment swaps
across poses, exact seat/pillow sockets at 1–4x zoom, articulated gait/grip, gesture
frames, back-facing item occlusion, held-item cache invalidation, actual axe art,
RNG/actor immutability, stale inventory, walk-to-sit speech and the full real-action
sequence. Existing occupancy tests cover covered-body picking, visibility, UI
bounds, macro suspension, logical interaction targets and legacy fallback.

The broader regression selection additionally covers dynamic characters, world
art, interiors, architecture, UI, inventory, repair, combat, save migration,
activity, speech, hauling and movement. Native SDL smoke completed 60 frames in
0.92 seconds; this is a smoke test, not a whole-simulation performance benchmark.

Final combined regression result: **761 tests and 1,188 subtests passed** in
102.81 seconds. The run emitted 22,973 warnings; it is not warning-free. Compilation
and whitespace checks passed. The new pose module contributes 41 test cases.

Focused reproduction:

```powershell
python -m pytest tests/test_character_poses.py tests/test_dynamic_characters.py tests/test_furniture_occupancy.py tests/test_world_art.py tests/test_interiors_motion.py -q --disable-warnings
```

## Limits and scope

This is a first articulated pixel-art rig, not full skeletal animation or cloth
physics. It uses a small set of discrete gesture phases; sit/stand and bed entry
currently switch poses without an animated approach/settling transition. The
existing front-facing furniture atlas does not provide arbitrary chair/bed
orientations. Catalog item icons are still lower-resolution than the body art.

Clothes and helmets stay on during sleep unless actual equipment state changes;
the renderer does not invent undressing. Children keep their established reduced
scale. No new cosmetic variants, autonomous grooming/fashion, gameplay routines,
save schema, purchased assets, or simulation simplification were introduced.

Changes are local on the existing branch; this pass does not commit or push.
