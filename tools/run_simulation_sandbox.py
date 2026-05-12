#!/usr/bin/env python3
"""CLI entry point for the developer-only headless simulation sandbox."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Support direct execution: python tools/run_simulation_sandbox.py ...
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.simulation_scenarios import SCENARIOS, run_scenario  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a deterministic headless simulation sandbox scenario.")
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS), help="Scenario name to run.")
    parser.add_argument("--ticks", required=True, type=int, help="Number of sandbox ticks to advance.")
    parser.add_argument("--seed", required=True, type=int, help="Deterministic random seed.")
    parser.add_argument("--report", help="Optional JSON report output path.")
    parser.add_argument("--log", help="Optional readable text log output path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_scenario(args.scenario, seed=args.seed, ticks=args.ticks)

    if args.report:
        result.write_json(args.report)
    if args.log:
        result.write_log(args.log)

    print(result.summary_text())
    return 0 if result.result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
