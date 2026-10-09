import unittest

from gemini_agent.goal_state import step_goal_disposition


class GoalStepDispositionTests(unittest.TestCase):
    def test_verified_step_verifies_goal(self):
        self.assertEqual(
            step_goal_disposition("VERIFIED", raw_tool_failed=False, recovery_verified=False),
            ("VERIFIED", False),
        )

    def test_failed_tool_keeps_goal_active_and_requests_replan(self):
        self.assertEqual(
            step_goal_disposition("FAILED", raw_tool_failed=True, recovery_verified=False),
            ("ACTIVE", True),
        )

    def test_incomplete_successful_step_keeps_goal_active(self):
        self.assertEqual(
            step_goal_disposition("FAILED", raw_tool_failed=False, recovery_verified=False),
            ("ACTIVE", False),
        )

    def test_verified_recovery_keeps_goal_active_until_goal_is_verified(self):
        self.assertEqual(
            step_goal_disposition("FAILED", raw_tool_failed=True, recovery_verified=True),
            ("ACTIVE", False),
        )

    def test_inconclusive_step_keeps_goal_active(self):
        self.assertEqual(
            step_goal_disposition("INCONCLUSIVE", raw_tool_failed=False, recovery_verified=False),
            ("ACTIVE", False),
        )


if __name__ == "__main__":
    unittest.main()
