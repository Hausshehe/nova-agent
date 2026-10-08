import unittest

from gemini_agent.client import GeminiClient
from gemini_agent.tools import TOOL_DECLARATIONS, TOOL_HANDLERS


class GoalPortfolioClientTests(unittest.TestCase):
    def test_client_routes_entity_state_representation_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Represent entities and their states with "battery | device | 82 percent | 100\\n'
            'nova | agent | active | 90". '
            "Do not change any entity or device state."
        )
        self.assertIn("Entity and state representation (read-only):", result)
        self.assertIn("Entity count: 2", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "represent_entity_states")

    def test_entity_state_tool_is_registered_once(self):
        self.assertIn("represent_entity_states", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("represent_entity_states"), 1)

    def test_client_routes_entity_relationships_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Represent relationships between entities with entities "battery | device | 82 percent | 100\\n'
            'nova | agent | active | 90" and relationships "battery | powers | nova". '
            "Do not infer missing relationships or change any state."
        )
        self.assertIn("Entity relationship representation (read-only):", result)
        self.assertIn("Relationship count: 1", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "represent_entity_relationships")

    def test_entity_relationship_tool_is_registered_once(self):
        self.assertIn("represent_entity_relationships", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("represent_entity_relationships"), 1)

    def test_client_routes_world_evidence_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Represent evidence and provenance with entities "battery | device | 82 percent | 100\\n'
            'nova | agent | active | 90" and evidence "battery | battery state was reported as 82 percent | user | 100". '
            "Do not infer claims, sources, relationships, or state, and do not change device state."
        )
        self.assertIn("World evidence and provenance representation (read-only):", result)
        self.assertIn("Evidence count: 1", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "represent_world_evidence")

    def test_world_evidence_tool_is_registered_once(self):
        self.assertIn("represent_world_evidence", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("represent_world_evidence"), 1)

    def test_client_routes_goal_portfolio_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Establish a goal portfolio with "battery | Check battery | Battery status is reported\n'
            'date | Check date | Current date is reported". '
            "Do not prioritize, execute, interrupt, or complete any goal."
        )
        self.assertIn("Goal portfolio established (read-only):", result)
        self.assertIn("Goal count: 2", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "establish_goal_portfolio")
        self.assertIn("no priority", result)

    def test_goal_portfolio_tool_is_registered_once(self):
        self.assertIn("establish_goal_portfolio", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("establish_goal_portfolio"), 1)

    def test_client_routes_goal_portfolio_verification_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Verify goal portfolio with expected goal ids "battery,date" and goals "battery | Check battery | Battery status is reported | ACTIVE | No observations have been collected\\n'
            'date | Check date | Current date is reported | ACTIVE | No observations have been collected". '
            "Do not execute or change any goal or device state."
        )
        self.assertIn("Coherence: VERIFIED", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "verify_goal_portfolio")

    def test_goal_portfolio_verification_tool_is_registered_once(self):
        self.assertIn("verify_goal_portfolio", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("verify_goal_portfolio"), 1)

    def test_client_routes_goal_priority_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Select goal priority from "battery | Check battery | 10 | 1 | 0 | 5\\n'
            'urgent | Handle urgent task | 90 | 8 | 0 | 5". '
            "Do not execute, interrupt, or complete any goal."
        )
        self.assertIn("Selected goal: urgent", result)
        self.assertIn("Priority score:", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "select_goal_priority")


    def test_client_routes_goal_interruption_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Manage goal interruption for "task | ACTIVE | Step 3 complete | PAUSE, RESUME". '
            "Preserve the checkpoint and do not execute or complete the goal."
        )
        self.assertIn("Transition: PAUSE -> PAUSED", result)
        self.assertIn("Transition: RESUME -> ACTIVE", result)
        self.assertIn("Checkpoint preserved: YES", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "manage_goal_interruption")

    def test_client_routes_goal_conflict_resolution_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Resolve goal conflicts from "urgent | Handle urgent task | shared-device | MUST_CONTINUE; '
            'battery | Check battery | shared-device | CAN_DEFER". '
            "Do not execute, interrupt, or complete any goal."
        )
        self.assertIn("battery is safely deferrable", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "resolve_goal_conflicts")

    def test_goal_conflict_tool_is_registered_once(self):
        self.assertIn("resolve_goal_conflicts", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("resolve_goal_conflicts"), 1)

    def test_goal_interruption_tool_is_registered_once(self):
        self.assertIn("manage_goal_interruption", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("manage_goal_interruption"), 1)

    def test_goal_priority_tool_is_registered_once(self):
        self.assertIn("select_goal_priority", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("select_goal_priority"), 1)


    def test_client_routes_belief_revision_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Revise world beliefs for entities "battery | device | 82 percent | 100\\n'
            'nova | agent | active | 90" with beliefs "battery | battery level is 82 percent | 80" '
            'and evidence "battery | battery level is 41 percent | Android system state | 95 | CONTRADICTS". '
            "Do not infer missing evidence or change entity or device state."
        )
        self.assertIn("Belief revision (read-only):", result)
        self.assertIn("decision: REVISED", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "revise_world_beliefs")

    def test_belief_revision_tool_is_registered_once(self):
        self.assertIn("revise_world_beliefs", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("revise_world_beliefs"), 1)


    def test_client_routes_temporal_states_locally(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.tool_declarations = TOOL_DECLARATIONS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        result = client.ask(
            'Represent temporal states for entities "battery | device | 82 percent | 100\\n'
            'nova | agent | active | 90" with observations "battery | 82 percent | 2026-10-08T18:00:00+03:00 | 95\\n'
            'nova | active | 2026-10-08T18:05:00+03:00 | 90". '
            "Do not infer prior, current, or future states, and do not change device state."
        )
        self.assertIn("Temporal state representation (read-only):", result)
        self.assertIn("Observation count: 2", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "represent_temporal_states")

    def test_temporal_state_tool_is_registered_once(self):
        self.assertIn("represent_temporal_states", TOOL_HANDLERS)
        names = [
            item["name"]
            for item in TOOL_DECLARATIONS
            if isinstance(item, dict)
        ]
        self.assertEqual(names.count("represent_temporal_states"), 1)


if __name__ == "__main__":
    unittest.main()
