import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gemini_agent.client import GeminiClient
from gemini_agent.goal_state import start_goal_state
from gemini_agent.goal_state_store import save_goal_state


class GoalResumeIntegrationTests(unittest.TestCase):
    def test_resume_restores_active_goal_and_supplies_prior_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "active_goal.json"
            state = start_goal_state("Build a calculator app", "APK built and arithmetic UI verified")
            state.add_evidence("First attempt failed because the build command was unavailable")
            state.record_step("gradle", "FAILED", "Executable not found")
            state.record_recovery("Inspected available build tools")
            save_goal_state(state, store)
            with patch.dict(os.environ, {
                "NOVA_GOAL_STATE_PATH": str(store),
                "CLOUDFLARE_API_TOKEN": "test-token",
                "CLOUDFLARE_ACCOUNT_ID": "test-account",
            }):
                client = GeminiClient()
                with patch.object(client, "_generate_cloudflare", return_value="continued") as generate:
                    result = client.ask("/resume")

            self.assertEqual(result, "continued")
            self.assertEqual(client.goal_state.goal, "Build a calculator app")
            self.assertEqual(client.goal_state.success_condition, "APK built and arithmetic UI verified")
            sent = generate.call_args.args[0][-1]["parts"][0]["text"]
            self.assertIn("First attempt failed", sent)
            self.assertIn("gradle: FAILED", sent)
            self.assertIn("Inspect current reality", sent)

    def test_resume_without_active_goal_does_not_call_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "missing.json"
            with patch.dict(os.environ, {
                "NOVA_GOAL_STATE_PATH": str(store),
                "CLOUDFLARE_API_TOKEN": "test-token",
                "CLOUDFLARE_ACCOUNT_ID": "test-account",
            }):
                client = GeminiClient()
                with patch.object(client, "_generate_cloudflare") as generate:
                    result = client.ask("/resume")
            self.assertIn("No persisted active goal", result)
            generate.assert_not_called()
