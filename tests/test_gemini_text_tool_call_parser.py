import json
import unittest

from gemini_agent.client import GeminiClient


class TextToolCallParserTests(unittest.TestCase):
    def setUp(self):
        self.declarations = [{
            "name": "make_directory",
            "description": "Create a directory",
            "parameters": {
                "type": "OBJECT",
                "properties": {"path": {"type": "STRING"}},
                "required": ["path"],
            },
        }]

    def test_parses_registered_explicit_text_tool_call(self):
        content = (
            "<tool_call>make_directory"
            "<arg_key>path</arg_key><arg_value>workspace/app</arg_value>"
            "</tool_call>"
        )
        parsed = GeminiClient._parse_text_tool_call(content, self.declarations)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["function"]["name"], "make_directory")
        self.assertEqual(
            json.loads(parsed["function"]["arguments"]),
            {"path": "workspace/app"},
        )

    def test_rejects_unregistered_tool_name(self):
        content = (
            "<tool_call>represent_goal_portfolio"
            "<arg_key>goal</arg_key><arg_value>Build an app</arg_value>"
            "</tool_call>"
        )
        self.assertIsNone(GeminiClient._parse_text_tool_call(content, self.declarations))

    def test_rejects_missing_required_argument(self):
        content = "<tool_call>make_directory</tool_call>"
        self.assertIsNone(GeminiClient._parse_text_tool_call(content, self.declarations))

    def test_ignores_ordinary_prose(self):
        self.assertIsNone(
            GeminiClient._parse_text_tool_call("I will create the workspace.", self.declarations)
        )


if __name__ == "__main__":
    unittest.main()
