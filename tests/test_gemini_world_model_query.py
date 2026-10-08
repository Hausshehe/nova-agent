import unittest

from gemini_agent.world_model_query import query_world_model


ENTITIES = "battery | device | 82 percent | 100\nnova | agent | active | 90"
RELATIONSHIPS = "battery | powers | nova"
EVIDENCE = "battery | battery level is 82 percent | Android system state | 100"
TEMPORAL = "battery | 82 percent | 2026-10-08T18:00:00+03:00 | 95"
BELIEFS = "battery | battery level is 82 percent | 80"


class WorldModelQueryTests(unittest.TestCase):
    def test_returns_explicit_entity_and_related_records(self):
        result = query_world_model(
            ENTITIES, RELATIONSHIPS, EVIDENCE, TEMPORAL, BELIEFS, "battery"
        )
        self.assertIn("Answer status: SUPPORTED_BY_SUPPLIED_RECORDS", result)
        self.assertIn("ENTITY: battery | device | 82 percent | 100", result)
        self.assertIn("RELATIONSHIP: battery | powers | nova", result)
        self.assertIn("EVIDENCE: battery | battery level is 82 percent | Android system state | 100", result)
        self.assertIn("TEMPORAL: battery | 82 percent | 2026-10-08T18:00:00+03:00 | 95", result)
        self.assertIn("BELIEF: battery | battery level is 82 percent | 80", result)

    def test_returns_unknown_without_inference(self):
        result = query_world_model(
            ENTITIES, RELATIONSHIPS, EVIDENCE, TEMPORAL, BELIEFS, "battery temperature"
        )
        self.assertIn("Answer status: UNKNOWN_OR_UNSUPPORTED", result)
        self.assertIn("no missing fact was inferred", result)

    def test_does_not_infer_missing_relationship(self):
        result = query_world_model(
            ENTITIES, "", EVIDENCE, "", "", "nova powers battery"
        )
        self.assertIn("Answer status: UNKNOWN_OR_UNSUPPORTED", result)
        self.assertNotIn("RELATIONSHIP:", result)

    def test_query_is_read_only(self):
        result = query_world_model(
            ENTITIES, RELATIONSHIPS, EVIDENCE, TEMPORAL, BELIEFS, "nova"
        )
        self.assertIn("No entity state, relationship, evidence, temporal observation, belief, action, or device state was changed.", result)

    def test_rejects_empty_query(self):
        with self.assertRaises(ValueError):
            query_world_model(ENTITIES, "", "", "", "", " ")

    def test_bounds_records(self):
        entities = "\n".join(f"e{i} | test | state | 100" for i in range(33))
        with self.assertRaises(ValueError):
            query_world_model(entities, "", "", "", "", "e1")


if __name__ == "__main__":
    unittest.main()
