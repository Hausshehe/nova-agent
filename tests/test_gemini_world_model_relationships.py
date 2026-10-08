import unittest

from gemini_agent.world_model import represent_entity_relationships, represent_world_evidence, represent_temporal_states


class WorldModelRelationshipTests(unittest.TestCase):
    def test_represents_explicit_relationships(self):
        result = represent_entity_relationships(
            "battery | device | 82 percent | 100\n"
            "nova | agent | active | 90",
            "battery | powers | nova",
        )
        self.assertIn("Entity count: 2", result)
        self.assertIn("Relationship count: 1", result)
        self.assertIn("battery | powers | nova", result)
        self.assertIn("no missing relationship was inferred", result)
        self.assertIn("device state", result)

    def test_rejects_unknown_source_entity(self):
        with self.assertRaises(ValueError):
            represent_entity_relationships(
                "battery | device | 82 percent | 100",
                "missing | powers | battery",
            )

    def test_rejects_unknown_target_entity(self):
        with self.assertRaises(ValueError):
            represent_entity_relationships(
                "battery | device | 82 percent | 100",
                "battery | powers | missing",
            )

    def test_rejects_duplicate_relationships(self):
        with self.assertRaises(ValueError):
            represent_entity_relationships(
                "battery | device | 82 percent | 100\n"
                "nova | agent | active | 90",
                "battery | powers | nova\n"
                "battery | powers | nova",
            )

    def test_rejects_malformed_relationship(self):
        with self.assertRaises(ValueError):
            represent_entity_relationships(
                "battery | device | 82 percent | 100\n"
                "nova | agent | active | 90",
                "battery | powers",
            )

    def test_represents_explicit_evidence_and_provenance(self):
        result = represent_world_evidence(
            "battery | device | 82 percent | 100\n"
            "nova | agent | active | 90",
            "battery | battery state was reported as 82 percent | user | 100",
        )
        self.assertIn("World evidence and provenance representation (read-only):", result)
        self.assertIn("Evidence count: 1", result)
        self.assertIn("battery state was reported as 82 percent", result)
        self.assertIn("source: user", result)
        self.assertIn("no claim, source, relationship, or state was inferred", result)

    def test_rejects_evidence_for_unknown_entity(self):
        with self.assertRaises(ValueError):
            represent_world_evidence(
                "battery | device | 82 percent | 100",
                "missing | battery state was reported as 82 percent | user | 100",
            )

    def test_rejects_duplicate_evidence(self):
        with self.assertRaises(ValueError):
            represent_world_evidence(
                "battery | device | 82 percent | 100",
                "battery | battery state was reported as 82 percent | user | 100\n"
                "battery | battery state was reported as 82 percent | user | 100",
            )

    def test_rejects_malformed_evidence(self):
        with self.assertRaises(ValueError):
            represent_world_evidence(
                "battery | device | 82 percent | 100",
                "battery | battery state was reported as 82 percent | user",
            )


    def test_represents_explicit_temporal_states(self):
        result = represent_temporal_states(
            "battery | device | 82 percent | 100\n"
            "nova | agent | active | 90",
            "battery | 82 percent | 2026-10-08T18:00:00+03:00 | 95\n"
            "nova | active | 2026-10-08T18:05:00+03:00 | 90",
        )
        self.assertIn("Temporal state representation (read-only):", result)
        self.assertIn("Entity count: 2", result)
        self.assertIn("Observation count: 2", result)
        self.assertIn("battery | state: 82 percent | observed_at: 2026-10-08T18:00:00+03:00 | confidence: 95", result)
        self.assertIn("no prior, current, or future state was inferred", result)

    def test_rejects_temporal_observation_for_unknown_entity(self):
        with self.assertRaises(ValueError):
            represent_temporal_states(
                "battery | device | 82 percent | 100",
                "missing | active | 2026-10-08T18:00:00+03:00 | 90",
            )

    def test_rejects_duplicate_temporal_observations(self):
        with self.assertRaises(ValueError):
            represent_temporal_states(
                "battery | device | 82 percent | 100",
                "battery | 82 percent | 2026-10-08T18:00:00+03:00 | 95\n"
                "battery | 82 percent | 2026-10-08T18:00:00+03:00 | 95",
            )

    def test_rejects_malformed_temporal_observation(self):
        with self.assertRaises(ValueError):
            represent_temporal_states(
                "battery | device | 82 percent | 100",
                "battery | 82 percent | 2026-10-08T18:00:00+03:00",
            )


if __name__ == "__main__":
    unittest.main()
