# Responsive controls and calm real-time pacing

September 12, 2026. This follows the settlement-consistency work already in the working tree; that work is preserved. Game LLM connections remain disabled. No commit or push has been made in this pass.

## Causes addressed

1. The old main loop rendered before reading input, then ran up to five accumulated world updates without another input check or presentation. Expensive frames could therefore cause bursts of simulation and delayed feedback.
2. Click movement added a five-tick UI cooldown **after** the actual terrain/body recovery. Ordinary NPCs could move each tick while the player waited. Manual keys pressed during recovery were simply discarded, and holding a key depended on OS repeat timing.
3. Normal playback was ten ticks/second. Walking animation crossed a tile at twenty tiles/second, making each move a quick dart. An old save could also restore fast-forward.
4. Ambient conversation selection scored every directed pair of villagers every tick, including pairs in different settlements that could never satisfy its existing four-tile distance limit.

## Behavior now

- Normal/Calm playback is four complete ticks/second. Keys 2 and 3 explicitly select Brisk (eight) or Fast-forward (sixteen); key 1 returns to Calm. Loading or starting a game selects Calm. Pause state remains respected.
- Every input frame is processed before drawing. The loop presents the player action before running at most one complete world update. Fractional time is retained at normal frame rates; wall-clock backlog from a hitch is discarded. Simulation time advances only for updates actually executed—no skipped world events or clock jumps.
- Rendering is capped at 30 frames/second instead of an unrestricted busy loop. Walking interpolation takes most of a calm tick rather than darting in 50ms.
- The first ready arrow press moves immediately. Holding walks without the OS repeat delay. Releasing stops held movement; one early deliberate tap can remain buffered through recovery. Repeat backlogs cannot accumulate extra steps.
- Click-to-walk starts on the input frame when unpaused and ready, then uses the same recovery as manual movement. Neither mode bypasses body impairment, terrain cost or the world clock. The old extra UI cooldown is retired.
- Menus, focus loss and other non-movement controls clear held/buffered input. Held keys are not restored from a save. An open interaction menu does not allow background clicks to start walking. Paused held input cannot secretly advance turns.
- Conversation candidates come from spatial buckets covering the **same** maximum distance. All eligible directed pairs retain their scoring, personality, knowledge, relationship and deterministic tie-break rules. Tests compare selected pairs with the original exhaustive calculation. No conversation frequency, population or simulation system was disabled.

`TIME_PER_TICK` is expressed in simulated seconds per tick, independent of wall-clock playback. Work, days, wounds, healing, elections and all other tick-based rules retain their units.

## Verification

Regression coverage in `tests/test_playability.py` exercises the real event router and main-loop ordering, including an artificial multi-second hitch, press/hold/release, buffered taps, OS repeat floods, focus/menu/pause transitions, input save/load, click/manual recovery parity, immediate click response, and exact conversation selection.

The existing realtime clock test now exercises `RealtimeClock`, not a copied version of the old accumulator. The legacy broken-leg test now verifies actual injury-dependent recovery after body migration instead of requiring the removed ten-tick UI throttle. The help-layout test caught an overlong new label; the label was shortened, and its assertion was preserved.

Focused runs passed 96 tests covering controls/combat/activity/visual UI, followed by 165 UI/control tests and the final 31 movement/clock/injury checks. The full final-source suite passed **2,568 tests plus 2,450 subtests, zero failures**, in 16m44s with two workers and `PYTHONHASHSEED=0`. SHA-256 checks confirmed the 31 changed/new Python files remained unchanged during validation. The 26,819 warnings concern test helper collection and existing deprecated APIs, mostly sprite-atlas tile assignment; they are not test failures. The result is recorded in `artifacts/playability-full-suite.xml`.

### CPU sample

`tools/probe_playability.py` loads the real tileset, generates seed 451, advances ordinary world ticks, and draws at the default 3x zoom. Forty measured frames after five warm-up frames:

| Measurement | Before | After |
| --- | ---: | ---: |
| Median world tick | 24.99 ms | 14.19 ms |
| 95th-percentile world tick | 51.49 ms | 37.47 ms |
| Median console draw | 13.31 ms | 12.77 ms |

These are short CPU samples on this machine, not a claim of universal FPS or physical-key latency. The after sample overlapped focused tests. Profiling separately confirms that rejecting impossible distant conversation pairs removed most of that selection cost. The CPU benchmark excludes GPU presentation.

### Actual main loop and SDL presentation

`tools/probe_live_loop.py` creates a **hidden Direct3D11/SDL window**, loads the real art, and runs `main.start_game` with synthetic arrow press/release events. It does not edit terrain, teleport the player or supply equipment. This tests application input-to-presentation, not hardware input or subjective human play feel.

The standalone observation completed 120 presentations and 19 ordinary world ticks, retained all 73 villagers, and never ran more than one update between presentations. Median frame interval was 33.99ms; the 95th percentile was 92.72ms. Four immediately accepted key events reached presentation in 121.35, 54.26, 72.31 and 51.77ms. The earlier concurrent observation had a 130.82ms first event. These results still show occasional heavier frames; this pass does **not** claim every rendering hitch is eliminated.

The final-source recheck after the full suite again completed 120 presentations, 19 ticks, at most one tick between presentations, and all 73 villagers alive. Median frame interval was 34.10ms and the 95th percentile was 80.53ms; accepted synthetic key events reached presentation in 106.63, 57.40, 62.44 and 44.70ms. See `artifacts/playability-live-loop-final.json`.

Artifacts are under `artifacts/playability-*.json` and associated `.prof` files. Reproduce the standalone presentation check:

```powershell
$env:PYTHONHASHSEED='0'
python -W ignore tools/probe_live_loop.py --frames 120 --output artifacts/playability-live-loop-standalone.json
```

Restart the game to load the changes. Start with key **1** (Calm), hold/release the arrow keys, then compare left-click walking. Injured legs and difficult terrain should still slow travel; they should not turn into ignored controls.
