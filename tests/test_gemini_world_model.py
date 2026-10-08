import unittest

from gemini_agent.world_model import represent_entity_states


class WorldModelTests(unittest.TestCase):
    def test_represents_multiple_entities_and_states(self):
        result = represent_entity_states(
            "battery | device | 82 percent | 100\n"
            "nova | agent | active | 90"
        )
        self.assertIn("Entity count: 2", result)
        self.assertIn("Entity id: battery", result)
        self.assertIn("State: 82 percent", result)
        self.assertIn("Entity id: nova", result)
        self.assertIn("Confidence: 90", result)
        self.assertIn("No device state was changed.", result)

    def test_rejects_duplicate_entity_ids(self):
        with self.assertRaises(ValueError):
            represent_entity_states(
                "battery | device | 82 percent | 100\n"
                "battery | device | 81 percent | 90"
            )

    def test_rejects_invalid_confidence(self):
        with self.assertRaises(ValueError):
            represent_entity_states("battery | device | 82 percent | 101")

    def test_rejects_malformed_entity(self):
        with self.assertRaises(ValueError):
            represent_entity_states("battery | device | 82 percent")

    def test_bounds_entity_count(self):
        entities = "\n".join(
            f"entity{i} | test | state {i} | 100"
            for i in range(17)
        )
        with self.assertRaises(ValueError):
            represent_entity_states(entities)


if __name__ == "__main__":
    unittest.main()
