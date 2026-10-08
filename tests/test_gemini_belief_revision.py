import unittest

from gemini_agent.belief_revision import revise_world_beliefs


class BeliefRevisionTests(unittest.TestCase):
    def setUp(self):
        self.entities = (
            "battery | device | 82 percent | 100\n"
            "nova | agent | active | 90"
        )

    def test_confirms_supported_belief(self):
        result = revise_world_beliefs(
            self.entities,
            "battery | battery level is 82 percent | 80",
            "battery | battery level is 82 percent | Android system state | 95 | SUPPORTS",
        )
        self.assertIn("decision: CONFIRMED", result)
        self.assertIn("confidence: 95", result)
        self.assertIn("Android system state", result)

    def test_revises_from_higher_confidence_contradiction(self):
        result = revise_world_beliefs(
            self.entities,
            "battery | battery level is 82 percent | 80",
            "battery | battery level is 41 percent | Android system state | 95 | CONTRADICTS",
        )
        self.assertIn("revised_to: battery level is 41 percent", result)
        self.assertIn("decision: REVISED", result)

    def test_equal_confidence_contradiction_requires_human_input(self):
        result = revise_world_beliefs(
            self.entities,
            "battery | battery level is 82 percent | 90",
            "battery | battery level is 41 percent | Android system state | 90 | CONTRADICTS",
        )
        self.assertIn("HUMAN INPUT REQUIRED", result)

    def test_weaker_contradiction_does_not_revise(self):
        result = revise_world_beliefs(
            self.entities,
            "battery | battery level is 82 percent | 90",
            "battery | battery level is 41 percent | Android system state | 80 | CONTRADICTS",
        )
        self.assertIn("decision: UNCHANGED", result)
        self.assertIn("contradictory evidence is weaker", result)

    def test_unrelated_evidence_does_not_change_belief(self):
        result = revise_world_beliefs(
            self.entities,
            "nova | agent is active | 90",
            "nova | agent is ready | runtime state | 95 | SUPPORTS",
        )
        self.assertIn("decision: UNCHANGED", result)
        self.assertIn("does not explicitly support or contradict", result)

    def test_rejects_unknown_belief_entity(self):
        with self.assertRaises(ValueError):
            revise_world_beliefs(
                self.entities,
                "missing | unknown state | 80",
                "battery | battery level is 82 percent | system | 90 | SUPPORTS",
            )

    def test_rejects_unknown_evidence_entity(self):
        with self.assertRaises(ValueError):
            revise_world_beliefs(
                self.entities,
                "battery | battery level is 82 percent | 80",
                "missing | battery level is 41 percent | system | 95 | CONTRADICTS",
            )

    def test_rejects_invalid_stance(self):
        with self.assertRaises(ValueError):
            revise_world_beliefs(
                self.entities,
                "battery | battery level is 82 percent | 80",
                "battery | battery level is 41 percent | system | 95 | MAYBE",
            )

    def test_rejects_duplicate_beliefs(self):
        with self.assertRaises(ValueError):
            revise_world_beliefs(
                self.entities,
                "battery | battery level is 82 percent | 80\n"
                "battery | battery level is 82 percent | 80",
                "battery | battery level is 82 percent | system | 95 | SUPPORTS",
            )

    def test_read_only_boundary_is_explicit(self):
        result = revise_world_beliefs(
            self.entities,
            "battery | battery level is 82 percent | 80",
            "battery | battery level is 82 percent | system | 95 | SUPPORTS",
        )
        self.assertIn("no missing evidence, claim, source, or state was inferred", result)
        self.assertIn("No entity state", result)


if __name__ == "__main__":
    unittest.main()
