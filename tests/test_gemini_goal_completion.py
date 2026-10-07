"""Offline tests for bounded goal-completion verification."""

import unittest

from gemini_agent.goal_completion import verify_goal_completion


class GoalCompletionTests(unittest.TestCase):
    def test_matching_evidence_verifies_goal(self):
        result = verify_goal_completion(
            "check the device battery",
            "the current battery status is successfully reported",
            "Level: 70% Status: Discharging Health: Good",
        )
        self.assertEqual(result.status, "VERIFIED")

    def test_explicit_failure_fails_goal(self):
        result = verify_goal_completion(
            "check the device battery",
            "the current battery status is successfully reported",
            "Tool error: battery command failed",
        )
        self.assertEqual(result.status, "FAILED")

    def test_partial_evidence_is_inconclusive(self):
        result = verify_goal_completion(
            "check the device battery",
            "the current battery status is successfully reported",
            "Level: 70%",
        )
        self.assertEqual(result.status, "INCONCLUSIVE")

    def test_unrelated_evidence_is_inconclusive(self):
        result = verify_goal_completion(
            "check the device battery",
            "the current battery status is successfully reported",
            "Network interface is connected.",
        )
        self.assertEqual(result.status, "INCONCLUSIVE")

    def test_inputs_are_bounded(self):
        with self.assertRaises(ValueError):
            verify_goal_completion("", "reported", "reported")
        with self.assertRaises(ValueError):
            verify_goal_completion("goal", "reported", "x" * 4097)


if __name__ == "__main__":
    unittest.main()
