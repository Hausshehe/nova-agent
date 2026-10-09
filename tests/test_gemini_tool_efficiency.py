"""Regression tests for lean tool declarations on construction goals."""

import unittest

from gemini_agent.client import GeminiClient
from gemini_agent.tools import TOOL_DECLARATIONS


class ConstructionToolProfileTests(unittest.TestCase):
    def test_construction_goal_keeps_execution_and_verification_tools_without_diagnostics(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_declarations = TOOL_DECLARATIONS
        contents = [{
            "role": "user",
            "parts": [{
                "text": (
                    "Create a minimal Android calculator app from scratch in a new "
                    "workspace. Determine source files, build procedure, and verify "
                    "the result."
                )
            }],
        }]

        selected = client._relevant_tool_declarations(contents)
        names = {item["name"] for item in selected}

        self.assertLess(len(selected), len(TOOL_DECLARATIONS))
        self.assertTrue({
            "run_command", "find_executable", "verify_command_result",
            "diagnose_command_failure", "retry_command", "recover_command",
            "write_text_file", "read_text_file",
        }.issubset(names))
        self.assertNotIn("get_system_battery_status", names)
        self.assertNotIn("get_screen_brightness", names)


if __name__ == "__main__":
    unittest.main()
