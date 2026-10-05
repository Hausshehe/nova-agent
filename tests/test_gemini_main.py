"""CLI wiring tests for conversation context continuity."""

import os
import unittest
from unittest.mock import patch

from gemini_agent import main as agent_main


class MainContextTests(unittest.TestCase):
    def test_passes_previous_exchange_into_next_request(self):
        answers = iter(["First answer", "Second answer"])
        request_calls = []
        saved_exchanges = []

        class FakeMemory:
            def __init__(self):
                self.contexts = [[], [
                    {"role": "user", "parts": [{"text": "first question"}]},
                    {"role": "model", "parts": [{"text": "First answer"}]},
                ]]

            def context(self):
                return self.contexts[len(request_calls)]

            def add_exchange(self, prompt, answer):
                saved_exchanges.append((prompt, answer))

            def remember_fact(self, key, value):
                return f"Remembered {key} = {value}"

            def forget_fact(self, key):
                return f"Forgot {key}."

            def list_memory(self):
                return "(no remembered facts)"

        class FakeClient:
            web_search = False
            last_grounding_sources = []

            def __init__(self, **kwargs):
                pass

            def ask(self, prompt, history, system_instruction):
                request_calls.append((prompt, history))
                return next(answers)

        inputs = iter(["first question", "second question", "/exit"])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True), patch.object(agent_main, "ConversationMemory", FakeMemory), patch.object(agent_main, "GeminiClient", FakeClient), patch("builtins.input", side_effect=lambda _: next(inputs)):
            agent_main.main()

        self.assertEqual(request_calls[1][0], "second question")
        self.assertEqual(
            request_calls[1][1],
            [
                {"role": "user", "parts": [{"text": "first question"}]},
                {"role": "model", "parts": [{"text": "First answer"}]},
            ],
        )
        self.assertEqual(
            saved_exchanges,
            [
                ("first question", "First answer"),
                ("second question", "Second answer"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
