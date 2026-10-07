import unittest

from gemini_agent.goal_state import GoalState, start_goal_state


class GoalStateTests(unittest.TestCase):
    def test_starts_active_without_completion_claim(self):
        state = start_goal_state("Check battery", "Battery status is reported")
        self.assertEqual(state.status, "ACTIVE")
        self.assertEqual(state.snapshot()["evidence"], [])

    def test_bounded_evidence_history(self):
        state = GoalState("Goal", "Done")
        for i in range(10):
            state.add_evidence(f"evidence-{i}")
        self.assertEqual(state.snapshot()["evidence"], [f"evidence-{i}" for i in range(2, 10)])

    def test_rejects_invalid_goal_state(self):
        with self.assertRaises(ValueError):
            GoalState("", "Done")
        with self.assertRaises(ValueError):
            GoalState("Goal", "")
        with self.assertRaises(ValueError):
            GoalState("Goal", "Done", "UNKNOWN")
