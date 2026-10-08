import ast
from pathlib import Path
import unittest


class CloudflareToolCallPolicyTests(unittest.TestCase):
    def test_adaptive_investigation_has_a_bounded_sixteen_round_ceiling(self):
        source = (
            Path(__file__).resolve().parents[1] / "gemini_agent" / "client.py"
        ).read_text(encoding="utf-8")

        self.assertIn("max_tool_rounds = 16", source)
        self.assertNotIn("max_tool_rounds = 8", source)

    def test_adaptive_investigation_requires_mechanism_substitution_after_failure(self):
        source = (
            Path(__file__).resolve().parents[1] / "gemini_agent" / "client.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        policy_nodes = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "decision_policy"
                for target in node.targets
            )
        ]
        self.assertEqual(len(policy_nodes), 1)

        policy = ast.literal_eval(policy_nodes[0])
        required_fragments = (
            "Adaptive investigation rule:",
            "unavailable, blocked, failed, or inconclusive observation mechanism",
            "requested fact is unknowable",
            "identify and try a distinct already-registered mechanism",
            "while preserving read-only and safety constraints",
            "Do not stop merely because the first diagnostic path is blocked",
            "Stop only after the fact is verified",
            "available mechanisms have been meaningfully exhausted",
        )
        for fragment in required_fragments:
            self.assertIn(fragment, policy)

    def test_tool_runtime_failures_enter_adaptive_investigation(self):
        source = (
            Path(__file__).resolve().parents[1] / "gemini_agent" / "client.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        catches_runtime_error = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not isinstance(node.type, ast.Tuple):
                continue
            names = {
                item.id
                for item in node.type.elts
                if isinstance(item, ast.Name)
            }
            if "RuntimeError" in names:
                catches_runtime_error.append(node)

        self.assertTrue(catches_runtime_error)
        matching_handlers = [
            ast.get_source_segment(source, node)
            for node in catches_runtime_error
            if "Tool error:" in (ast.get_source_segment(source, node) or "")
            and "tool_result" in (ast.get_source_segment(source, node) or "")
        ]
        self.assertTrue(matching_handlers)


    def test_adaptive_investigation_stops_on_identical_observation_round(self):
        source = (
            Path(__file__).resolve().parents[1] / "gemini_agent" / "client.py"
        ).read_text(encoding="utf-8")

        required_fragments = (
            "last_observation_signature = None",
            "round_trace_start = len(self.last_tool_calls)",
            "round_observations = self.last_tool_calls[round_trace_start:]",
            'if observation_signature == last_observation_signature:',
            "The latest investigation round repeated exactly the same",
            "use a genuinely distinct safe mechanism only if it can add",
            'payload.pop("tools", None)',
            'payload.pop("tool_choice", None)',
        )
        for fragment in required_fragments:
            self.assertIn(fragment, source)

    def test_cloudflare_tool_rounds_serialize_tool_calls(self):
        source = (
            Path(__file__).resolve().parents[1] / "gemini_agent" / "client.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        matches = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            keys = [
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant)
            ]
            if "parallel_tool_calls" in keys:
                index = keys.index("parallel_tool_calls")
                matches.append(node.value.values[index])

        self.assertEqual(len(matches), 1)
        self.assertIsInstance(matches[0], ast.Constant)
        self.assertIs(matches[0].value, False)


if __name__ == "__main__":
    unittest.main()