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


if __name__ == "__main__":
    unittest.main()
