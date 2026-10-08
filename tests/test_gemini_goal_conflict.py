import unittest

from gemini_agent.goal_conflict import GoalConflictCandidate, resolve_goal_conflicts


class GoalConflictTests(unittest.TestCase):
    def test_resolves_deferrable_goal_against_must_continue(self):
        result = resolve_goal_conflicts(
            "urgent | Handle urgent task | shared-device | MUST_CONTINUE\n"
            "battery | Check battery | shared-device | CAN_DEFER"
        )
        self.assertIn("urgent retains the conflicting resource/outcome; battery is safely deferrable", result)
        self.assertIn("battery must retain its goal state and resume later", result)
        self.assertIn("all detected conflicts have a constraint-supported resolution", result)
        self.assertIn("No device state was changed.", result)

    def test_protects_goal_that_must_not_be_interrupted(self):
        result = resolve_goal_conflicts(
            "critical | Protect critical task | shared-ui | MUST_NOT_INTERRUPT; "
            "background | Background task | shared-ui | CAN_INTERRUPT"
        )
        self.assertIn("critical retains uninterrupted ownership", result)

    def test_requires_human_for_unresolved_conflict(self):
        result = resolve_goal_conflicts(
            "a | Goal A | shared-resource | CAN_DEFER; "
            "b | Goal B | shared-resource | CAN_DEFER"
        )
        self.assertIn("HUMAN INPUT REQUIRED", result)
        self.assertIn("1 conflict group(s) remain unresolved.", result)

    def test_non_conflicting_goals_are_left_independent(self):
        result = resolve_goal_conflicts(
            "battery | Check battery | battery | CAN_DEFER; "
            "date | Check date | date | CAN_DEFER"
        )
        self.assertIn("no competing goals share a conflict key", result)

    def test_rejects_duplicate_ids_and_invalid_constraint(self):
        with self.assertRaises(ValueError):
            resolve_goal_conflicts(
                "a | Goal A | shared | CAN_DEFER; a | Goal B | other | CAN_DEFER"
            )
        with self.assertRaises(ValueError):
            resolve_goal_conflicts("a | Goal A | shared | PRIORITY")

    def test_candidate_bounds(self):
        self.assertEqual(
            GoalConflictCandidate("a", "Goal", "shared", "CAN_DEFER").constraint,
            "CAN_DEFER",
        )
        with self.assertRaises(ValueError):
            resolve_goal_conflicts(
                "; ".join(f"g{i} | Goal {i} | k{i} | CAN_DEFER" for i in range(9))
            )


if __name__ == "__main__":
    unittest.main()
