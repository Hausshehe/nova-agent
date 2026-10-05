"""Offline tests for the single-provider Cloudflare Nova client."""

import io
import json
import os
import unittest
import urllib.error
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


class CloudflareClientTests(unittest.TestCase):
    def test_requires_cloudflare_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "CLOUDFLARE_API_TOKEN"):
                GeminiClient()

    def test_uses_cloudflare_only(self):
        with patch.dict(
            os.environ,
            {
                "CLOUDFLARE_API_TOKEN": "token",
                "CLOUDFLARE_ACCOUNT_ID": "account",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=FakeResponse({"choices": [{"message": {"content": "hello"}}]}),
        ) as open_url:
            answer = GeminiClient().ask("Hello")
        self.assertEqual(answer, "hello")
        self.assertEqual(open_url.call_count, 1)
        self.assertIn("/accounts/account/ai/v1/chat/completions", open_url.call_args.args[0].full_url)

    def test_uses_calculator_tool(self):
        tool_response = {"choices": [{"message": {"content": "", "tool_calls": [{
            "id": "call-1", "type": "function",
            "function": {"name": "calculator", "arguments": '{"expression":"17 * 23"}'},
        }]}}]}
        final_response = {"choices": [{"message": {"content": "391"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Use the calculator tool to calculate 17 * 23.")
        self.assertEqual(answer, "391")
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(
            client.last_tool_calls,
            [{"name": "calculator", "args": {"expression": "17 * 23"}, "result": "391", "expression": "17 * 23"}],
        )
        follow_up = json.loads(open_url.call_args_list[1].args[0].data)
        self.assertNotIn("tools", follow_up)
        self.assertNotIn("tool_choice", follow_up)

    def test_explicit_tool_is_selected(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Use the delete_file tool to delete test.txt.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual([t["function"]["name"] for t in sent["tools"]], ["delete_file"])
        self.assertEqual(sent["tool_choice"], {"type": "function", "function": {"name": "delete_file"}})

    def test_filesystem_request_requires_tool(self):
        response = {"choices": [{"message": {"content": "ok"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", return_value=FakeResponse(response)) as open_url:
            GeminiClient().ask("Please read this file.")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(sent["tool_choice"], "required")

    def test_accepts_decoded_tool_arguments(self):
        tool_response = {"choices": [{"message": {"content": "", "tool_calls": [{
            "id": "call-1", "type": "function",
            "function": {"name": "calculator", "arguments": {"expression": "12 * 7"}},
        }]}}]}
        final_response = {"choices": [{"message": {"content": "84"}}]}
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ):
            self.assertEqual(GeminiClient().ask("Calculate 12 * 7."), "84")

    def test_cloudflare_http_error(self):
        error = urllib.error.HTTPError(
            "https://example.test", 400, "bad request", {},
            io.BytesIO(b'{"error":{"message":"bad"}}'),
        )
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, r"Cloudflare API error \(400\)"):
                GeminiClient().ask("Hello")


if __name__ == "__main__":
    unittest.main()
