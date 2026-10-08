import unittest

from gemini_agent.client import GeminiClient
from gemini_agent.tools import TOOL_DECLARATIONS, TOOL_HANDLERS


class GoalPortfolioClientTests(unittest.TestCase):
    def test_client_routes_goal_portfolio_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Establish a goal portfolio with "battery | Check battery | Battery status is reported\n'
            'date | Check date | Current date is reported". '
            "Do not prioritize, execute, interrupt, or complete any goal."
        )
        self.assertIn("Goal portfolio established (read-only):", result)
        self.assertIn("Goal count: 2", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "establish_goal_portfolio")
        self.assertIn("no priority", result)

    def test_goal_portfolio_tool_is_registered_once(self):
        self.assertIn("establish_goal_portfolio", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("establish_goal_portfolio"), 1)


if __name__ == "__main__":
    unittest.main()
