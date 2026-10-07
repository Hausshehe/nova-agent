import unittest

from gemini_agent.goal_state import GoalState, start_goal_state


class GoalStateTests(unittest.TestCase):
    def test_starts_active_without_completion_claim(self):
        state = start_goal_state("Check battery", "Battery status is reported")
        self.assertEqual(state.status, "ACTIVE")
        self.assertEqual(state.snapshot()["progress_status"], "INCONCLUSIVE")
        self.assertEqual(state.snapshot()["evidence"], [])
        self.assertEqual(state.snapshot()["steps"], [])

    def test_bounded_evidence_history(self):
        state = GoalState("Goal", "Done")
        for i in range(10):
            state.add_evidence(f"evidence-{i}")
        self.assertEqual(state.snapshot()["evidence"], [f"evidence-{i}" for i in range(2, 10)])

    def test_records_bounded_goal_steps(self):
        state = GoalState("Goal", "Done")
        for i in range(18):
            state.record_step(f"tool_{i}", "EXECUTED", f"evidence-{i}")
        steps = state.snapshot()["steps"]
        self.assertEqual(len(steps), 16)
        self.assertEqual(steps[0]["action"], "tool_2")
        self.assertEqual(steps[-1]["status"], "EXECUTED")

    def test_rejects_invalid_step_status(self):
        state = GoalState("Goal", "Done")
        with self.assertRaises(ValueError):
            state.record_step("tool", "UNKNOWN", "evidence")

    def test_rejects_invalid_goal_state(self):
        with self.assertRaises(ValueError):
            GoalState("", "Done")
        with self.assertRaises(ValueError):
            GoalState("Goal", "")
        with self.assertRaises(ValueError):
            GoalState("Goal", "Done", "UNKNOWN")
