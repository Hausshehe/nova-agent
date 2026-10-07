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
        self.assertEqual(snapshot["status"], "VERIFIED")
        self.assertEqual(snapshot["progress_status"], "PROGRESS")
        self.assertEqual(len(snapshot["evidence"]), 1)

    def test_active_goal_selects_and_executes_one_bounded_next_step(self):
        responses = [
            {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "goal-next-step",
                            "type": "function",
                            "function": {
                                "name": "get_system_battery_status",
                                "arguments": "{}",
                            },
                        }]
                    }
                }]
            },
            {
                "choices": [{"message": {"content": "Battery goal verified."}}],
            },
        ]
        calls = {"count": 0}

        def battery():
            calls["count"] += 1
            return "Level: 82% Status: Charging Power source: Battery"

        def urlopen(_request, timeout=180):
            del timeout
            response = _FakeResponse(responses[calls["count"]])
            return response

        with patch.dict(
            os.environ,
            {
                "CLOUDFLARE_API_TOKEN": "token",
                "CLOUDFLARE_ACCOUNT_ID": "account",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=urlopen,
        ):
            client = GeminiClient(tool_handlers={"get_system_battery_status": battery})
            result = client.ask(
                'Establish a goal contract for "check the device battery" with success condition '
                '"the current battery status is successfully reported". '
                "Pursue this goal autonomously. Do not ask me to name a tool."
            )

        self.assertEqual(calls["count"], 1)
        self.assertIn("Goal progress observation: PROGRESS", result)
        self.assertIn("Goal completion verification: VERIFIED", result)
        self.assertIsNotNone(client.goal_state)
        self.assertEqual(client.goal_state.status, "VERIFIED")
        self.assertTrue(
            any(call["name"] == "select_goal_next_step" for call in client.last_tool_calls)
        )


    def test_active_goal_continues_to_a_distinct_next_step(self):
        responses = [
            {
                "choices": [{"message": {"tool_calls": [{
                    "id": "battery-step",
                    "type": "function",
                    "function": {"name": "get_system_battery_status", "arguments": "{}"},
                }]}}]
            },
            {
                "choices": [{"message": {"tool_calls": [{
                    "id": "datetime-step",
                    "type": "function",
                    "function": {"name": "current_datetime", "arguments": "{}"},
                }]}}]
            },
            {
                "choices": [{"message": {"content": "Goal verified."}}],
            },
        ]
        calls = {"battery": 0, "datetime": 0, "round": 0}

        def battery():
            calls["battery"] += 1
            return "Level: 82% Status: Charging Power source: Battery"

        def current_datetime():
            calls["datetime"] += 1
            return "2026-10-07T20:00:00+03:00"

        def urlopen(_request, timeout=180):
            del timeout
            response = _FakeResponse(responses[calls["round"]])
            calls["round"] += 1
            return response

        with patch.dict(
            os.environ,
            {
                "CLOUDFLARE_API_TOKEN": "token",
                "CLOUDFLARE_ACCOUNT_ID": "account",
            },
            clear=True,
        ), patch(
            "urllib.request.urlopen",
            side_effect=urlopen,
        ):
            client = GeminiClient(
                tool_handlers={
                    "get_system_battery_status": battery,
                    "current_datetime": current_datetime,
                }
            )
            result = client.ask(
                'Establish a goal contract for "check the battery and current date" with success condition '
                '"the battery status and current date are successfully reported". '
                "Pursue this goal autonomously without asking me to name a tool."
            )

        self.assertEqual(calls["battery"], 1)
        self.assertEqual(calls["datetime"], 1)
        self.assertEqual(calls["round"], 2)
        self.assertIn("Goal completion verification: VERIFIED", result)
        self.assertEqual(client.goal_state.status, "VERIFIED")
        selected = [
            call["result"]
            for call in client.last_tool_calls
            if call["name"] == "select_goal_next_step"
        ]
        self.assertGreaterEqual(len(selected), 2)
        self.assertIn("current_datetime", selected[-1])

    def test_goal_contract_reaches_verified_completion_from_full_evidence(self):
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
                    "get_system_battery_status": lambda: (
                        "Level: 82% Status: Charging "
                        "Power source: Battery"
                    ),
                }
            )
            result = client.ask(
                'Establish a goal contract for "check the device battery" with success condition '
                '"the current battery status is successfully reported". Then use '
                "get_system_battery_status to observe the current battery status."
            )

        self.assertIn("Goal completion verification: VERIFIED", result)
        self.assertIn("Goal completion reason:", result)
        self.assertIsNotNone(client.goal_state)
        snapshot = client.goal_state.snapshot()
        self.assertEqual(snapshot["status"], "VERIFIED")
        self.assertEqual(snapshot["progress_status"], "PROGRESS")
        self.assertEqual(len(snapshot["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()
