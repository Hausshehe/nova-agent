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

    def test_tool_loop_failure_context_reports_execution_and_goal_evidence(self):
        from types import SimpleNamespace
        context = GeminiClient._tool_loop_failure_context(
            16,
            [
                {"name": "execute_constructed_action", "result": "created workspace"},
                {"name": "verify_artifact", "result": "APK missing"},
            ],
            SimpleNamespace(
                status="ACTIVE",
                steps=[
                    {"action": "execute_constructed_action", "status": "EXECUTED"},
                    {"action": "verify_artifact", "status": "FAILED"},
                ],
                evidence=["workspace created"],
            ),
        )
        self.assertEqual(context["round_limit"], 16)
        self.assertEqual(context["executed_tool_call_count"], 2)
        self.assertEqual(
            [call["name"] for call in context["recent_executed_tool_calls"]],
            ["execute_constructed_action", "verify_artifact"],
        )
        self.assertEqual(context["goal"]["status"], "ACTIVE")
        self.assertEqual(context["goal"]["evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
