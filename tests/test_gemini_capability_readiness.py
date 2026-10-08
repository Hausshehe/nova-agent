import unittest

from gemini_agent.tools import assess_capability_readiness


class CapabilityReadinessTests(unittest.TestCase):
    def test_registered_capability_reports_available_but_unverified_without_verification(self):
        result = assess_capability_readiness("calculator")
        self.assertIn("Declaration: PRESENT", result)
        self.assertIn("Handler: PRESENT and callable", result)
        self.assertIn("Readiness: AVAILABLE_BUT_UNVERIFIED", result)
        self.assertIn("No capability execution", result)

    def test_unknown_capability_reports_unavailable(self):
        result = assess_capability_readiness("nova_missing_capability")
        self.assertIn("Declaration: MISSING", result)
        self.assertIn("Handler: MISSING or INVALID", result)
        self.assertIn("Readiness: UNAVAILABLE", result)


if __name__ == "__main__":
    unittest.main()
