"""Offline tests for the minimal Gemini client."""

import json
import os
import unittest
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

    def test_rejects_unexpected_response(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen", return_value=FakeResponse({"candidates": []})
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected response"):
                GeminiClient().ask("Hi")


if __name__ == "__main__":
    unittest.main()
