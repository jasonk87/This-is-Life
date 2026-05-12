import json
import tempfile
import unittest

from tools.simulation_scenarios import SCENARIOS, ScenarioResult, SimulationTrace, run_scenario


class TestSimulationSandbox(unittest.TestCase):
    def test_registry_contains_required_scenarios(self):
        self.assertGreaterEqual(
            set(SCENARIOS),
            {"construction_basic", "delivery_basic", "hunting_food_chain", "settlement_growth"},
        )

    def test_construction_basic_runs_headlessly_and_reports_structure(self):
        result = run_scenario("construction_basic", seed=123, ticks=500)
        report = result.to_dict()

        self.assertEqual(report["scenario"], "construction_basic")
        self.assertEqual(report["seed"], 123)
        self.assertEqual(report["ticks"], 500)
        self.assertIn(report["result"], {"PASS", "FAIL"})
        self.assertTrue(report["assertions"])
        self.assertTrue(report["events"])
        self.assertIn("blueprint_created", {assertion["name"] for assertion in report["assertions"]})

    def test_delivery_basic_emits_lifecycle_events_or_failed_assertion(self):
        result = run_scenario("delivery_basic", seed=123, ticks=500)
        event_types = {event.event_type for event in result.trace.events}
        assertion_failures = [assertion for assertion in result.trace.assertions if not assertion.passed]

        if result.result == "PASS":
            self.assertGreaterEqual(
                event_types,
                {"delivery_created", "delivery_claimed", "delivery_pickup", "delivery_deposit", "delivery_completed"},
            )
        else:
            self.assertTrue(assertion_failures)
            self.assertTrue(all(assertion.name for assertion in assertion_failures))

    def test_report_json_can_be_written(self):
        result = run_scenario("delivery_basic", seed=123, ticks=500)

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = f"{temp_dir}/delivery_basic.json"
            result.write_json(report_path)
            with open(report_path, encoding="utf-8") as handle:
                report = json.load(handle)

        self.assertEqual(report["scenario"], "delivery_basic")
        self.assertIn("events", report)
        self.assertIn("assertions", report)

    def test_failed_assertions_are_represented_cleanly(self):
        trace = SimulationTrace()
        trace.event(0, "scenario_started", metadata={"scenario": "unit_failure"})
        trace.assert_check(1, "forced_failure", False, "intentional test failure", expected="clean representation")
        result = ScenarioResult("unit_failure", 1, 1, trace)
        report = result.to_dict()

        self.assertEqual(report["result"], "FAIL")
        self.assertEqual(report["assertions"], [
            {
                "name": "forced_failure",
                "passed": False,
                "reason": "intentional test failure",
                "metadata": {"expected": "clean representation"},
            }
        ])
        self.assertIn("forced_failure: intentional test failure", result.summary_text())

    def test_seed_and_ticks_produce_stable_assertion_names_and_results(self):
        first = run_scenario("delivery_basic", seed=123, ticks=500).to_dict()["assertions"]
        second = run_scenario("delivery_basic", seed=123, ticks=500).to_dict()["assertions"]

        first_pairs = [(assertion["name"], assertion["passed"]) for assertion in first]
        second_pairs = [(assertion["name"], assertion["passed"]) for assertion in second]
        self.assertEqual(first_pairs, second_pairs)


if __name__ == "__main__":
    unittest.main()
