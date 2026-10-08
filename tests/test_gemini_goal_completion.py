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

    def test_goal_contract_metadata_cannot_verify_goal(self):
        result = verify_goal_completion(
            "run the harmless Android diagnostic command dumpsys -l and report the current date",
            "the recovered diagnostic command result and current date are successfully reported",
            "Runtime goal contract established for this turn. "
            "Goal: run the harmless Android diagnostic command dumpsys -l and report the current date. "
            "Success condition: the recovered diagnostic command result and current date are successfully reported. "
            "The runtime state is ACTIVE. "
            "Any tool outcome must be observed as goal evidence; do not claim final completion unless a later bounded completion verifier explicitly proves it.",
        )
        self.assertEqual(result.status, "INCONCLUSIVE")


    def test_read_only_discovery_echo_cannot_verify_construction_goal(self):
        result = verify_goal_completion(
            "Create a minimal Android calculator app from scratch in a new workspace.",
            "Build the APK and verify the resulting artifact with evidence.",
            "Android mechanism discovery (read-only):\n"
            "Requested capability: Create a minimal Android calculator app from scratch in a new workspace. "
            "Build the APK and verify the resulting artifact with evidence.\n"
            "Discovered bounded UI mechanisms: ui-text:HOME\n"
            "No action was performed and no device state was modified.",
        )
        self.assertEqual(result.status, "INCONCLUSIVE")

    def test_iso_datetime_is_date_evidence(self):
        result = verify_goal_completion(
            "check the battery and current date",
            "the battery status and current date are successfully reported",
            "Level: 82% Status: Charging Power source: Battery\n"
            "2026-10-07T20:00:00+03:00",
        )
        self.assertEqual(result.status, "VERIFIED")

    def test_verification_tool_metadata_cannot_complete_goal(self):
        result = verify_goal_completion(
            "attempt the unavailable command and report the current date",
            "the current date is successfully reported after the unavailable command attempt",
            "Verification: VERIFIED: expected text found: Goal contract established.\n"
            "Observed tool: verify_command_result",
        )
        self.assertEqual(result.status, "INCONCLUSIVE")

    def test_partial_ordered_goal_evidence_cannot_verify(self):
        result = verify_goal_completion(
            "attempt the unavailable command and report the current date",
            "the current date is successfully reported after the unavailable command attempt",
            "2026-10-08T00:17:34+03:00",
        )
        self.assertEqual(result.status, "INCONCLUSIVE")

    def test_ordered_goal_verifies_when_both_sides_are_observed(self):
        result = verify_goal_completion(
            "attempt the unavailable command and report the current date",
            "the current date is successfully reported after the unavailable command attempt",
            "Goal step attempted: run_command nova-missing-command\n"
            "2026-10-08T00:17:34+03:00",
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
