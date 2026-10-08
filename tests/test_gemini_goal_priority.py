import unittest

from gemini_agent.goal_priority import GoalPriorityCandidate, select_goal_priority


class GoalPriorityTests(unittest.TestCase):
    def test_selects_highest_explicit_priority(self):
        result = select_goal_priority(
            "battery | Check battery | 10 | 1 | 0 | 5\n"
            "urgent | Handle urgent task | 90 | 8 | 0 | 5"
        )
        self.assertIn("Selected goal: urgent", result)
        self.assertIn("Priority score: 8099995", result)

    def test_user_priority_can_outweigh_urgency(self):
        result = select_goal_priority(
            "important | Important user goal | 20 | 10 | 0 | 0\n"
            "urgent | Urgent goal | 100 | 0 | 0 | 0"
        )
        self.assertIn("Selected goal: important", result)

    def test_resource_cost_reduces_priority(self):
        low_cost = GoalPriorityCandidate("a", "A", 50, 5, 0, 0)
        high_cost = GoalPriorityCandidate("b", "B", 50, 5, 0, 100)
        self.assertGreater(low_cost.score(), high_cost.score())

    def test_tied_highest_scores_require_human_input(self):
        result = select_goal_priority(
            "a | Goal A | 10 | 5 | 0 | 0\n"
            "b | Goal B | 10 | 5 | 0 | 0"
        )
        self.assertIn("Decision: HUMAN INPUT REQUIRED", result)
        self.assertIn("a, b", result)

    def test_rejects_duplicate_goal_ids(self):
        with self.assertRaises(ValueError):
            select_goal_priority(
                "a | Goal A | 1 | 1 | 1 | 1\n"
                "a | Goal B | 2 | 2 | 2 | 2"
            )

    def test_rejects_unbounded_signal(self):
        with self.assertRaises(ValueError):
            select_goal_priority("a | Goal A | 101 | 0 | 0 | 0")


if __name__ == "__main__":
    unittest.main()
