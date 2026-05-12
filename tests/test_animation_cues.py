"""Tests for lightweight animation cues."""

import unittest
from simulation.animation_cues import ANIMATION_CUES, get_cue, AnimationCue, CueFrame
from tools.simulation_scenarios import TraceEvent

class TestAnimationCues(unittest.TestCase):
    def test_cue_registry_contains_defaults(self):
        cues = ["open_door", "chop_tree", "build", "attack_lunge", "butcher_work", "haul_carry"]
        for cue_id in cues:
            cue = get_cue(cue_id)
            self.assertIsNotNone(cue)
            self.assertEqual(cue.cue_id, cue_id)

    def test_cue_frame_generation_if_empty(self):
        cue = AnimationCue(cue_id="test", frame_count=2, frame_duration=10)
        self.assertEqual(len(cue.frames), 2)
        self.assertEqual(cue.frames[0], CueFrame())

    def test_cue_validation_rejects_mismatched_frames(self):
        with self.assertRaises(ValueError):
            AnimationCue(cue_id="test", frame_count=2, frame_duration=10, frames=[CueFrame()])

    def test_deterministic_frame_metadata(self):
        cue = get_cue("open_door")
        self.assertEqual(cue.frame_count, 3)
        self.assertEqual(cue.frames[1].target_state, "open")

    def test_trace_event_metadata_integration(self):
        event = TraceEvent(
            tick=1,
            event_type="action_performed",
            metadata={"animation_cue": "open_door"}
        )
        self.assertEqual(event.metadata["animation_cue"], "open_door")


    def test_preview_export_success(self):
        from tools.asset_workbench import preview_animation
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "test.png")
            result = preview_animation("open_door", output=out_path)
            self.assertEqual(result["preview"], "animation")
            self.assertEqual(result["cue_id"], "open_door")
            self.assertTrue(os.path.exists(out_path))

    def test_graceful_missing_asset_handling(self):
        from tools.asset_workbench import preview_animation
        result = preview_animation("non_existent_cue")
        self.assertEqual(result["error"], "Cue not found")
        self.assertEqual(result["missing_assets"], ["non_existent_cue"])

if __name__ == "__main__":
    unittest.main()
