import unittest

from gemini_agent.goal_contract import GoalContract, establish_goal_contract
from gemini_agent.client import GeminiClient
from gemini_agent.tools import TOOL_HANDLERS, TOOL_DECLARATIONS


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

    def test_client_routes_explicit_goal_contract_requests_locally(self):
        contents = [{
            "role": "user",
            "parts": [{"text": "Establish a goal contract for checking battery with success condition battery status is reported."}],
        }]
        self.assertEqual(
            GeminiClient._requested_local_tool(contents),
            "establish_goal_contract",
        )

    def test_goal_contract_is_registered_once(self):
        self.assertIn("establish_goal_contract", TOOL_HANDLERS)
        names = [item["name"] for item in TOOL_DECLARATIONS]
        self.assertEqual(names.count("establish_goal_contract"), 1)
