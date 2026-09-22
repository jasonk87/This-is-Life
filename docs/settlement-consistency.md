# Physical economy and persistent household migration

This pass addresses the integration failures recorded against `7b2109e`. Game LLM connections remain disabled. It does not add war triggers or change combat damage, personalities, clothing, or anatomy.

## Authoritative state

- Building and personal `Inventory`/`ItemReference` objects own goods. `village.supply` is a derived view, excluding currency. The daily macro pass no longer produces, eats, spoils or exports a separate ledger of goods.
- Distant manufacturing keeps the existing real recipe/worker path and buys missing cycle inputs from actual dormant local suppliers. Public and private workplaces both pay; payroll cannot overwrite procurement payments. Active suppliers retain physical delivery tasks. Distant hunting deposits its ecology-backed output into an actual inventory. Per-item spoilage remains owned by the existing inventory tick.
- Distant meals consume carried food, a resident's home pantry, or food purchased from a real seller. Shopping transfers payment to that seller. Wells remain real renewable water sources; travelers cannot buy food from an origin market they have left.
- Local and abstract hunger/thirst advancement share a saved per-NPC clock, preventing duplicate metabolism when both dispatchers run.
- Salaries require an employer's money, including publicly managed businesses. Hourly payments are credited against that day's pay; a local/distant transition cannot grant a second full paycheck. Detached workers receive no fallback salary.
- World generation can seed starter equipment. An existing person's job change cannot create a new starter kit; additional equipment must come from existing workplace stock through trade.

## Needs and workplaces

The normal economy dispatcher refreshes actual population and inventories, derives food/recipe/construction input pressure, and calls the needs detector. Detection itself never creates or consumes goods. Demand relaxation is interval-based rather than frame-based.

The service detector handles missing industries as well as empty existing workplaces. Communities of at least eight residents request basic services; smaller settlements still surface unstaffed existing services. This is an explicit initial service-coverage policy, not a claim of deep economic specialization.

Missing-service projects can request an appropriately typed workshop even when another generic workshop exists. Housing pressure counts actual residents, including the unhoused. Homes now have explicit `housing_capacity`; old saves use a conservative interior-area fallback (one place per eight interior tiles, minimum two). This permits households larger than two and uses the same capacity for migration and expansion. Rent, property transfer and room-specific occupancy are not added in this pass.

A service notice is not an employer. NPCs and the player can take an actual advertised job; selecting a service need alone cannot fabricate a profession/workplace relationship. Incoming employment reservations consume capacity so another hire cannot silently take the same slot.

## Household journey

1. A resident must have learned an opportunity. Merchants now read local opportunity notices on both active and abstract arrivals, preserving the news they brought. Memories older than seven days are ineligible for migration decisions.
2. Before departure, the destination, current job opening/funds, a single home with household capacity, and actual map paths are validated. The job and home capacity are reserved together. Stale listings and scattered single-person vacancies cannot trigger the move.
3. Departure clears old home/work membership and wages without replacing people, clothing or possessions. Children retain their child role and family ties rather than becoming unemployed adults. Household members already traveling, jailed, incapacitated, in another settlement, or committed to a non-routine task (escorting, following, fighting, hauling, etc.) cannot be silently pulled into a new trip.
4. Visible travelers use existing body-aware, collision-aware, door-opening movement. Dormant travelers advance along actual paths using elapsed time and physical movement capability; they switch to local simulation on entering an active area. The clock does not stop because the player watches them.
5. Arrival requires the real people to reach the reserved home. Housing and the job are revalidated. All members share that home; employment is established only if hiring actually succeeds. Lost housing interrupts the move and releases reservations without deleting the people; a lost job leaves an explicit arrived/seeking-work state.
6. Travel state, reservations, routes and cooldowns survive save/load. History distinguishes departure, arrival, establishment and interruption. A failed move retains the people and their consequences.

Poor unemployed residents now attempt opportunity-based relocation rather than being sent to a map edge for deletion. The existing separate outside-world immigrant spawner is unchanged; its new people must not be counted as successful relocation of an existing resident.

## Verification and limits

New regression coverage is in `tests/test_settlement_consistency.py`: real dispatcher shortage detection, physical stock/money conservation, no phantom meals, no duplicate metabolism/pay, stale offers, shared housing, reservations, walking arrival, save/load, interruption, and opportunity transmission.

The existing 900-tick work-errand regression exposed a real integration failure when construction became more active. The pushed baseline passed under `PYTHONHASHSEED=0`; the new branch initially did not. Two assignment paths could interrupt production:

- The construction dispatcher scanned the entire population, including dormant workers, other settlements and people committed elsewhere. It now checks local availability and scopes new assignments to the actual blueprint being dispatched; it does not advance another site's crew.
- Movement briefly marks a worker idle on reaching a work station. `HaulingBehavior` interpreted that handoff as free time and overwrote `fetch_ore` with `Fetching raw_log` before the daily work policy resumed. During work hours a worker beside their current station keeps the errand. Truly free workers can still volunteer, and unemployment does not authorize interrupting an escort, fight or journey.

The original work-errand test is unchanged, including its 900-tick window. The focused run passed 93 tests plus 5 subtests after these fixes. New construction coverage includes available crews, employment, jurisdiction, sleep, travel, jail, death, existing hauls, existing construction and other commitments; both stocked and material-short sites are exercised.

