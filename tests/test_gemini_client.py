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

    def test_enables_google_search_when_requested(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "Searched"}]}}]}
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GEMINI_WEB_SEARCH": "1"},
            clear=True,
        ), patch(
            "urllib.request.urlopen", return_value=FakeResponse(payload)
        ) as open_url:
            GeminiClient().ask("What happened today?")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(sent["tools"][1], {"google_search": {}})

    def test_extracts_grounding_sources(self):
        payload = {
            "candidates": [{
                "content": {"parts": [{"text": "Answer"}]},
                "groundingMetadata": {
                    "groundingChunks": [
                        {"web": {"title": "Example", "uri": "https://example.com"}}
                    ]
                },
            }]
        }
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GEMINI_WEB_SEARCH": "1"},
            clear=True,
        ), patch(
            "urllib.request.urlopen", return_value=FakeResponse(payload)
        ):
            client = GeminiClient()
            answer = client.ask("Search this")
        self.assertEqual(answer, "Answer")
        self.assertEqual(
            client.last_grounding_sources,
            [{"title": "Example", "uri": "https://example.com"}],
        )

    def test_openrouter_fallback_after_gemini_server_error_without_groq(self):
        busy = urllib.error.HTTPError(
            "https://example.test", 500, "server error", {},
            io.BytesIO(b'{"error":{"message":"server error"}}'),
        )
        response = {
            "choices": [{"message": {"content": "OpenRouter fallback"}}]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "OPENROUTER_API_KEY": "openrouter-key",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[busy, busy, busy, busy, busy, busy, FakeResponse(response)],
        ) as open_url, patch("time.sleep"):
            answer = GeminiClient().ask("Hi")

        self.assertEqual(answer, "OpenRouter fallback")
        self.assertEqual(open_url.call_count, 4)
        self.assertIn(
            "https://openrouter.ai/api/v1/chat/completions",
            open_url.call_args.args[0].full_url,
        )

    def test_groq_fallback_after_gemini_quota(self):
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {},
            io.BytesIO(b'{"error":{"message":"quota exceeded"}}'),
        )
        groq_payload = {
            "choices": [{"message": {"content": "Groq fallback"}}]
        }
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "groq-key"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[quota, quota, quota, quota, quota, quota, FakeResponse(groq_payload)],
        ) as open_url, patch("time.sleep"):
            answer = GeminiClient().ask("Hi")

        self.assertEqual(answer, "Groq fallback")
        self.assertEqual(open_url.call_count, 7)
        groq_request = open_url.call_args.args[0]
        self.assertEqual(groq_request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(groq_request.headers["Authorization"], "Bearer groq-key")

    def test_openrouter_fallback_after_groq_quota(self):
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {},
            io.BytesIO(b'{"error":{"message":"quota exceeded"}}'),
        )
        groq_quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {},
            io.BytesIO(b'{"error":{"message":"groq quota exceeded"}}'),
        )
        openrouter_payload = {
            "choices": [{"message": {"content": "OpenRouter fallback"}}]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "GROQ_API_KEY": "groq-key",
                "OPENROUTER_API_KEY": "openrouter-key",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                quota, quota, quota, quota, quota, quota,
                groq_quota,
                FakeResponse(openrouter_payload),
            ],
        ) as open_url, patch("time.sleep"):
            answer = GeminiClient().ask("Hi")

        self.assertEqual(answer, "OpenRouter fallback")
        self.assertEqual(open_url.call_count, 8)
        request = open_url.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://openrouter.ai/api/v1/chat/completions",
        )
        self.assertEqual(request.headers["Authorization"], "Bearer openrouter-key")

    def test_openrouter_fallback_uses_web_search(self):
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {},
            io.BytesIO(b'{"error":{"message":"quota exceeded"}}'),
        )
        response = {
            "choices": [{"message": {"content": "OpenRouter searched"}}]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "GROQ_API_KEY": "groq-key",
                "OPENROUTER_API_KEY": "openrouter-key",
                "GEMINI_WEB_SEARCH": "1",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                quota, quota, quota, quota, quota, quota,
                quota,
                FakeResponse(response),
            ],
        ) as open_url, patch("time.sleep"):
            answer = GeminiClient().ask("Latest news")

        self.assertEqual(answer, "OpenRouter searched")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(sent["tools"][0], {"type": "openrouter:web_search"})
        self.assertTrue(
            any(tool.get("type") == "function" for tool in sent["tools"])
        )

    def test_openrouter_fallback_extracts_web_sources(self):
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {}, 
            io.BytesIO(b'{"error":{"message":"quota exceeded"}}'),
        )
        response = {
            "choices": [{
                "message": {
                    "content": "OpenRouter searched",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url": "https://example.com/news",
                            "title": "Example News",
                        }
                    ],
                }
            }]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "GROQ_API_KEY": "groq-key",
                "OPENROUTER_API_KEY": "openrouter-key",
                "GEMINI_WEB_SEARCH": "1",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                quota, quota, quota, quota, quota, quota,
                quota,
                FakeResponse(response),
            ],
        ) as open_url, patch("time.sleep"):
            client = GeminiClient()
            answer = client.ask("Latest news")

        self.assertEqual(answer, "OpenRouter searched")
        self.assertEqual(
            client.last_grounding_sources,
            [{"title": "Example News", "uri": "https://example.com/news"}],
        )

    def test_openrouter_fallback_extracts_nested_web_sources(self):
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {},
            io.BytesIO(b'{"error":{"message":"quota exceeded"}}'),
        )
        response = {
            "choices": [{
                "message": {
                    "content": "OpenRouter searched",
                    "annotations": [{
                        "type": "url_citation",
                        "url_citation": {
                            "url": "https://example.com/nested",
                            "title": "Nested News",
                        },
                    }],
                }
            }]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "GROQ_API_KEY": "groq-key",
                "OPENROUTER_API_KEY": "openrouter-key",
                "GEMINI_WEB_SEARCH": "1",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                quota, quota, quota, quota, quota, quota,
                quota,
                FakeResponse(response),
            ],
        ) as open_url, patch("time.sleep"):
            client = GeminiClient()
            answer = client.ask("Latest news")

        self.assertEqual(answer, "OpenRouter searched")
        self.assertEqual(
            client.last_grounding_sources,
            [{"title": "Nested News", "uri": "https://example.com/nested"}],
        )

    def test_groq_fallback_uses_browser_search(self):
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {},
            io.BytesIO(b'{"error":{"message":"quota exceeded"}}'),
        )
        groq_payload = {
            "choices": [{"message": {"content": "Searched fallback"}}]
        }
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "groq-key", "GEMINI_WEB_SEARCH": "1"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[quota, quota, quota, quota, quota, quota, FakeResponse(groq_payload)],
        ) as open_url, patch("time.sleep"):
            answer = GeminiClient().ask("Latest news")

        self.assertEqual(answer, "Searched fallback")
        sent = json.loads(open_url.call_args.args[0].data)
        self.assertEqual(sent["tools"], [{"type": "browser_search"}])
        self.assertEqual(sent["tool_choice"], "required")

    def test_openrouter_fallback_accepts_decoded_tool_arguments(self):
        tool_response = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": {"expression": "12 * 7"},
                        },
                    }],
                }
            }]
        }
        final_response = {
            "choices": [{"message": {"content": "84"}}]
        }
        with patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-key",
                "OPENROUTER_API_KEY": "openrouter-key",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_response), FakeResponse(final_response)],
        ) as open_url:
            client = GeminiClient()
            answer = client._generate_openrouter(
                [{"role": "user", "parts": [{"text": "What is 12 times 7?"}]}],
                None,
            )

        self.assertEqual(answer, "84")
        self.assertEqual(
            client.last_tool_calls,
            [{"name": "calculator", "args": {"expression": "12 * 7"}, "result": "84", "expression": "12 * 7"}],
        )
        second_request = open_url.call_args_list[1].args[0]
        sent = json.loads(second_request.data)
        self.assertEqual(sent["messages"][-1]["content"], "84")

    def test_groq_fallback_uses_local_tool(self):
        quota = urllib.error.HTTPError(
            "https://example.test", 429, "quota", {},
            io.BytesIO(b'{"error":{"message":"quota exceeded"}}'),
        )
        tool_response = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression":"12 * 7"}',
                        },
                    }],
                }
            }]
        }
        final_response = {
            "choices": [{"message": {"content": "84"}}]
        }
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "groq-key"},
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=[
                quota, quota, quota, quota, quota, quota,
                FakeResponse(tool_response),
                FakeResponse(final_response),
            ],
        ) as open_url, patch("time.sleep"):
            client = GeminiClient()
            answer = client.ask("What is 12 times 7?")

        self.assertEqual(answer, "84")
        self.assertEqual(
            client.last_tool_calls,
            [{"name": "calculator", "args": {"expression": "12 * 7"}, "result": "84", "expression": "12 * 7"}],
        )
        groq_request = open_url.call_args_list[6].args[0]
        sent = json.loads(groq_request.data)
        function_tools = [
            tool for tool in sent["tools"]
            if tool.get("type") == "function"
        ]
        self.assertTrue(
            any(tool["function"]["name"] == "calculator" for tool in function_tools)
        )
        second_groq_request = open_url.call_args_list[7].args[0]
        second_sent = json.loads(second_groq_request.data)
        self.assertEqual(second_sent["messages"][-1]["content"], "84")


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

    def test_executes_multiple_gemini_tool_calls(self):
        tool_calls = {
            "candidates": [{
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "calculator",
                                "args": {"expression": "12 * 7"},
                            }
                        },
                        {
                            "functionCall": {
                                "name": "calculator",
                                "args": {"expression": "5 + 6"},
                            }
                        },
                    ]
                }
            }]
        }
        final = {
            "candidates": [{
                "content": {"parts": [{"text": "84 and 11"}]}
            }]
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), patch(
            "urllib.request.urlopen",
            side_effect=[FakeResponse(tool_calls), FakeResponse(final)],
        ) as open_url:
            client = GeminiClient()
            answer = client.ask("Calculate both 12 times 7 and 5 plus 6.")

        self.assertEqual(answer, "84 and 11")
        self.assertEqual(open_url.call_count, 2)
        self.assertEqual(
            client.last_tool_calls,
            [
                {
                    "name": "calculator",
                    "args": {"expression": "12 * 7"},
                    "result": "84",
                    "expression": "12 * 7",
                },
                {
                    "name": "calculator",
                    "args": {"expression": "5 + 6"},
                    "result": "11",
                    "expression": "5 + 6",
                },
            ],
        )
        second = json.loads(open_url.call_args_list[1].args[0].data)
        response_parts = second["contents"][-1]["parts"]
        self.assertEqual(len(response_parts), 2)
        self.assertEqual(
            response_parts[0]["functionResponse"]["response"]["result"],
            "84",
        )
        self.assertEqual(
            response_parts[1]["functionResponse"]["response"]["result"],
            "11",
        )

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
