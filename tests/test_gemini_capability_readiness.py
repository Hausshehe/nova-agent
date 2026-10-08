import json
import os
import tempfile
import unittest


from gemini_agent.tools import assess_capability_readiness


class CapabilityReadinessTests(unittest.TestCase):
    def test_registered_capability_reports_available_but_unverified_without_verification(self):
        result = assess_capability_readiness("calculator")
        self.assertIn("Declaration: PRESENT", result)
        self.assertIn("Handler: PRESENT and callable", result)
        self.assertIn("Readiness: AVAILABLE_BUT_UNVERIFIED", result)
        self.assertIn("No capability execution", result)


    def test_capability_selection_prefers_direct_supported_evidence(self):
        from gemini_agent.tools import select_capability_by_evidence
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger=os.path.join(temp_dir,"outcomes.json")
            with open(ledger,"w",encoding="utf-8") as handle:
                json.dump([
                    {"capability":"calculator","stage":"VERIFICATION","status":"VERIFIED",
                     "evidence":"Requested capability: calculator\nPost-action verification: VERIFIED. Expected result observed.",
                     "recorded_at":"2026-10-08T00:00:00+00:00"},
                    {"capability":"get_system_battery_status","stage":"VERIFICATION","status":"VERIFIED",
                     "evidence":"Post-action verification: VERIFIED. Battery state observed.",
                     "recorded_at":"2026-10-08T00:00:00+00:00"},
                ],handle)
            with unittest.mock.patch.dict(os.environ,{"NOVA_OUTCOME_LEDGER":ledger},clear=False):
                result=select_capability_by_evidence("get_system_battery_status\ncalculator","perform a calculation")
        self.assertIn("Selected capability: calculator",result)
        self.assertIn("calculator: tier=VERIFIED_SUPPORTED_DIRECT",result)
        self.assertIn("get_system_battery_status: tier=VERIFIED_SUPPORTED_INDIRECT",result)

    def test_capability_selection_rejects_candidates_without_supported_evidence(self):
        from gemini_agent.tools import select_capability_by_evidence
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger=os.path.join(temp_dir,"outcomes.json")
            with open(ledger,"w",encoding="utf-8") as handle: json.dump([],handle)
            with unittest.mock.patch.dict(os.environ,{"NOVA_OUTCOME_LEDGER":ledger},clear=False):
                result=select_capability_by_evidence("calculator\nget_system_battery_status","perform a calculation safely")
        self.assertIn("Selected capability: NONE",result)
        self.assertIn("Decision: NO_SUPPORTED_CANDIDATE",result)

    def test_capability_selection_request_routes_to_evidence_selection(self):
        from gemini_agent.client import GeminiClient
        contents=[{"role":"user","parts":[{"text":"Select the best capability by evidence from calculator and get_system_battery_status for the requirement."}]}]
        self.assertEqual(GeminiClient._requested_local_tool(contents),"select_capability_by_evidence")

    def test_capability_evidence_quality_reports_verified_evidence(self):
        from gemini_agent.tools import assess_capability_evidence_quality

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = os.path.join(temp_dir, "outcomes.json")
            with open(ledger, "w", encoding="utf-8") as handle:
                json.dump([{
                    "capability": "calculator",
                    "stage": "VERIFICATION",
                    "status": "VERIFIED",
                    "evidence": "Post-action verification: VERIFIED. Calculator returned the expected result.",
                    "recorded_at": "2026-10-08T00:00:00+00:00",
                }], handle)
            with unittest.mock.patch.dict(os.environ, {"NOVA_OUTCOME_LEDGER": ledger}, clear=False):
                result = assess_capability_evidence_quality("calculator")

        self.assertIn("Latest verification status: VERIFIED", result)
        self.assertIn("Evidence completeness: SUFFICIENT", result)
        self.assertIn("Prior VERIFIED-to-current regression: NO", result)
        self.assertIn("Quality: SUPPORTED", result)
        self.assertIn("No capability execution", result)

    def test_unknown_capability_reports_unavailable(self):
        result = assess_capability_readiness("nova_missing_capability")
        self.assertIn("Declaration: MISSING", result)
        self.assertIn("Handler: MISSING or INVALID", result)
        self.assertIn("Readiness: UNAVAILABLE", result)

    def test_capability_evidence_provenance_distinguishes_direct_and_indirect_evidence(self):
        from gemini_agent.tools import assess_capability_evidence_provenance

        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = os.path.join(temp_dir, "outcomes.json")
            with open(ledger, "w", encoding="utf-8") as handle:
                json.dump([
                    {
                        "capability": "calculator",
                        "stage": "VERIFICATION",
                        "status": "VERIFIED",
                        "evidence": (
                            "Requested capability: calculator\n"
                            "Post-action verification: VERIFIED. Expected result observed."
                        ),
                    },
                    {
                        "capability": "get_system_battery_status",
                        "stage": "VERIFICATION",
                        "status": "VERIFIED",
                        "evidence": "Post-action verification: VERIFIED. Battery state observed.",
                    },
                    {
                        "capability": "inspect_android_ui",
                        "stage": "VERIFICATION",
                        "status": "VERIFIED",
                        "evidence": (
                            "Requested capability: get_foreground_android_component\n"
                            "Post-action verification: VERIFIED. Foreground component observed."
                        ),
                    },
                ], handle)
            with unittest.mock.patch.dict(os.environ, {"NOVA_OUTCOME_LEDGER": ledger}, clear=False):
                direct = assess_capability_evidence_provenance("calculator")
                indirect = assess_capability_evidence_provenance("get_system_battery_status")
                mismatched = assess_capability_evidence_provenance("inspect_android_ui")

        self.assertIn("Provenance: DIRECTLY_ALIGNED", direct)
        self.assertIn("Provenance: INDIRECT", indirect)
        self.assertIn("Provenance: MISMATCHED", mismatched)
        self.assertIn("No capability execution", direct)

    def test_capability_evidence_provenance_request_routes_to_provenance_self_model(self):
        from gemini_agent.client import GeminiClient

        contents = [{
            "role": "user",
            "parts": [{
                "text": (
                    "Assess capability evidence provenance and determine whether "
                    "the capability verification evidence is directly tied to the capability."
                )
            }],
        }]
        self.assertEqual(
            GeminiClient._requested_local_tool(contents),
            "assess_capability_evidence_provenance",
        )

    def test_capability_evidence_quality_request_routes_to_quality_self_model(self):
        from gemini_agent.client import GeminiClient

        contents = [{
            "role": "user",
            "parts": [{
                "text": (
                    "Check capability verification evidence quality and determine "
                    "whether the capability evidence is sufficient."
                )
            }],
        }]
        self.assertEqual(
            GeminiClient._requested_local_tool(contents),
            "assess_capability_evidence_quality",
        )

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
