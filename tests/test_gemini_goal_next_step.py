import unittest

from gemini_agent.goal_next_step import select_goal_next_step


class GoalNextStepTests(unittest.TestCase):
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
