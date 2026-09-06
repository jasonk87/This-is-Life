"""Every sandbox scenario still runs.

tests/test_simulation_sandbox.py runs five of the thirty-nine scenarios in the
registry. The other thirty-four were only ever run by hand, and one of them had
been raising

    AttributeError: 'World' object has no attribute '_find_nearest_rest_target'

from inside run_world_tick for long enough that nobody knew. A full test suite of
1784 passing tests said nothing about it, because nothing in the suite reached the
fatigue survival override and the scenario that did was not being run.

This is the cheap half of the fix: drive every registered scenario for a couple of
hundred ticks and require only that it does not raise. It says nothing about
whether a scenario's assertions hold - tests/test_sandbox_scenario_status.py
covers that, at real tick counts, in the slow tier. What it does catch is the
whole class of "a code path nothing else exercises has been broken for weeks",
which is what actually happened.

Two hundred ticks is enough: the crash above reproduces here, verified by putting
it back. The whole file takes about a minute.
"""

import pytest

from tools.simulation_scenarios import SCENARIOS, run_scenario

SMOKE_TICKS = 200
SMOKE_SEED = 1


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_scenario_runs_without_raising(scenario):
    """Parametrised so a failure names the scenario rather than the loop."""
    run_scenario(scenario, seed=SMOKE_SEED, ticks=SMOKE_TICKS)


def test_the_registry_is_not_empty():
    """A registry that failed to populate would make every test above vacuous."""
    assert len(SCENARIOS) >= 39, f"only {len(SCENARIOS)} scenarios registered"
