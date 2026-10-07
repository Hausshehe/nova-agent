import unittest

from gemini_agent.goal_contract import GoalContract, establish_goal_contract


class GoalContractTests(unittest.TestCase):
    def test_establishes_bounded_goal_contract(self):
        contract = GoalContract("Check battery", "Battery status is reported")
        self.assertEqual(contract.snapshot(), {
            "goal": "Check battery",
            "success_condition": "Battery status is reported",
            "status": "ACTIVE",
        })

    def test_rejects_missing_goal_or_success_condition(self):
        with self.assertRaises(ValueError):
            GoalContract("", "done")
        with self.assertRaises(ValueError):
            GoalContract("goal", "")

    def test_establish_goal_contract_has_no_execution_claim(self):
        result = establish_goal_contract("Check battery", "Battery status is reported")
        self.assertIn("Goal contract established.", result)
        self.assertIn("Status: ACTIVE", result)
        self.assertIn("no action was executed", result)
        self.assertNotIn("VERIFIED", result)
