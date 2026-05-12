import json
import tempfile
import unittest
from unittest.mock import patch

from tools.simulation_scenarios import SCENARIOS, ScenarioResult, SimulationTrace, run_scenario
from tools.asset_workbench import preview_animal, preview_blueprint, preview_character
from tools.simulation_snapshot import SnapshotConfig, render_snapshot


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


    def test_final_snapshot_file_is_written_headlessly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = f"{temp_dir}/construction_basic.png"
            result = run_scenario(
                "construction_basic",
                seed=123,
                ticks=500,
                snapshot_config=SnapshotConfig(snapshot_path=snapshot_path),
            )

            self.assertEqual(result.result, "PASS")
            self.assertTrue(result.artifacts["snapshot"].endswith("construction_basic.png"))
            with open(snapshot_path, "rb") as handle:
                self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")

    def test_periodic_snapshot_directory_and_report_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_dir = f"{temp_dir}/snapshots"
            report_path = f"{temp_dir}/delivery_basic.json"
            result = run_scenario(
                "delivery_basic",
                seed=123,
                ticks=200,
                snapshot_config=SnapshotConfig(snapshot_every=100, snapshot_dir=snapshot_dir),
            )
            result.write_json(report_path)

            self.assertEqual(len(result.artifacts["snapshots"]), 2)
            for snapshot_path in result.artifacts["snapshots"]:
                self.assertTrue(snapshot_path.endswith(".png"))
                with open(snapshot_path, "rb") as handle:
                    self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")
            with open(report_path, encoding="utf-8") as handle:
                report = json.load(handle)
            self.assertEqual(report["artifacts"], result.artifacts)

    def test_snapshot_renderer_handles_missing_overlays_and_text_fallback(self):
        result = run_scenario("settlement_growth", seed=123, ticks=10)

        with tempfile.TemporaryDirectory() as temp_dir:
            text_path = f"{temp_dir}/snapshot.png"
            # No world is exposed from completed reports; use an intentionally tiny
            # object to prove missing optional overlay state does not crash.
            tiny_world = type("TinyWorld", (), {"chunk_width": 1, "chunk_height": 1})()
            with patch("tools.simulation_snapshot._write_png", side_effect=RuntimeError("png unavailable")):
                rendered_path = render_snapshot(tiny_world, text_path, overlays=set())

            self.assertEqual(rendered_path, text_path)
            with open(text_path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("Legend:", text)
            self.assertEqual(result.result, "PASS")


    def test_asset_aware_snapshot_rendering_runs_headlessly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = f"{temp_dir}/hunting_food_chain.png"
            result = run_scenario(
                "hunting_food_chain",
                seed=123,
                ticks=500,
                snapshot_config=SnapshotConfig(snapshot_path=snapshot_path, overlays={"wildlife", "npcs", "buildings", "items"}),
            )

            self.assertEqual(result.result, "PASS")
            with open(snapshot_path, "rb") as handle:
                self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")

    def test_missing_asset_mappings_fail_gracefully(self):
        summary = preview_animal("not_a_real_animal")

        self.assertIn("not_a_real_animal", summary["missing_assets"])
        self.assertIsNone(summary["asset_keys"]["animal"])

    def test_blueprint_and_interaction_overlays_render_safely(self):
        blueprint = type(
            "Blueprint",
            (),
            {"x": 2, "y": 2, "width": 5, "height": 4, "required_materials": {"raw_log": 1}},
        )()
        building = type(
            "Building",
            (),
            {
                "global_origin_x": 10,
                "global_origin_y": 10,
                "width": 4,
                "height": 4,
                "building_type": "workshop",
                "anchors": [{"x": 11, "y": 11, "type": "workbench"}],
                "interaction_points": {"door": (12, 13)},
                "work_zone_tiles": {"station": [(12, 12)]},
            },
        )()
        world = type(
            "OverlayWorld",
            (),
            {
                "chunk_width": 1,
                "chunk_height": 1,
                "blueprints_by_id": {"bp": blueprint},
                "buildings_by_id": {"b": building},
                "land_claims_by_id": {},
                "village_npcs": [],
                "npcs": [],
            },
        )()

        with tempfile.TemporaryDirectory() as temp_dir:
            text_path = f"{temp_dir}/overlays.txt"
            render_snapshot(world, text_path, overlays={"blueprints", "interactions", "buildings"}, force_text=True)
            with open(text_path, encoding="utf-8") as handle:
                text = handle.read()

        self.assertIn("C", text)
        self.assertIn("a", text)

    def test_crowded_npc_snapshot_limits_labels(self):
        class Schedule:
            current_path = []
            current_destination_coords = None
            current_task = "idle"

        actors = []
        for index in range(25):
            economic = type("Economic", (), {"profession": "Merchant", "npc_inventory": {}})()
            actors.append(type("Actor", (), {"x": index + 1, "y": 5, "name": f"Crowded{index}", "economic": economic, "schedule": Schedule(), "task_context": None})())
        world = type("CrowdedWorld", (), {"chunk_width": 1, "chunk_height": 1, "village_npcs": actors, "npcs": []})()

        with tempfile.TemporaryDirectory() as temp_dir:
            text_path = f"{temp_dir}/crowded.txt"
            render_snapshot(world, text_path, overlays={"npcs", "labels"}, force_text=True)
            with open(text_path, encoding="utf-8") as handle:
                text = handle.read()

        self.assertLessEqual(text.count("Crowde"), 3)

    def test_asset_preview_export_writes_files_successfully(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            character = preview_character("female", "Blacksmith", f"{temp_dir}/character.png")
            blueprint = preview_blueprint("butcher_shop", f"{temp_dir}/blueprint.png")
            animal = preview_animal("deer", f"{temp_dir}/animal.png")

            for summary in (character, blueprint, animal):
                with open(summary["output"], "rb") as handle:
                    self.assertEqual(handle.read(8), b"\x89PNG\r\n\x1a\n")
                self.assertIn("asset_keys", summary)

    def test_seed_and_ticks_produce_stable_assertion_names_and_results(self):
        first = run_scenario("delivery_basic", seed=123, ticks=500).to_dict()["assertions"]
        second = run_scenario("delivery_basic", seed=123, ticks=500).to_dict()["assertions"]

        first_pairs = [(assertion["name"], assertion["passed"]) for assertion in first]
        second_pairs = [(assertion["name"], assertion["passed"]) for assertion in second]
        self.assertEqual(first_pairs, second_pairs)


if __name__ == "__main__":
    unittest.main()
