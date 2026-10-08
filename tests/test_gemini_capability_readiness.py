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

    def test_capability_readiness_request_routes_to_readiness_self_model(self):
        from gemini_agent.client import GeminiClient

        contents = [{
            "role": "user",
            "parts": [{
                "text": (
                    "Assess your own readiness for the capabilities needed to safely "
                    "determine the current foreground Android app. Determine which "
                    "capabilities are actually available, which are verified, which "
                    "are merely present but unverified, and which are unavailable. "
                    "Use your own capability evidence and persisted verification history."
                )
            }],
        }]
        self.assertEqual(
            GeminiClient._requested_local_tool(contents),
            "assess_capability_readiness",
        )


if __name__ == "__main__":
    unittest.main()
