import os
import unittest
from unittest.mock import patch

from gemini_agent.client import GeminiClient


class ConstructedActionRoutingTest(unittest.TestCase):
    def test_explicit_structured_action_routes_directly(self):
        calls = []

        def handler(**kwargs):
            calls.append(kwargs)
            return "Constructed action execution: Exit code: 0"

        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient(tool_handlers={"execute_constructed_action": handler})
            answer = client.ask(
                'Execute a newly constructed workspace action: '
                'executable=touch, arguments=["proof.txt"], working_directory=., '
                'timeout_seconds=5, mutation_scope=WORKSPACE_MUTATION, '
                'expected_effects=["proof.txt exists"], '
                'evidence_requirements=["exit code is 0","artifact exists"]; '
                'use no shell syntax or interpreter.'
            )

        self.assertIn("Exit code: 0", answer)
        self.assertEqual(calls[0]["executable"], "touch")
        self.assertEqual(calls[0]["arguments"], ["proof.txt"])
        self.assertEqual(calls[0]["timeout_seconds"], 5)
        self.assertEqual(calls[0]["mutation_scope"], "WORKSPACE_MUTATION")
        open_url.assert_not_called()


if __name__ == "__main__":
    unittest.main()