Several old construction fixtures contained anonymous occupant counters without actual NPC residents; those fixtures now register real people. The remote-service fixture explicitly supplies sufficient housing to isolate industrial construction. The hourly wage fixture explicitly starts unpaid with a known metabolic timestamp. Their original behavioral assertions remain.

Career/social fixtures now fund their employers when testing satisfaction or dismissal (so an unrelated unpaid-payroll departure cannot remove the boss first), and explicitly provide the third worker slot used by the hiring relationship test. The sandbox's growth scenario also uses registered NPC residents, not anonymous occupancy counters.

The reduced month-long test now measures successful job assignments, physical output and actual tax transfers (including currency conservation). It no longer treats `coins + item counts` increasing, or a treasury balance growing despite spending, as proof those mechanisms ran. This is a correction to those tests' stated mechanism checks, **not a claim that employment or economic survival has improved**. The seed 8675309 reduced loop still ended with unemployment rising from 37 to 86 and the local treasury exhausted. Business solvency, service revenue, production cadence and ordinary purchasing need a dedicated long-run balance pass; no subsidy or money creation was added to hide that result.

### Final regression result

On September 12, 2026, the complete local suite passed **2,544 tests and 2,450 subtests**, with **zero failures, errors or skips**, in 1,149.27 seconds. This includes 62 new consistency regression cases. Python 3.14.6 on Windows, game LLM connections disabled:

```powershell
$env:PYTHONHASHSEED='0'
python -m pytest tests/ -n 2 --dist loadfile -q --tb=short --durations=10 --junitxml=artifacts/settlement-consistency-final-suite.xml
```

All 19 changed/new Python files had matching SHA-256 hashes before and after the full run. `git diff --check` and compilation checks passed. The run emitted 26,819 warnings, predominantly existing rendering deprecations; it was not warning-free. This is a local result, not a GitHub CI result for a new commit. No commit or push was made in this pass.

The unchanged `tests/test_work_errands.py` also passed all six tests under `PYTHONHASHSEED=1` after the full run (68.46 seconds). That is an additional process-seed check, not a claim of exhaustive random-seed coverage.

### Runtime observations

After the final source changes, seed 451 ran another **2,400 ordinary world ticks**, sampled every 600 ticks. All four samples retained 73 residents across the four settlements, with exact population-cache matches, zero physical-stock/summary mismatches, zero negative stacks and no resident at hunger >=90. No relocations or new buildings occurred in this four-hour window. Output: `artifacts/consistency-runtime-verified-451.json`; elapsed 88.29 seconds while the second-seed test also ran. This confirms short-window consistency, not long-term prosperity.

Measured development probes (the day/month observations below predate the final construction/work handoff fix):

- Seed 451, 2,400 consecutive ordinary world ticks: all 73 villagers retained; population caches matched actual residents; zero sampled inventory/summary mismatches, negative stacks, or hunger >=90 at the endpoint. This is four game hours, not a long-term survival guarantee.
- Two 14,400-tick ordinary-dispatch days were measured on seed 451, before and after the procurement integration. Both retained all 73 villagers. The latter sampled all four settlements every 600 ticks: all 24 samples matched physical stock, with zero negative stacks and zero hunger >=90. It completed in 806.19 seconds while regression tests were also running; that timing is not a standalone performance benchmark.
- Seed 451, 30-day reduced hourly macro sample: four houses completed, and one two-person household departed, arrived together and established employment without injecting an opportunity or forcing a destination. Seed 7 completed three houses with no relocations in the same duration; foreign job information did reach residents.
- After connecting paid workplace input procurement, the seed 451 repeat completed four houses but **no household relocations**. Final high-hunger counts were 32/35 in Oakstead, 18/19 in Cedarwick, 17/18 in Alderford and 0/4 in Briarbrook. Earlier natural migration is development evidence, not a reproducible promise for the final economy; the controlled walking/save-load tests prove the journey machinery.
- The post-procurement seed 7 repeat completed two houses with no relocations, no sampled stock mismatches and no negative stacks. High-hunger counts were 0/10 in Hazelhaven, 24/26 in Cedarwick, 21/21 in Alderford and 21/22 in Alderbrook. Both post-procurement macro seeds are reported; neither is being presented as a successful long-term survival result.
- The macro samples had substantial food stress by day 30. They omit local movement and per-tick survival/spoilage, and cannot establish normal-play famine rates. Removing calorie-for-coin shortcuts exposes resource/financial constraints; **long-term economic balance is not certified by these results**.
- Ordinary player travel was rerun: Briarbrook → Oakstead, 180 keyboard steps / 181 ticks, alive, arrival and save/load preserved, no supplied loadout, teleportation or terrain changes.

Reproduce a full dispatcher observation:

```powershell
python -W ignore tools/probe_settlement_consistency.py --mode runtime --seed 451 --ticks 2400 --output artifacts/consistency-runtime-451.json
```

Reproduce the explicitly reduced macro comparison:

```powershell
python -W ignore tools/probe_settlement_consistency.py --mode macro --seed 451 --days 30 --output artifacts/consistency-macro-451.json
```

Natural manufacturing diversification, multi-year survival, property/rent contracts, prisoner carrying, and causes of war remain separate work. No forced conflict or migration-date trigger was introduced to make a probe produce a desired story.
