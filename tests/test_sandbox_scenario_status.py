"""Which sandbox scenarios pass, held still so it cannot drift quietly.

Thirty-three of the thirty-nine pass at 2000 ticks. The other six are recorded
below with what is actually wrong with each, because "eight are broken" decays
into "some are broken" and then into nobody looking.

The list is meant to shrink. This test fails in both directions on purpose: a
scenario that starts failing is a regression, and a scenario that starts passing
means somebody fixed it and should take it off the list.

Two kinds of problem are in here, and they are not the same kind:

* **stale expectations** - the scenario asserts on trace names the engine stopped
  emitting. The overrides were generalised into a pressure-arbitration system and
  renamed `survival_override_*`; these scenarios still look for the old
  fatigue- and cold-specific names. The behaviour underneath is correct. Verified
  by hand for the fatigue one: the tired actor walks to the shelter zone, rests,
  and clears the override. Only the words changed.

* **a warm world** - five scenarios opened with `world.ambient_temperature = -4.0`
  or similar. That field is recomputed from season, biome and time of day every
  tick, so by tick 1 they were running in a 15 degree spring and nothing cold ever
  happened. They now call `_make_it_winter`, and two of them started passing.
  Checked first that the engine does the work: in real winter
  `shelter_exposure_evaluated` fires 3000 times over 1500 ticks.

* **behaviour gaps** - every name the scenario expects is one the engine really
  can emit, so the scenario is describing something the simulation is not doing.
  These are the ones worth digging into. workshop_transformation is the clearest:
  its `complete()` needs a raw_log in the workshop input buffer, and the log never
  gets produced and hauled, so the transform never completes and no output trace
  fires.

Do not "fix" a scenario by renaming an assertion until you have checked the engine
genuinely does the thing - the rename is only correct where the behaviour is
already there.
"""

import pytest

from tools.simulation_scenarios import SCENARIOS, run_scenario

pytestmark = pytest.mark.slow  # 39 scenarios at 2000 ticks; see pytest.ini

STATUS_TICKS = 2000
STATUS_SEED = 1

# scenario -> why it fails, and which kind of failure it is
KNOWN_FAILING = {
    "cold_survival_override_runtime_soak":
        "stale expectations: wants survival_override_started/_target_selected/"
        "_target_lost/_recovered; engine emits survival_override_selected/_cleared/"
        "_arbitrated",
    "fatigue_rest_override_runtime_soak":
        "one assertion left: unavailable_traced wants actor_skipped_survival_override, "
        "which needs an override that lasts long enough for the scheduler to score "
        "against it. The sandbox replaces calculate_path with a two-step teleport, so a "
        "tired actor reaches rest and recovers almost immediately and the fatigue "
        "override is never sustained. Winter would supply the trace - measured 23 skips "
        "- but from the *cold* override, which would be the assertion passing for a "
        "reason other than its name, the same trap survival_override_arbitration was "
        "already caught in. The other three assertions were stale names and are fixed.",
    "production_task_arbitration_soak":
        "behaviour gap: blocked tasks never recover and stockpile reservations are "
        "never created in this setup",
    "routing_recovery_and_source_fallback_runtime_soak":
        "behaviour gap: the building-inventory fallback source is never selected",
    "selection_inspection_runtime_smoke":
        "behaviour gap: actor inspection payload is missing expected runtime state",
    "workshop_transformation_runtime_soak":
        "behaviour gap: no raw_log is ever produced and hauled, so the workshop "
        "transform has no inputs, never completes, and emits no output trace",
}


def _passed(scenario):
    result = run_scenario(scenario, seed=STATUS_SEED, ticks=STATUS_TICKS)
    return all(a.get("passed") for a in result.to_dict()["assertions"])


@pytest.mark.parametrize("scenario", sorted(set(SCENARIOS) - set(KNOWN_FAILING)))
def test_a_passing_scenario_still_passes(scenario):
    assert _passed(scenario), f"{scenario} was passing and now is not"


@pytest.mark.parametrize("scenario", sorted(KNOWN_FAILING))
def test_a_known_failing_scenario_has_not_been_fixed_silently(scenario):
    if _passed(scenario):
        pytest.fail(
            f"{scenario} now passes - remove it from KNOWN_FAILING.\n"
            f"It was listed as: {KNOWN_FAILING[scenario]}"
        )


def test_every_known_failing_scenario_still_exists():
    """So a renamed or deleted scenario cannot leave a stale excuse behind."""
    unknown = sorted(set(KNOWN_FAILING) - set(SCENARIOS))
    assert not unknown, f"KNOWN_FAILING names scenarios that no longer exist: {unknown}"
