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

    def test_client_routes_goal_priority_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Select goal priority from "battery | Check battery | 10 | 1 | 0 | 5\\n'
            'urgent | Handle urgent task | 90 | 8 | 0 | 5". '
            "Do not execute, interrupt, or complete any goal."
        )
        self.assertIn("Selected goal: urgent", result)
        self.assertIn("Priority score:", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "select_goal_priority")


    def test_client_routes_goal_interruption_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Manage goal interruption for "task | ACTIVE | Step 3 complete | PAUSE, RESUME". '
            "Preserve the checkpoint and do not execute or complete the goal."
        )
        self.assertIn("Transition: PAUSE -> PAUSED", result)
        self.assertIn("Transition: RESUME -> ACTIVE", result)
        self.assertIn("Checkpoint preserved: YES", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "manage_goal_interruption")

    def test_goal_interruption_tool_is_registered_once(self):
        self.assertIn("manage_goal_interruption", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("manage_goal_interruption"), 1)

    def test_goal_priority_tool_is_registered_once(self):
        self.assertIn("select_goal_priority", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("select_goal_priority"), 1)


if __name__ == "__main__":
    unittest.main()
