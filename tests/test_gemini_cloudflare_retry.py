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


if __name__ == "__main__":
    unittest.main()
