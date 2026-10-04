"""Offline tests for the minimal Gemini client."""

import json
import io
import os
import unittest
import urllib.error
from unittest import mock
from unittest.mock import patch

from gemini_agent.client import GeminiClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class GeminiClientTests(unittest.TestCase):
    def test_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                GeminiClient()

    def test_extracts_response_text(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen", return_value=FakeResponse(payload)
        ) as open_url:
            answer = GeminiClient().ask("Hi")
        self.assertEqual(answer, "Hello")
        request = open_url.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data)["contents"][0]["parts"][0]["text"], "Hi")

    def test_sends_conversation_history(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "Two"}]}}]}
        history = [
            {"role": "user", "parts": [{"text": "One"}]},
            {"role": "model", "parts": [{"text": "First reply"}]},
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen", return_value=FakeResponse(payload)
        ) as open_url:
            GeminiClient().ask("Continue", history)
        sent = json.loads(open_url.call_args.args[0].data)["contents"]
        self.assertEqual([item["role"] for item in sent], ["user", "model", "user"])
        self.assertEqual(sent[-1]["parts"][0]["text"], "Continue")

    def test_sends_system_instruction(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen", return_value=FakeResponse(payload)
        ) as open_url:
            GeminiClient().ask("Hi", system_instruction="You are Nova.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(
            sent["system_instruction"]["parts"][0]["text"],
            "You are Nova.",
        )

    def test_uses_calculator_tool(self):
        tool_call = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "functionCall": {
                            "name": "calculator",
                            "args": {"expression": "12 * 7"},
                        }
                    }]
                }
            }]
        }
        final = {
            "candidates": [{
                "content": {"parts": [{"text": "84"}]}
            }]
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_call), FakeResponse(final)],
        ) as open_url:
            answer = GeminiClient().ask("What is 12 times 7?")

        self.assertEqual(answer, "84")
        self.assertEqual(open_url.call_count, 2)
        second = json.loads(open_url.call_args_list[1].args[0].data)
        function_response = second["contents"][-1]["parts"][0]["functionResponse"]
        self.assertEqual(function_response["name"], "calculator")
        self.assertEqual(function_response["response"]["result"], "84")

    def test_uses_custom_tool_handler(self):
        tool_call = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "functionCall": {
                            "name": "remember_fact",
                            "args": {"key": "favorite_color", "value": "purple"},
                        }
                    }]
                }
            }]
        }
        final = {
            "candidates": [{
                "content": {"parts": [{"text": "Remembered."}]}
            }]
        }
        remember = mock.Mock(return_value="Remembered favorite_color = purple")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_call), FakeResponse(final)],
        ):
            answer = GeminiClient(tool_handlers={"remember_fact": remember}).ask(
                "Remember my favorite color is purple."
            )

        self.assertEqual(answer, "Remembered.")
        remember.assert_called_once_with(key="favorite_color", value="purple")

    def test_rejects_unexpected_response(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen", return_value=FakeResponse({"candidates": []})
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected response"):
                GeminiClient().ask("Hi")

    def test_falls_back_to_secondary_model_after_503(self):
        error_body = b'{"error":{"message":"busy"}}'
        busy = urllib.error.HTTPError(
            "https://example.test", 503, "busy", {}, io.BytesIO(error_body)
        )
        payload = {"candidates": [{"content": {"parts": [{"text": "Fallback"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=[busy, busy, busy, FakeResponse(payload)],
        ) as open_url, patch("time.sleep"):
            answer = GeminiClient().ask("Hi")

        self.assertEqual(answer, "Fallback")
        self.assertEqual(open_url.call_count, 4)
        first_url = open_url.call_args_list[0].args[0].full_url
        fallback_url = open_url.call_args_list[3].args[0].full_url
        self.assertIn("models/gemini-3.5-flash-lite:", first_url)
        self.assertIn("models/gemini-3.5-flash:", fallback_url)

    def test_falls_back_to_secondary_model_after_429(self):
        error_body = b'{"error":{"message":"quota exceeded"}}'
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {}, io.BytesIO(error_body)
        )
        payload = {"candidates": [{"content": {"parts": [{"text": "Fallback"}]}}]}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=[quota, quota, quota, FakeResponse(payload)],
        ) as open_url, patch("time.sleep"):
            answer = GeminiClient().ask("Hi")

        self.assertEqual(answer, "Fallback")
        self.assertEqual(open_url.call_count, 4)
        first_url = open_url.call_args_list[0].args[0].full_url
        fallback_url = open_url.call_args_list[3].args[0].full_url
        self.assertIn("models/gemini-3.5-flash-lite:", first_url)
        self.assertIn("models/gemini-3.5-flash:", fallback_url)


if __name__ == "__main__":
    unittest.main()
