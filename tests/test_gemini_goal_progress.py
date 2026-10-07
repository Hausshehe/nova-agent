import unittest

from gemini_agent.goal_progress import observe_goal_progress


class GoalProgressTests(unittest.TestCase):
    def test_success_condition_overlap_is_progress_not_completion(self):
        result = observe_goal_progress(
            "Check device battery",
            "the current battery status is successfully reported",
            "Level: 82% Status: Charging",
        )
        self.assertEqual(result.status, "PROGRESS")
        self.assertIn("without claiming final completion", result.reason)

    def test_explicit_failure_is_blocked(self):
        result = observe_goal_progress(
            "Check device battery",
            "the current battery status is successfully reported",
            "Postcondition: FAILED: battery status unavailable",
        )
        self.assertEqual(result.status, "BLOCKED")

    def test_unrelated_evidence_is_inconclusive(self):
        result = observe_goal_progress(
            "Check device battery",
            "the current battery status is successfully reported",
            "Current working directory: /data/data/com.termux/files/home",
        )
        self.assertEqual(result.status, "INCONCLUSIVE")

    def test_inputs_are_bounded(self):
        with self.assertRaises(ValueError):
            observe_goal_progress("", "Done", "evidence")
        with self.assertRaises(ValueError):
            observe_goal_progress("Goal", "Done", "")
        with self.assertRaises(ValueError):
            observe_goal_progress("x" * 513, "Done", "evidence")


if __name__ == "__main__":
    unittest.main()
