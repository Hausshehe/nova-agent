import json
import os
import unittest
from unittest.mock import patch

from gemini_agent.client import GeminiClient


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class GoalProgressIntegrationTests(unittest.TestCase):
    def test_goal_contract_continues_into_tool_outcome_observation(self):
        response = {"choices": [{"message": {"content": "observed"}}]}
        with patch.dict(
            os.environ,
            {
                "CLOUDFLARE_API_TOKEN": "token",
                "CLOUDFLARE_ACCOUNT_ID": "account",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            return_value=_FakeResponse(response),
        ):
            client = GeminiClient(
                tool_handlers={
                    "get_system_battery_status": lambda: "Level: 82% Status: Charging",
                }
            )
            result = client.ask(
                'Establish a goal contract for "check the device battery" with success condition '
                '"the current battery status is successfully reported". Then use '
                "get_system_battery_status to observe the current battery status."
            )

        self.assertIn("Goal progress observation: PROGRESS", result)
        self.assertIsNotNone(client.goal_state)
        snapshot = client.goal_state.snapshot()
        self.assertEqual(snapshot["status"], "ACTIVE")
        self.assertEqual(snapshot["progress_status"], "PROGRESS")
        self.assertEqual(len(snapshot["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()
