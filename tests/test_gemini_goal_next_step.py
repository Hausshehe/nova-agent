import unittest

from gemini_agent.goal_next_step import select_goal_next_step


class GoalNextStepTests(unittest.TestCase):
    def test_ordered_success_condition_prioritizes_prerequisite_step(self):
        result = select_goal_next_step(
            "attempt the unavailable command and report the current date",
            "the current date is successfully reported after the unavailable command attempt",
            "ACTIVE",
            "INCONCLUSIVE",
            "No goal-progress observation has been recorded.",
            ["current_datetime", "run_command"],
        )
        self.assertEqual(result.action, "run_command")

    def test_selects_goal_relevant_candidate(self):
        result = select_goal_next_step(
            "check the device battery",
            "the current battery status is successfully reported",
            "ACTIVE",
            "PROGRESS",
            "Observed battery state provides progress.",
            ["get_wifi_status", "get_system_battery_status"],
        )
        self.assertEqual(result.action, "get_system_battery_status")

    def test_unblocked_goal_prefers_primary_action_over_recovery(self):
        result = select_goal_next_step(
            "actually attempt the diagnostic command and report the current date",
            "the diagnostic command has been attempted successfully and the current date is reported",
            "ACTIVE",
            "INCONCLUSIVE",
            "No bounded evidence is available.",
            ["recover_command", "run_command", "current_datetime"],
        )
        self.assertEqual(result.action, "run_command")

    def test_unblocked_goal_does_not_substitute_verification_for_primary_action(self):
        result = select_goal_next_step(
            "attempt the unavailable command and report the current date",
            "the current date is successfully reported after the unavailable command attempt",
            "ACTIVE",
            "INCONCLUSIVE",
            "No bounded evidence is available.",
            ["verify_command_result", "run_command", "current_datetime"],
        )
        self.assertEqual(result.action, "run_command")

    def test_blocked_prefers_recovery_candidate(self):
        result = select_goal_next_step(
            "recover a failed battery check",
            "battery status is successfully reported",
            "ACTIVE",
            "BLOCKED",
            "Observed evidence contains an explicit failure marker.",
            ["get_system_battery_status", "recover_command"],
        )
        self.assertEqual(result.action, "recover_command")

    def test_uses_accumulated_evidence_to_select_remaining_step(self):
        result = select_goal_next_step(
            "check the battery and current date",
            "the battery status and current date are successfully reported",
            "ACTIVE",
            "PROGRESS",
            "Battery evidence provides partial progress.",
            ["get_system_battery_status", "current_datetime"],
            "Level: 82% Status: Charging Power source: Battery",
        )
        self.assertEqual(result.action, "current_datetime")

    def test_verified_goal_stops(self):
        result = select_goal_next_step(
            "check the device battery",
            "the current battery status is successfully reported",
            "VERIFIED",
            "PROGRESS",
            "Evidence satisfies the success condition.",
            ["get_system_battery_status"],
        )
        self.assertEqual(result.action, "STOP")

    def test_unfamiliar_construction_falls_back_to_constructed_action(self):
        result = select_goal_next_step(
            "create a minimal Android app",
            "the APK is built and verified with evidence",
            "ACTIVE",
            "INCONCLUSIVE",
            "No bounded evidence is available.",
            ["get_wifi_status", "execute_constructed_action", "verify_command_result"],
        )
        self.assertEqual(result.action, "execute_constructed_action")

    def test_construction_goal_does_not_select_intent_clarification_as_an_action(self):
        result = select_goal_next_step(
            "Create a minimal Android calculator app from scratch in a new workspace.",
            "Create the source files and configuration, build an installable APK, and verify addition, subtraction, multiplication, and division with actual tests.",
            "ACTIVE",
            "INCONCLUSIVE",
            "No bounded evidence is available.",
            [
                "build_intent_clarification",
                "list_directory",
                "read_text_file",
                "execute_constructed_action",
            ],
        )
        self.assertEqual(result.action, "execute_constructed_action")

    def test_blocked_construction_diagnoses_failed_action_before_repeating_executor(self):
        result = select_goal_next_step(
            "Create a minimal Android calculator app from scratch in a new workspace.",
            "Create the source files and configuration, build an installable APK, and verify addition, subtraction, multiplication, and division with actual tests.",
            "ACTIVE",
            "BLOCKED",
            "Observed evidence contains an explicit failure marker.",
            [
                "execute_constructed_action",
                "diagnose_command_failure",
                "find_executable",
                "discover_workspace_executables",
                "recover_command",
            ],
        )
        self.assertEqual(result.action, "diagnose_command_failure")

    def test_unrelated_candidates_stop_safely(self):
        result = select_goal_next_step(
            "check the device battery",
            "the current battery status is successfully reported",
            "ACTIVE",
            "INCONCLUSIVE",
            "No bounded evidence is available.",
            ["get_wifi_status", "get_screen_resolution"],
        )
        self.assertEqual(result.action, "STOP")


if __name__ == "__main__":
    unittest.main()
