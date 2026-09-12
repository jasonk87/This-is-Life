# Wounds, scars, archery and weapon goods

This pass extends the existing body model; it does not replace regional injuries
with another health pool. Models remain disabled. Restart an already-running
game to load the code changes. No new asset packs or generated art were used.

## What the player sees

- Normal world drawing no longer calls the overhead HP-bar renderer. The pinned
  field guide shows blood reserve rather than an HP meter. Hunger/thirst remain
  separate needs. Old HP adapters/helpers remain for compatibility.
- Observable symptoms such as bleeding, limping and unconsciousness appear over
  injured NPCs. This is not an enemy blood-percentage readout.
- Human cuts, bruises, dressings, splints and healed scars use the same anatomical
  joint anchors as the modular character, including seated/reclining poses.
  Clothing hides covered skin marks. Face marks do not appear through the back
  of the head. Small marks are clearest at closer zoom.
- A bleeding impact stains the actual struck garment item. Changing into a clean
  shirt does not transfer the old shirt's stains; re-equipping the old item brings
  them back. The renderer does not mutate clothing or wound state.
- Significant healed cuts/punctures leave saved scars with their body region,
  source wound, cause and formation time. Scars survive wound-history trimming
  and do not themselves cause fresh damage. The body panel lists scar history.
  Inventory previews use the same marked character as the world.

## Archery controls and rules

Equip an owned Short Bow from `U`, carry Arrow items, then use `F` to select a
visible target. `Tab` changes targets; `Enter` or `F` commits Attack. The picker
shows ammunition, distance and recovery. Punch/Kick remain adjacent alternatives
against humans/wolves. The normal interaction menu also retains combat.

Each released shot spends one actual arrow, including a miss, and one bow
durability. Shots require range (12 tiles), a clear terrain/actor line, two
functional hands and recovery readiness. Invalid shots spend no ammunition.
Archery skill, distance, pain and arm function affect the result; recovery is
six simulation ticks. Armor and regional puncture rules still apply. The bow's
curved limbs, string and draw pose are attached to the character's hands.

Human/wolf targets retain full detailed anatomy. Other huntable animals retain
their existing legacy bodies; lethal arrows now finalize the same real carcass,
ecology and death-history transition as melee hunting. Supported NPC combat and
guard response use the same ranged attack path.

Projectile flight is presentation: damage resolves at release, not through a
continuous ballistics simulation. There are no recoverable/lodged arrow objects,
quivers, elevation, wind or moving-target interception in this pass.

A controlled fresh-archer/fresh-wolf check (100 attempts per distance, seed
20260912 plus distance, ordinary rolls) recorded 71 hits at four tiles, 68 at
eight and 46 at twelve. All 300 released shots consumed an arrow. This is a
small starting-balance check, not a claim about trained archers or moving prey.

## Real materials and production

| Product | Consumed materials | Station | Yield |
| --- | --- | --- | ---: |
| Braided Bowstring | 1 cloth | Workbench | 8 |
| Short Bow | 2 wooden planks + 1 bowstring | Workbench | 1 |
| Arrow Shaft | 1 wooden plank | Workbench | 4 |
| Iron Arrowhead | 1 iron ingot | Anvil | 8 |
| Arrow | 1 shaft + 1 arrowhead + 1 flight feather | Workbench | 1 |
| Iron-tipped Spear | 1 raw log + 1 iron ingot | Anvil | 1 |

The existing logging/milling, cloth and ore/smelting chains feed these recipes.
Carpenter and smith workplace recipes participate in existing work-completion,
procurement and export hooks. Stock targets limit finished weapon/component
accumulation. Surplus bowstrings, shafts and arrowheads can be exported while
retaining a working reserve. Missing inputs are not manufactured by a shortage
request. Existing active delivery jobs move goods locally; existing off-camera
logistics transfer actual inventory items without rendering a delivery walk.

Workshop output goes directly into workplace stock with the worker's normal
craftsmanship roll and maker identity. It no longer passes through automatic
personal equipment selection, which could swallow a crafted weapon. Player
crafting also respects batch yields, inputs and station requirements.

Bulk cloth supplies eight strings; an ingot supplies eight arrowheads. The
finished arrow's base value is eight coins, versus six for its components.
Every new weapon recipe has positive base material value added, rather than
inheriting legacy placeholder prices that made production a guaranteed loss.
Actual market margins still depend on quality, supply, demand and labor.

Bow-equipped local hunters spend arrows on real shots, approach their actual
kill, dress its carcass, and deliver meat, pelts and feathers. Turkey carcasses
yield 3–6 flight feathers. An empty quiver requires taking real workplace stock
or buying arrows at a local market; no stock means no shot. Initial hunter and
bow-outlaw loadouts receive a finite starting supply, not recurring free arrows.

## Inter-village trade

Existing traveling merchants buy actual surplus weapons/ammunition/components
from village markets and sell carried goods in another market. Both ends use
item-reference transfers and opposing money transfers: quality, maker identity
and other item state travel with the same object. They do not equip purchased
cargo. Per-visit bookkeeping prevents immediately buying back a delivery.

On-screen merchants walk near the market before exchanging these goods. Existing
off-screen journey completion performs an inventory-backed arrival exchange.
Aggregate village supply totals alone cannot create a bow or arrow. This is an
extension of existing merchants, not a new diplomacy or player caravan system.

## Boundaries

- The separate off-screen aggregate hunting/food simulation remains abstract;
  it does not simulate every arrow and carcass. This pass does not unify all
  ecological production into local physical combat.
- Non-weapon merchant goods still use the existing aggregate trade rules.
- Production uses existing workshop work/completion hooks, not a new timed
  bowyer profession with dedicated station animations.
- No laundering, scar fading, infections, dismemberment, ground blood pools or
  detailed wildlife wound sprites yet. Stains currently form at bleeding impact.
- New save fields backfill cleanly. Earlier healed injuries that were already
  discarded cannot retrospectively acquire scars.

## Verification

`tests/test_scars_archery.py` covers ammunition on hits/misses, invalid-shot
conservation, legacy animal hunting/death/carcass collection, real resupply,
scar persistence, old save fields, garment identity, pose marks, workshop
stations/batches, two-market item/money conservation and removal of normal HP
meters. Existing combat, medical, pose, economy and survival tests remain enabled.

`python -m tools.scars_archery_review` renders native captures in
`artifacts/scars-archery/`. The wound sheet deliberately sets initial cuts, then
uses real treatment supplies and elapsed healing. Its pose grid is not a placed
bed scene. The archery scene stages initial terrain/actors/equipment and uses
normal target/action input; hit rolls are not forced. The current review records
two healed scars, two consumed bandages, one spent arrow, six recovery ticks and
zero pending model tasks.

Final local run, Windows / Python 3.14, 2026-09-12:

```text
python -m pytest tests -n 4 --dist=worksteal -q --disable-warnings --tb=short --junitxml=artifacts/scars-archery/verified-full-suite.xml
2459 passed, 26825 warnings, 2449 subtests passed in 626.92s (0:10:26)
```

This is the entire suite with no exclusions. Warnings remain, but no tests
failed. The earlier complete run caught an empty arrowhead catalog cell; the
mapping was corrected rather than weakening the catalog test. The interrupted
intermediate rerun was superseded after the material-price audit. The final
run includes the icon, outside-village resupply and recipe-value regressions.

The focused archery/catalog/economy/interaction run passed 167 tests and 160
subtests. Python 3.11 syntax parsing passed for all 24 changed/new Python files;
`compileall` and `git diff --check` passed. Native wound/scar and archery captures
were visually inspected. These are local results, not a claim about GitHub CI.
