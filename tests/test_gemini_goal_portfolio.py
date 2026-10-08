import unittest

from gemini_agent.goal_portfolio import GoalPortfolio, PortfolioGoal, establish_goal_portfolio


class GoalPortfolioTests(unittest.TestCase):
    def test_establishes_multiple_distinct_goals(self):
        result = establish_goal_portfolio(
            "battery | Check battery | Battery status is reported\n"
            "date | Check date | Current date is reported"
        )
        self.assertIn("Goal count: 2", result)
        self.assertIn("Goal id: battery", result)
        self.assertIn("Goal id: date", result)
        self.assertIn("no priority, execution, interruption, or completion decision", result)

    def test_rejects_duplicate_goal_ids(self):
        with self.assertRaises(ValueError):
            GoalPortfolio((
                PortfolioGoal("task", "First", "First is done"),
                PortfolioGoal("task", "Second", "Second is done"),
            ))

    def test_rejects_malformed_goal_entry(self):
        with self.assertRaises(ValueError):
            establish_goal_portfolio("task | Missing success condition")

    def test_bounds_goal_count(self):
        goals = tuple(
            PortfolioGoal(f"goal-{i}", f"Goal {i}", f"Goal {i} is done")
            for i in range(9)
        )
        with self.assertRaises(ValueError):
            GoalPortfolio(goals)

    def test_portfolio_starts_goals_active(self):
        portfolio = GoalPortfolio((
            PortfolioGoal("a", "Goal A", "A is done"),
            PortfolioGoal("b", "Goal B", "B is done"),
        ))
        snapshot = portfolio.snapshot()
        self.assertEqual(snapshot["count"], 2)
        self.assertEqual(
            [goal["status"] for goal in snapshot["goals"]],
            ["ACTIVE", "ACTIVE"],
        )


if __name__ == "__main__":
    unittest.main()
