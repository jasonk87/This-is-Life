# Dynamic characters — first functional round

## What changed

The world renderer now assembles a person from separate directional parts: persistent face, skin, eyes, build, hair, beard, and actual equipment. Profession does not select a face or costume. Eight base faces, four haircuts plus bald, six hair palettes, and four facial-hair shapes provide the initial vocabulary. This is a modular foundation, not a claim that every possible character is uniquely recognizable yet.

Image-generation skill usage supplied the separable raster parts. Eight canonical atlases are saved under `assets/world32/dynamic-*-v1.png`; [the asset manifest](../assets/world32/DYNAMIC-CHARACTERS.md) contains exact prompts, original/selected paths and built-in mode. Sources retain genuine alpha; runtime fitting/recoloring never modifies the PNGs. No pack was purchased.

The renderer retains four directions, observed-movement gait, real action cues, equipment occlusion, lighting, FOV and existing furniture picking. It does not change actor coordinates, navigation or schedules. Every visible state participates in the composite cache key, so changing clothes or grooming appears on the next draw, including while paused.

## Equipment and controls

- Existing tunic, jerkin, breastplate, cloak, hood and helmet have wearable layers.
- Six new craftable items: wool shirt, wool cap, linen trousers, wool trousers, leather boots and leather shoes. Recipes use existing cloth/leather/workstations. Legs and footwear participate in equipment utility, insulation, swapping, and existing combat/drop paths.
- NPCs use their existing concrete item references, including retaining the same object when unequipping or dropping it. Existing upgrade behavior can choose useful owned footwear/trousers; no random fashion scheduler was added.
- Newly generated villagers receive one real starter outfit, preserving already-equipped items and preferring suitable possessions already in their inventory. The choice is independent of profession and does not consume the world-generation RNG. This initialization never runs on load or ordinary ticks and never replenishes removed clothes.
- `U`: inventory. Select a carried garment and press `Enter` to equip it. The current-wear preview uses the same character rig as the world. New items have matching menu thumbnails.
- `S`: shave; `T`: trim to a short beard, while the inventory is open. Requires a carried/equipped stone knife and rejects dead/sleeping actors or a trim longer than current hair. Grooming is an explicit immediate action; timed barber/work animations are not implemented.

Player equipment still uses the pre-existing item-key armor dictionary (NPC gear is instance-bound). This pass does not implement per-instance garment dye, a full player equipment-instance migration, or a new unequip-only UI. Existing player repair/swap and inventory-transfer bookkeeping remain a separate limitation of that legacy system.

## Identity, time and saves

New identity fields resolve from the saved actor ID without RNG draws and are then persisted by the appearance system. Old nested Appearance/Equipment state is backfilled without rerolling existing hair/skin traits. Old `hairstyle="none"` meant no extra overlay on a base sprite; it now gets the natural short cut. Explicit `bald` remains bald.

Beard length is saved in game days with a last-update tick. The world checks hourly and handles time jumps, including distant macro-suspended villagers; drawing and repeated paused frames never grow hair. Stages are stubble at 2 days, short beard at 7, full beard at 21. A trimmed mustache retains its shape. Clock rewinds do not double-count elapsed growth. These are initial tunable game pacing thresholds, not a biological model.

Automatic growth defaults to adult male NPCs and adults already carrying facial hair; an explicit `beard_growth_enabled` flag overrides it. Children do not grow beards and dead actors stop. The current player model has no gender/age selection; a beardless unspecified player does not automatically gain beard growth. Character-creation customization is not added here.

Loaded worlds get the layered appearance and time migration, but **do not receive free new clothing**. Unequipped people display a quiet linen underlayer; trade/craft/equip real clothing to replace it. Restart the application to load new art. A new world is only needed to see the new starting outfits.

## Deliberately unfinished

The provisional seated/bed rig described by this first pass has now been replaced by the [embodied-character pose pass](embodied-characters-pass.md): articulated joints, furniture contact sockets, shared identity heads and held-item mounts. Floating `*resting*` event text is still not proof of a current furniture attachment.

No autonomous grooming/fashion preferences, long-hair growth, aging faces, wounds/scars, garment layering over armor, gloves, or per-item dye system yet. The straw-hat source row is reserved; it is not an obtainable item. Adding more art does not by itself create an inventory item or an AI purpose.

## Verification and reproducing captures

`python tools/character_review.py --world`

Produces native tcod captures in `artifacts/dynamic-characters/`:

- `identity-fixture.png`: deliberately selected faces/hair/skin wearing the same clothes.
- `wardrobe-fixture.png`: one NPC, actual owned-item swaps, all four directions.
- `beard-growth-fixture.png`: one person advanced through 0/2/7/21 game days.
- `village-tavern.png`, `village-house.png`, `village-street.png`: a disposable seed-123 world, normal FOV, unmodified villagers' routines. The player is positioned only to inspect these places.
- `inventory-wardrobe.png`: a clearly staged player inventory with actual added/equipped items to exercise the UI. No user's save is opened or written.

`python tools/interior_review.py --output artifacts/dynamic-characters/interior-smoke --smoke` also verifies native SDL rendering. The observed run rendered 60 frames in 1.10 seconds; this is a smoke test, not a performance benchmark.

Focused regressions cover deterministic identity, cache invalidation, directional/face differences, genuine alpha, both boots retained in atlas extraction, real owned equipment, starter-outfit idempotence, grooming tools/input, growth/save clocks, legacy migration, sleeping/dead/child exceptions, distant actors, and equipped footwear entering the existing death-drop path. Existing world-art, occupancy, inventory, UI, combat, repair and save-migration suites are also exercised.

Final combined result: **737 tests passed and 1,320 subtests passed** in 91.38 seconds. The run reported 19,156 warnings (not treated as failures); it is not claimed to be warning-free. Compilation and `git diff --check` also passed.

All changes remain local on the current branch; this turn does not commit or push.
