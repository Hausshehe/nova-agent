import unittest

from gemini_agent.goal_state import is_premature_blocker_claim, step_goal_disposition


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


    def test_active_goal_rejects_unverified_terminal_blocker_claims(self):
        self.assertTrue(is_premature_blocker_claim(
            "ACTIVE",
            "Goal status: BLOCKED. No recovery path available without installing tools.",
        ))

    def test_active_goal_rejects_claim_that_no_recovery_path_exists(self):
        self.assertTrue(is_premature_blocker_claim(
            "ACTIVE",
            "There is no viable recovery path.",
        ))

    def test_verified_or_failed_goal_does_not_trigger_blocker_rejection(self):
        response = "Goal status: BLOCKED. No recovery path available."
        self.assertFalse(is_premature_blocker_claim("VERIFIED", response))
        self.assertFalse(is_premature_blocker_claim("FAILED", response))

    def test_unrelated_prose_does_not_trigger_blocker_rejection(self):
        self.assertFalse(is_premature_blocker_claim("ACTIVE", "I will inspect the build options."))


if __name__ == "__main__":
    unittest.main()
