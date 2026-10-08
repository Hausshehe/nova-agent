import unittest

from gemini_agent.world_model import represent_entity_relationships


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


if __name__ == "__main__":
    unittest.main()
