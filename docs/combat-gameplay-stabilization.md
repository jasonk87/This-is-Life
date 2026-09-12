# Combat gameplay and stabilization

Models remain disabled by default, including independent gossip transport.
Restart an already-running game to load the changes. No new model-generated
art or paid assets were used in this follow-up.

## Playable controls

- `U`: use an actual owned axe, knife or other weapon to equip it.
- `F`: open the combat picker. `Tab` cycles visible targets, arrows select
  Attack/Punch/Kick/Examine Wounds, `Enter` or `F` commits the selected action.
  It shows the held weapon, distance, recovery and a civilian warning.
- The ordinary `E`/right-click interaction menu retains combat and treatment.
- While paused, an attempted strike spends its recovery interval through the
  real world loop. Opponents, wounds, guards and movement advance too. Invalid
  targets/range/recovery checks do not spend time. Real-time play uses the
  ongoing tick clock; picking an action suspends it until the menu closes.
- Movement pays its injury/weather cost on real ticks too. Paused walking
  advances opponents; real-time key repeat cannot bypass movement recovery.
- `I` then `B`: examine the player. `T` treats with owned supplies, spending
  ten real ticks. Treatment from the bag/context menu also spends ten ticks.

## Consequences and decisions

Wolves approach and bite humans at combat cadence rather than waiting on the
ordinary low-frequency work schedule. Injury/hunger/aggression affect retreat;
nearby actual attackers can draw their attention. Lost targets are searched at
their last seen location for a bounded interval, not followed omnisciently.

When a wolf attacks a person, witnesses remember the actual attacker, victim
and place. Nearby guards intervene; civilians escape and cornered people can
defend themselves. This uses the existing terrain/radius witness checks, even
off camera. Memory expires and a finished emergency releases the NPC's task.
Wildlife alarms do not set generic hostility toward the player.
An alarm also shares the observed animal and location with nearby guards who
can perceive the caller; it does not broadcast hidden threats across the map.

Injured NPCs can dress/splint themselves using owned supplies. Healers prioritize
incapacitated/low-blood nearby patients and use medicine skill to stabilize
them more effectively. Self-treatment is harder, and unconscious people cannot
administer their own supplies. Medical skill gains come from actual treatment.
Healers wait outside a known active attack instead of repeatedly stepping into
danger and retreating. Carrying patients remains future work.

Substantial impairment or low blood prompts recovery leave/home rest; finishing
the walk home does not clear the recovery decision. Ordinary work selection
and active interactions cannot silently overrule care. Fractional travel/work
and limb-function gating from the body slice remain in effect. Not every
abstract economic calculation is injury-aware yet, and permanent disability
adaptation/employer/family reaction systems are not part of this pass.

## Regressions found and fixed

1. **Warm-clothing overheating.** Insulation conserves heat against cold; it
   no longer generates additional heat in a comfortable room. Genuine cold
   remains hazardous, and heavy clothing still adds burden in genuinely hot
   air. The original failing mild-weather test is unchanged and passes.
2. **Wildlife alarms blamed the player.** Guard emergency targets now identify
   the observed animal, independently of player hostility and lawful arrest.
3. **Fighting a wolf earned criminal reputation.** The social history scorer
   assigns a human-violence penalty to `combat_attack`. Wildlife now has a
   distinct `wildlife_combat` record: still witnessed, remembered and shareable,
   without falsely making a rescuer notorious. Human assaults retain their
   existing incident/crime pipeline.
4. **Healers repeatedly abandoned care for an old sound.** Sound expiry was
   coupled to player movement. Sounds now expire on the simulation clock, and
   routine sound investigation does not replace medical decisions.
5. **Care and combat ended on path arrival.** Arrival no longer clears ongoing
   response/recovery decisions. Healers path to a usable adjacent position;
   they do not attempt to occupy their patient's tile.
6. **Blood recovery erased major loss overnight.** A controlled 50% reserve
   fixture reaches 58% after one supplied rest day, 74% after three, and full
   reserve after seven. Continued bleeding and unmet needs slow this further.

The full regression audit also exposed two brittle checks and an obsolete
guard expectation. The ownership check now exercises an owned workplace and
an otherwise-identical unowned positive control instead of searching source
text. The guard-alarm test now requires nearby guards to identify the wolf
and forbids hostility toward the innocent player; its old expected hostility
was the bug. The decision-explanation soak now observes its bounded public
history throughout the run, rather than expecting early decisions to survive
in the final 60-message window. Instrumentation confirmed 62 task selections,
32 actor scores and an assignment before those messages aged out. No scenario
was added to the existing known-failure list, and no test was skipped.

## Measurements, not impressions

`python -m tools.combat_balance_review` runs 100 fresh encounters of three
unaimed bites for each loadout, with the production hit/armor/wound rules.
Both body state and attacker skill are reset between encounters, so the sample
does not accidentally train one wolf across 100 fights. Seed: 20260912.

| Loadout | Attempts | Hits | Left lower leg | Right lower leg | New fractured regions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Unarmored | 300 | 218 | 16 | 15 | 0 |
| Wool and boots | 300 | 216 | 15 | 15 | 0 |

All 15 human regions were hit in each sample. Target weights are side-symmetric.
This does not establish that bites can never fracture bone: accumulated damage
can do so, and repeated-region tests cover it. It establishes that the earlier
aimed-leg demo was not a representative distribution or fracture-frequency
sample. No fracture-frequency nerf is justified by this sample alone.

## Ordinary-input encounter evidence

`python -m tools.combat_play_review` sets the initial terrain, actors, gear,
supplies and hostile wolf, then uses ordinary target/action input and real
world ticks. It does **not** aim body regions, force dice or wounds, choose
guard/healer actions, or inject recovery/death outcomes.

Current preset result (seed 117 after setup): 476 ticks; Mara survives; wolf
dies; six persistent wounds, all dressed; Elara's bandages fall from eight to
two; guard never becomes hostile to Mara; zero queued model tasks. Captures and
the machine-readable result are in `artifacts/body-combat/playable/`.

The earlier `tools.body_review` remains explicitly staged. Its fourth image
forces unconsciousness solely to inspect the pose; it is **not** an event in
Mara's staged fight. Nobody attacked while unconscious in either verification.

## Regression verification

Final local run on 2026-09-12, Windows / Python 3.14:

```text
python -m pytest tests -n 4 --dist=worksteal -q --disable-warnings --tb=short --junitxml=artifacts/body-combat/verified-full-suite.xml
2434 passed, 22997 warnings, 2436 subtests passed in 588.53s
```

This is the entire suite, including slow simulations, with no exclusions.
Four local workers use the already-installed optional `pytest-xdist` test
runner; `python -m pytest tests` is the ordinary serial equivalent. Warnings
remain; there were no test failures. GitHub's existing workflow independently
runs the serial suite on Python 3.11 after push.

The latest movement/combat/UI selection passed 176 tests. The final alarm,
ownership and decision-soak regression selection passed 73 tests and ten
subtests. `compileall`, Python 3.11 syntax parsing of 100 source files, and
`git diff --check` passed. The native combat picker and after-care panel were
visually inspected. No model connections were used.
