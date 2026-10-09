"""CLI wiring tests for conversation context continuity."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout
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
                request_calls.append((prompt, history, system_instruction))
                return next(answers)

        inputs = iter(["first question", "second question", "/exit"])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True), patch.object(agent_main, "ConversationMemory", FakeMemory), patch.object(agent_main, "GeminiClient", FakeClient), patch("builtins.input", side_effect=lambda _: next(inputs)):
            agent_main.main()

        self.assertEqual(request_calls[1][0], "second question")
        self.assertIn("first call list_saved_workflows", request_calls[0][2])
        self.assertIn("inspect_saved_workflow by its exact name", request_calls[0][2])
        self.assertIn("Execute a saved workflow by exact name only when its real behavior fits", request_calls[0][2])
        self.assertIn("Never claim a workflow ran or a verification occurred", request_calls[0][2])
        self.assertIn("execute every required action, including each independent verification", request_calls[0][2])
        self.assertIn("compare each claimed action with the recorded tool results", request_calls[0][2])
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

    def test_prints_actual_recorded_workflow_result(self):
        workflow_result = {
            "status": "completed",
            "steps_completed": 2,
            "steps": [
                {"step": 0, "tool": "calculator", "status": "completed", "result": "42"},
                {"step": 1, "tool": "calculator", "status": "completed", "result": "42"},
            ],
        }

        class FakeClient:
            last_tool_calls = [{
                "name": "run_workflow",
                "args": {"steps": [{"tool": "calculator"}, {"tool": "calculator"}]},
                "result": json.dumps(workflow_result),
            }]

        output = io.StringIO()
        with redirect_stdout(output):
            agent_main._print_workflow_execution_evidence(FakeClient())

        rendered = output.getvalue()
        self.assertIn("Execution evidence (local run_workflow result)", rendered)
        self.assertIn('"status": "completed"', rendered)
        self.assertIn('"steps_completed": 2', rendered)
        self.assertEqual(rendered.count('"result": "42"'), 2)

    def test_prints_discovery_and_calculator_evidence_when_no_workflow_runs(self):
        class FakeClient:
            last_tool_calls = [
                {
                    "name": "list_saved_workflows",
                    "args": {},
                    "result": '[{"name":"persistence-check","description":"Verify reusable workflow persistence"}]',
                },
                {
                    "name": "inspect_saved_workflow",
                    "args": {"name": "persistence-check"},
                    "result": '{"name":"persistence-check","steps":[{"index":0,"tool":"calculator","arguments":{"expression":"6 * 7"}}]}',
                },
                {
                    "name": "calculator",
                    "args": {"expression": "19 * 23"},
                    "result": "437",
                },
                {
                    "name": "calculator",
                    "args": {"expression": "437"},
                    "result": "437",
                },
            ]

        output = io.StringIO()
        with redirect_stdout(output):
            agent_main._print_workflow_execution_evidence(FakeClient())

        rendered = output.getvalue()
        self.assertIn("Execution evidence (local direct-tool results)", rendered)
        self.assertIn("list_saved_workflows", rendered)
        self.assertIn("inspect_saved_workflow", rendered)
        self.assertIn("6 * 7", rendered)
        self.assertIn("persistence-check", rendered)
        self.assertIn('"expression": "19 * 23"', rendered)
        self.assertIn('"expression": "437"', rendered)
        self.assertEqual(rendered.count('"result": "437"'), 2)

    def test_prints_actual_recorded_saved_workflow_result(self):
        workflow_result = {
            "status": "completed",
            "steps_completed": 1,
            "steps": [
                {"step": 0, "tool": "calculator", "status": "completed", "result": "42"},
            ],
        }

        class FakeClient:
            last_tool_calls = [{
                "name": "run_saved_workflow",
                "args": {"name": "persistence-check"},
                "result": json.dumps(workflow_result),
            }]

        output = io.StringIO()
        with redirect_stdout(output):
            agent_main._print_workflow_execution_evidence(FakeClient())

        rendered = output.getvalue()
        self.assertIn("Execution evidence (local run_saved_workflow result)", rendered)
        self.assertIn('"status": "completed"', rendered)
        self.assertIn('"steps_completed": 1', rendered)
        self.assertIn('"result": "42"', rendered)


if __name__ == "__main__":
    unittest.main()
