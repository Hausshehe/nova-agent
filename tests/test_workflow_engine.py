"""Deterministic tests for reusable Nova workflow composition."""

import json
import unittest

from gemini_agent.workflow_engine import execute_workflow


class WorkflowEngineTests(unittest.TestCase):
    def setUp(self):
        self.handlers = {
            "source": lambda value: f"VALUE:{value}",
            "consume": lambda value, suffix="": f"{value}{suffix}",
            "fail": lambda: (_ for _ in ()).throw(RuntimeError("expected failure")),
            "after": lambda: "SHOULD NOT RUN",
        }
        self.allowed = set(self.handlers)

    def test_two_distinct_workflows_reuse_same_engine_and_pass_results(self):
        first = execute_workflow(
            [
                {"tool": "source", "arguments": {"value": "alpha"}},
                {"tool": "consume", "arguments": {"value": {"$step_result": 0}, "suffix": ":checked"}},
            ],
            self.handlers,
            allowed_tools=self.allowed,
        )
        second = execute_workflow(
            [
                {"tool": "source", "arguments": {"value": "beta"}},
                {"tool": "consume", "arguments": {"value": {"$step_result": 0}, "suffix": ":verified"}},
            ],
            self.handlers,
            allowed_tools=self.allowed,
        )
        a, b = json.loads(first), json.loads(second)
        self.assertEqual(a["status"], "completed")
        self.assertEqual(a["steps"][1]["result"], "VALUE:alpha:checked")
        self.assertEqual(b["status"], "completed")
        self.assertEqual(b["steps"][1]["result"], "VALUE:beta:verified")

    def test_failure_stops_later_steps_and_is_not_reported_as_success(self):
        result = json.loads(execute_workflow(
            [
                {"tool": "source", "arguments": {"value": "x"}},
                {"tool": "fail", "arguments": {}},
                {"tool": "after", "arguments": {}},
            ],
            self.handlers,
            allowed_tools=self.allowed,
        ))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["steps_completed"], 1)
        self.assertEqual(result["steps"][-1]["status"], "failed")
        self.assertNotIn("SHOULD NOT RUN", json.dumps(result))

    def test_unknown_or_disallowed_tool_is_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, "not allowed"):
            execute_workflow(
                [{"tool": "after", "arguments": {}}],
                self.handlers,
                allowed_tools={"source"},
            )

    def test_forward_or_missing_step_reference_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "earlier completed step"):
            execute_workflow(
                [{"tool": "consume", "arguments": {"value": {"$step_result": 0}}}],
                self.handlers,
                allowed_tools=self.allowed,
            )

    def test_step_count_is_bounded(self):
        steps = [{"tool": "source", "arguments": {"value": "x"}}] * 9
        with self.assertRaisesRegex(ValueError, "step limit"):
            execute_workflow(steps, self.handlers, allowed_tools=self.allowed)


    def test_registered_workflow_tool_composes_real_read_only_capabilities(self):
        from gemini_agent.tools import RUN_WORKFLOW_DECLARATION, TOOL_DECLARATIONS, TOOL_HANDLERS

        self.assertIs(TOOL_HANDLERS["run_workflow"], __import__("gemini_agent.tools", fromlist=["run_workflow"]).run_workflow)
        self.assertIn(RUN_WORKFLOW_DECLARATION, TOOL_DECLARATIONS)
        self.assertEqual(RUN_WORKFLOW_DECLARATION["parameters"]["properties"]["steps"]["type"], "ARRAY")
        steps = [
            {"tool": "calculator", "arguments": {"expression": "6 * 7"}},
            {"tool": "calculator", "arguments": {"expression": {"$step_result": 0}}},
        ]
        result = json.loads(TOOL_HANDLERS["run_workflow"](steps=steps))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["steps"][0]["result"], "42")
        self.assertEqual(result["steps"][1]["result"], "42")
        # Preserve compatibility for existing callers that pass JSON text.
        text_result = json.loads(TOOL_HANDLERS["run_workflow"](steps=json.dumps(steps)))
        self.assertEqual(text_result["status"], "completed")
        self.assertEqual(text_result["steps"][1]["result"], "42")

    def test_public_workflow_tool_cannot_run_mutating_capabilities(self):
        from gemini_agent.tools import run_workflow

        with self.assertRaisesRegex(ValueError, "not allowed"):
            run_workflow(json.dumps([
                {"tool": "write_text_file", "arguments": {"path": "workflow-test.txt", "content": "no"}}
            ]))


    def test_invalid_later_step_is_rejected_before_any_handler_runs(self):
        calls = []
        handlers = {
            "source": lambda: calls.append("ran") or "ok",
        }
        with self.assertRaisesRegex(ValueError, "not allowed"):
            execute_workflow(
                [
                    {"tool": "source", "arguments": {}},
                    {"tool": "forbidden", "arguments": {}},
                ],
                handlers,
                allowed_tools={"source"},
            )
        self.assertEqual(calls, [])

    def test_named_workflow_save_list_reload_and_execute(self):
        import os
        import tempfile
        from unittest.mock import patch
        from gemini_agent.tools import save_workflow, list_saved_workflows, run_saved_workflow

        steps = [
            {"tool": "calculator", "arguments": {"expression": "6 * 7"}},
            {"tool": "calculator", "arguments": {"expression": {"$step_result": 0}}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            store = os.path.join(directory, "workflows.json")
            with patch.dict(os.environ, {"NOVA_WORKFLOW_STORE": store}):
                self.assertIn('"status":"saved"', save_workflow("double_check", steps, "Two-step calculation"))
                listed = json.loads(list_saved_workflows())
                self.assertEqual(listed["count"], 1)
                self.assertEqual(listed["workflows"][0]["name"], "double_check")
                # Simulate a fresh load by invoking only through the persisted store API.
                result = json.loads(run_saved_workflow("double_check"))
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["steps_completed"], 2)
                self.assertEqual([step["result"] for step in result["steps"]], ["42", "42"])
                with self.assertRaisesRegex(ValueError, "already exists"):
                    save_workflow("double_check", steps)
                with self.assertRaisesRegex(ValueError, "not found"):
                    run_saved_workflow("missing")

    def test_named_workflow_rejects_disallowed_tool_without_persisting(self):
        import os
        import tempfile
        from unittest.mock import patch
        from gemini_agent.tools import save_workflow, list_saved_workflows

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_WORKFLOW_STORE": os.path.join(directory, "workflows.json")}):
                with self.assertRaisesRegex(ValueError, "not allowed"):
                    save_workflow("unsafe", [
                        {"tool": "write_text_file", "arguments": {"path": "x", "content": "y"}}
                    ])
                self.assertEqual(json.loads(list_saved_workflows())["count"], 0)


if __name__ == "__main__":
    unittest.main()
