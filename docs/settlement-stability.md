# Settlement gameplay stabilization

Starting baseline: `328bb4a` (wounds, archery, weapon production).
This pass closes and verifies travel, local government, public employment,
alive-only bounty contracts, and offscreen construction. It does not replace
the simulation with visual presets or add any LLM dependency. All probes run
with both LLM connection flags disabled.

## Player entry points

- Read the local noticeboard. A destination row + Enter marks that town's
  actual square coordinates in the field guide. Travel remains ordinary
  walking; arrival messages and named settlements make crossing legible.
- Read the civic row for local officeholders, tax rate, and the next election.
  Press R at the board to register in that town. Registration determines where
  the player can stand; an incumbent cannot move registration mid-term.
  Holding office in one town does not authorize governing another.
- Enter on an employment row now accepts the vacancy. It reserves a real
  worker slot; daily wages debit the employer, including partial payment when
  funds are insufficient. The existing work-performance/attendance rules remain.
  NPC visitors read the board in the town they are visiting; exhausted or
  missing boards clear stale job-seeking errands rather than leaving them stuck.
- Enter on a witnessed wanted notice reserves its reward from that town's
  treasury. Find the person using the last public report, interact next to
  them to Request Surrender, and escort them to the issuing sheriff office.
  Deliver Prisoner performs actual jail intake and pays once. Death, a guard's
  independent arrest, or losing the escort closes/refunds the contract.

## Consistency fixes

### Jurisdiction and persistence

Each Village owns one PoliticsTracker. `local_offices` is a compatibility view
of its authoritative holders; `World.politics` views the current jurisdiction.
Daily elections, taxes, salaries and warrants explicitly visit each settlement.
Voters and candidates are local residents, plus the registered player.
Older village/world records migrate on load, once. Saving in the countryside
does not replace an existing town's government with a neutral fallback record.

### Physical construction and economy

Placement now checks the actual archetype footprint/yard and chunk boundaries.
Completed rural expansion stays registered to its owning village and atlas,
and global-coordinate building lookup finds it outside the original chunk.
Public and NPC-funded service workshops open as their needed operational
business (for example a carpenter shop), enabling ordinary vacancies/production.

Registered offscreen settlements procure actual ItemReference objects from
local stores, paying the supplier from the owner or public treasury. Construction
does not create materials from a stock counter. Abstract woodcutters now use
the existing real tree-harvesting command, producing logs, leaving stumps and
regrowth timers, and degrading their equipped tool. Stock targets limit harvest.

Abstract exports cannot exceed available, unreserved surplus. The old fixed
ten-unit shipment could make stock negative. Trade's diplomatic benefit is
limited to one bonus per settlement pair per day, not one per commodity.
The wider aggregate economy still has abstractions; this is not a claim of
full local/offscreen item or ecology parity.

### Wildlife purpose

Ordinary wolves no longer spawn already hostile to the player at zero hunger.
That flag bypassed their prey/desperation decisions and stopped ordinary
travel probes through incapacitation. Existing hunting, desperate predation,
retaliation and body damage remain. Bite damage and injury consequences were
not reduced. Dire wolves/bears keep their existing defaults. Existing saves'
already-hostile individual wolves are not forcibly pacified.

### Regression fixtures

Local-government fixtures now place their voters, guards and buildings in the
same settlement instead of relying on world-global authority. The wolf-hit
fixture controls the body system's actual accuracy roll. The fresh-world test
cache restores both entity and object ID allocator state as well as RNG state;
otherwise later births/construction depended on which tests ran previously.
Production save-loading ID reservation behavior is unchanged.
Noticeboard errand fixtures now use independent seeded worlds and residents
of the tested town. Separate failing-before/fixed-after cases cover visitors
being redirected to a home-town board and the last vacancy disappearing.
The career fixture's mock player also obtains a real allocated ID, preventing
an id-1 collision with the first NPC in a fresh test worker.

## Reproducible evidence

Final release check on Windows / Python 3.14.6: **2,482 tests passed,
2,449 subtests passed, zero failures** (723.32 seconds). This includes the
noticeboard errand fixes and the 23 new settlement-loop test cases. The two
travel probes below were rerun successfully after those fixes. Local JUnit
report: `artifacts/settlement-stability/release-full-suite.xml` (not committed).

```sh
python -m pytest tests/test_settlement_playable_loops.py -q
python -W ignore -m tools.probe_settlement_loops travel --seed 451
python -W ignore -m tools.probe_settlement_loops remote --seed 451 --days 120
python -m pytest tests -n 4 --dist=worksteal -q --disable-warnings --tb=short
```

The travel probe uses actual keyboard movement, door interactions and world
ticks, without teleporting, removing NPCs, modifying terrain or supplying gear.
Seed 451: Briarbrook to Oakstead, 180 walking steps / 181 real ticks.
Seed 7: Hazelhaven to Alderbrook, 181 walking steps / 182 real ticks.
Both travelers remained alive, with destination/save-load persistence verified.
Native tcod renders capture
arrival and the destination noticeboard under `artifacts/settlement-stability/`.
The optional `--prepared` flag is an explicitly supplied expedition fixture,
not evidence for an ordinary starting inventory.

The 120-day remote probe advances the actual hourly/daily macro entry points,
not every local pathfinding tick. It does not force resources, relations,
construction, staffing or outcomes. Seed 451 results:

| Settlement | Buildings, start → end | Residents, start → end |
| --- | --- | --- |
| Oakstead | 17 → 20 | 34 → 46 |
| Cedarwick | 17 → 20 | 18 → 20 |
| Alderford | 16 → 18 | 17 → 22 |
| Briarbrook | 17 → 17 | 4 → 4 |

Eight completed buildings: seven houses and a warehouse, between days 8–26.
No negative supply observations. Three later housing projects were waiting for
materials at day 120. The new warehouse remained unstaffed; do not describe
this natural soak as proof of an autonomous new manufacturing business.

Separate controlled tests establish both public and private
need → valid site → real material/payment transfer → completion → staffing →
input-consuming production. Public projects post a vacancy and hire; private
projects activate their owner as a worker. They supply the initial shortage,
funds and materials explicitly, without forcing the site, hire or output.
Other tests exercise independent elections/taxes, player office access,
noticeboard keyboard entry, wages, migration, contract escrow/save-load,
refunds, jail intake and an actual multi-tick walking escort.

## Honest remaining limits

- Zero natural wars in the 120-day run. Fixing repeated trade bonuses did not
  establish a satisfying natural conflict rate. Conflict motivation/tuning
  remains separate work; there is no forced war timer in this patch.
- Contracts are alive-only, with voluntary or injury-enabled surrender.
  Unconscious people cannot walk an escort; carrying, restraints, courts and
  dead-or-alive terms are not implemented here.
- Two successful generated-world routes prove those routes, not universal
  connectivity/safety for every seed, destination or injured traveler.
- Native UI captures and deterministic input probes do not replace extended
  human playtesting. Player succession, mounts, craft teaching, deep culture
  and other missing systems from the inventory are outside this stabilization.
