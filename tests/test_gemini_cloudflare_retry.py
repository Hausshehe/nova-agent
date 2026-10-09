import unittest

from gemini_agent.client import GeminiClient


class CloudflareToolChoiceRetryTests(unittest.TestCase):
    def test_retries_matching_bad_request_when_tool_choice_is_forced(self):
        payload = {
            "tool_choice": {
                "type": "function",
                "function": {"name": "make_directory"},
            }
        }
        self.assertTrue(
            GeminiClient._should_retry_with_auto_tool_choice(
                400,
                '{"message":"AiError: Expecting value: line 1 column 1 (char 0)"}',
                payload,
            )
        )

    def test_does_not_retry_same_failure_twice(self):
        payload = {"tool_choice": {"type": "function", "function": {"name": "x"}}}
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(
                400, "Expecting value: line 1 column 1", payload, True
            )
        )

    def test_does_not_retry_unrelated_bad_request(self):
        payload = {"tool_choice": {"type": "function", "function": {"name": "x"}}}
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(
                400, "Invalid schema", payload
            )
        )

    def test_does_not_retry_when_choice_is_not_forced(self):
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(
                400,
                "Expecting value: line 1 column 1",
                {"tool_choice": "auto"},
            )
        )

    def test_does_not_retry_non_400_errors(self):
        payload = {"tool_choice": {"type": "function", "function": {"name": "x"}}}
        self.assertFalse(
            GeminiClient._should_retry_with_auto_tool_choice(
                503, "Expecting value: line 1 column 1", payload
            )
        )

    def test_autonomous_goal_restores_tools_after_a_toolless_continuation(self):
        payload = {
            "model": "@cf/zai-org/glm-4.7-flash",
            "messages": [],
            "tools": [],
        }
        declarations = [{
            "name": "run_command",
            "description": "Run a bounded command.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }]

        restored = GeminiClient._restore_tools_for_autonomous_goal(
            payload, declarations, autonomous_goal=True
        )

        self.assertTrue(restored)
        self.assertEqual(
            [tool["function"]["name"] for tool in payload["tools"]],
            ["run_command"],
        )
        self.assertEqual(payload["tool_choice"], "auto")

    def test_does_not_restore_tools_for_non_autonomous_requests(self):
        payload = {"tools": []}
        restored = GeminiClient._restore_tools_for_autonomous_goal(
            payload,
            [{"name": "run_command", "description": "", "parameters": {}}],
            autonomous_goal=False,
        )
        self.assertFalse(restored)
        self.assertEqual(payload["tools"], [])

    def test_error_diagnostic_context_excludes_credentials_and_includes_tool_path(self):
        payload = {
            "model": "@cf/zai-org/glm-4.7-flash",
            "tool_choice": "auto",
            "tools": [
                {"function": {"name": "execute_constructed_action"}},
                {"function": {"name": "select_goal_next_step"}},
            ],
        }
        context = GeminiClient._cloudflare_request_context(payload, True)
        import json
        rendered = json.dumps(context, sort_keys=True)
        self.assertIn("execute_constructed_action", rendered)
        self.assertIn('"tool_choice": "auto"', rendered)
        self.assertIn('"auto_tool_choice_retry_used": true', rendered)
        self.assertNotIn("token", rendered.lower())


if __name__ == "__main__":
    unittest.main()
