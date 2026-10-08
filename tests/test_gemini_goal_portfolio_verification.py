import unittest

from gemini_agent.goal_portfolio_verification import verify_goal_portfolio


class GoalPortfolioVerificationTests(unittest.TestCase):
    def test_verifies_coherent_portfolio(self):
        result = verify_goal_portfolio(
            "battery,date",
            "battery | Check battery | Battery status is reported | VERIFIED | Battery status is reported: 82 percent\n"
            "date | Check date | Current date is reported | ACTIVE | No observations have been collected",
        )
        self.assertIn("Coherence: VERIFIED", result)
        self.assertIn("Missing goals: none", result)
        self.assertIn("Unexpected goals: none", result)

    def test_detects_missing_goal(self):
        result = verify_goal_portfolio(
            "battery,date",
            "battery | Check battery | Battery status is reported | ACTIVE | No observations have been collected; date | Check date | Current date is reported | ACTIVE | No observations have been collected",
        )
        self.assertIn("Missing goals: date", result)
        self.assertIn("Coherence: INCOHERENT", result)

    def test_detects_false_verified_state(self):
        result = verify_goal_portfolio(
            "battery",
            "battery | Check battery | Battery status is reported | VERIFIED | No battery result is available",
        )
        self.assertIn("Coherence: INCOHERENT", result)
        self.assertIn("without verified success evidence", result)

    def test_detects_duplicate_goal_content(self):
        with self.assertRaises(ValueError):
            verify_goal_portfolio(
                "a,b",
                "a | Check battery | Battery status is reported | ACTIVE | Not checked\n"
                "b | Check battery | Battery status is reported | ACTIVE | Not checked",
            )

    def test_detects_unexpected_goal(self):
        result = verify_goal_portfolio(
            "battery",
            "battery | Check battery | Battery status is reported | ACTIVE | No observations have been collected; date | Check date | Current date is reported | ACTIVE | No observations have been collected"
            "date | Check date | Current date is reported | ACTIVE | No observations have been collected",
        )
        self.assertIn("Unexpected goals: date", result)
        self.assertIn("Coherence: INCOHERENT", result)

    def test_rejects_invalid_status(self):
        with self.assertRaises(ValueError):
            verify_goal_portfolio(
                "battery",
                "battery | Check battery | Battery status is reported | UNKNOWN | Not checked",
            )

    def test_bounds_goal_count(self):
        ids = ",".join(f"g{i}" for i in range(9))
        goals = "\n".join(
            f"g{i} | Goal {i} | Goal {i} is done | ACTIVE | Not done"
            for i in range(9)
        )
        with self.assertRaises(ValueError):
            verify_goal_portfolio(ids, goals)


if __name__ == "__main__":
    unittest.main()
