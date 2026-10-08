import unittest

from gemini_agent.goal_interruption import GoalInterruptionState, manage_goal_interruption


class GoalInterruptionTests(unittest.TestCase):
    def test_pauses_and_resumes_while_preserving_checkpoint(self):
        result = manage_goal_interruption(
            "task | ACTIVE | Step 3 complete; resume from Step 3 | PAUSE, RESUME"
        )
        self.assertIn("Transition: PAUSE -> PAUSED", result)
        self.assertIn("Transition: RESUME -> ACTIVE", result)
        self.assertIn("Final status: ACTIVE", result)
        self.assertIn("Checkpoint preserved: YES", result)
        self.assertIn("No device state was changed.", result)

    def test_paused_goal_can_resume(self):
        result = manage_goal_interruption(
            "task | PAUSED | Saved checkpoint | RESUME"
        )
        self.assertIn("Final status: ACTIVE", result)

    def test_rejects_invalid_transition(self):
        with self.assertRaises(ValueError):
            manage_goal_interruption("task | ACTIVE | Saved checkpoint | RESUME")

    def test_rejects_malformed_request(self):
        with self.assertRaises(ValueError):
            manage_goal_interruption("task | ACTIVE | Saved checkpoint")


if __name__ == "__main__":
    unittest.main()
