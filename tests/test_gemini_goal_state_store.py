import json
import tempfile
import unittest
from pathlib import Path

from gemini_agent.goal_state import GoalState, start_goal_state
from gemini_agent.goal_state_store import load_goal_state, save_goal_state


class GoalStateStoreTests(unittest.TestCase):
    def test_round_trip_preserves_active_goal_evidence_steps_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "active_goal.json"
            state = start_goal_state("Build an app", "APK is built and verified")
            state.add_evidence("Initial build failed: missing SDK path")
            state.progress_status = "BLOCKED"
            state.progress_reason = "Build tool could not find SDK"
            state.record_step("gradle", "FAILED", "SDK path missing")
            state.record_recovery("Inspected environment and identified configured SDK path")
            save_goal_state(state, path)

            restored = load_goal_state(path)

            self.assertIsNotNone(restored)
            self.assertEqual(restored.snapshot(), state.snapshot())
            self.assertEqual(json.loads(path.read_text())["version"], 1)

    def test_missing_record_returns_none(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(load_goal_state(Path(directory) / "missing.json"))

    def test_terminal_goal_is_not_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "active_goal.json"
            state = start_goal_state("Build an app", "APK is verified")
            state.status = "VERIFIED"
            save_goal_state(state, path)
            self.assertIsNone(load_goal_state(path))
            self.assertEqual(json.loads(path.read_text())["goal_state"]["status"], "VERIFIED")

    def test_corrupt_record_is_rejected_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "active_goal.json"
            path.write_text("{broken")
            with self.assertRaises(ValueError):
                load_goal_state(path)
            self.assertEqual(path.read_text(), "{broken")

    def test_unsupported_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "active_goal.json"
            path.write_text(json.dumps({"version": 99, "goal_state": {}}))
            with self.assertRaises(ValueError):
                load_goal_state(path)

    def test_recovery_history_is_bounded(self):
        state = GoalState("Goal", "Done")
        for index in range(10):
            state.record_recovery(f"recovery-{index}")
        self.assertEqual(state.snapshot()["recovery_history"], [f"recovery-{i}" for i in range(2, 10)])
