import ast
from pathlib import Path
import unittest


class CloudflareToolCallPolicyTests(unittest.TestCase):
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
