"""Client routing tests for bounded local tool execution."""

import unittest

from gemini_agent.client import GeminiClient


class ClientDirectToolRoutingTests(unittest.TestCase):
    def test_workspace_executable_discovery_returns_directly_after_first_tool_round(self):
        self.assertTrue(
            GeminiClient._should_return_tool_result_directly(
                "discover_workspace_executables", 0
            )
        )

    def test_workspace_executable_discovery_does_not_repeat_on_later_rounds(self):
        self.assertFalse(
            GeminiClient._should_return_tool_result_directly(
                "discover_workspace_executables", 1
            )
        )


if __name__ == "__main__":
    unittest.main()
