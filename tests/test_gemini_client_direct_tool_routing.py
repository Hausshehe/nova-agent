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

    def test_explicit_executable_discovery_prompt_selects_single_tool(self):
        contents = [{
            "role": "user",
            "parts": [{
                "text": "Discover executable resources in the current workspace environment."
            }],
        }]
        self.assertEqual(
            GeminiClient._requested_local_tool(contents),
            "discover_workspace_executables",
        )


if __name__ == "__main__":
    unittest.main()
