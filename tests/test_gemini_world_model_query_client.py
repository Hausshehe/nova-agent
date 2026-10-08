import unittest

from gemini_agent.client import GeminiClient
from gemini_agent.tools import TOOL_DECLARATIONS, TOOL_HANDLERS


class WorldModelQueryClientTests(unittest.TestCase):
    def _client(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        return client

    def test_client_routes_world_model_query_locally(self):
        client = self._client()
        result = client.ask(
            'Query world model with entities "battery | device | 82 percent | 100\n'
            'nova | agent | active | 90" relationships "battery | powers | nova" '
            'evidence "battery | battery level is 82 percent | Android system state | 100" '
            'temporal states "battery | 82 percent | 2026-10-08T18:00:00+03:00 | 95" '
            'beliefs "battery | battery level is 82 percent | 80" '
            'query "battery". Do not infer missing facts or change any state.'
        )
        self.assertIn("World-model query (read-only):", result)
        self.assertIn("Answer status: SUPPORTED_BY_SUPPLIED_RECORDS", result)
        self.assertIn("RELATIONSHIP: battery | powers | nova", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "query_world_model")

    def test_client_routes_unknown_query_without_inference(self):
        client = self._client()
        result = client.ask(
            'Query world model with entities "battery | device | 82 percent | 100" '
            'relationships "" evidence "" temporal states "" beliefs "" '
            'query "battery temperature". Do not infer missing facts or change any state.'
        )
        self.assertIn("Answer status: UNKNOWN_OR_UNSUPPORTED", result)
        self.assertIn("no missing fact was inferred", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "query_world_model")

    def test_world_model_query_tool_is_registered_once(self):
        self.assertIn("query_world_model", TOOL_HANDLERS)
        names = [item["name"] for item in TOOL_DECLARATIONS if isinstance(item, dict)]
        self.assertEqual(names.count("query_world_model"), 1)


if __name__ == "__main__":
    unittest.main()
