import unittest

from gemini_agent.goal_contract import GoalContract, OutcomeContract, establish_goal_contract, establish_outcome_contract
from gemini_agent.client import GeminiClient
from gemini_agent.tools import TOOL_HANDLERS, TOOL_DECLARATIONS, verify_outcome_contract


class GoalContractTests(unittest.TestCase):
    def test_exact_autonomy_boundary_prompt_dispatches_deterministically(self):
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS.copy()
        client.last_tool_calls = []
        client.last_grounding_sources = []
        client.goal_state = None
        prompt = ('Assess the autonomy boundary for the goal "determine whether the current foreground Android app is safely identifiable for a read-only interaction" using only the supplied state; do not execute any capability, inspect the device, change device state, or perform the interaction. The outcome state is "INCONCLUSIVE". The uncertainty is "the foreground target and read-only support are unknown and cannot yet be determined". The observed evidence is "no reliable observation has established the foreground package or activity". The available actions are "investigate by using a bounded read-only observation mechanism". The risk constraints are "low risk, read-only, bounded, non-destructive". Decide whether Nova should STOP, CONTINUE, INVESTIGATE, RECOVER, REPLAN, or ESCALATE, explain the evidence basis, and confirm that nothing was executed.')
        result = client.ask(prompt)
        self.assertIn("Autonomy decision: INVESTIGATE", result)
        self.assertEqual(client.last_tool_calls[-1]["name"], "assess_autonomy_boundary")


    def test_establishes_bounded_goal_contract(self):
        contract = GoalContract("Check battery", "Battery status is reported")
        self.assertEqual(contract.snapshot(), {
            "goal": "Check battery",
            "success_condition": "Battery status is reported",
            "status": "ACTIVE",
        })

    def test_rejects_missing_goal_or_success_condition(self):
        with self.assertRaises(ValueError):
            GoalContract("", "done")
        with self.assertRaises(ValueError):
            GoalContract("goal", "")

    def test_establishes_bounded_outcome_contract(self):
        contract = OutcomeContract(
            "Open the settings page",
            "Settings page is visible",
            "The foreground screen changes to settings",
            "The observed UI identifies the settings page",
            "The foreground screen remains unchanged or shows an error",
            "The UI may be unavailable for direct inspection",
        )
        self.assertEqual(contract.snapshot(), {
            "goal": "Open the settings page",
            "success_condition": "Settings page is visible",
            "expected_transition": "The foreground screen changes to settings",
            "observable_evidence": "The observed UI identifies the settings page",
            "failure_condition": "The foreground screen remains unchanged or shows an error",
            "uncertainty": "The UI may be unavailable for direct inspection",
        })

    def test_establish_outcome_contract_has_no_execution_claim(self):
        result = establish_outcome_contract(
            "Open settings", "Settings is visible",
            "Foreground screen changes to settings",
            "Observed UI identifies settings",
            "Foreground screen remains unchanged or shows an error",
            "UI inspection may be unavailable",
        )
        self.assertIn("Outcome contract established (read-only).", result)
        self.assertIn("Expected transition: Foreground screen changes to settings", result)
        self.assertIn("Observable evidence: Observed UI identifies settings", result)
        self.assertIn("Failure condition: Foreground screen remains unchanged or shows an error", result)
        self.assertIn("Uncertainty: UI inspection may be unavailable", result)
        self.assertIn("no action was executed", result)

    def test_client_routes_explicit_outcome_contract_requests_locally(self):
        contents = [{"role": "user", "parts": [{"text": "Establish an outcome contract for opening settings with the expected transition, observable evidence, failure condition, and uncertainty."}]}]
        self.assertEqual(GeminiClient._requested_local_tool(contents), "establish_outcome_contract")

    def test_outcome_contract_is_registered_once(self):
        self.assertIn("establish_outcome_contract", TOOL_HANDLERS)
        names = [item["name"] for item in TOOL_DECLARATIONS]
        self.assertEqual(names.count("establish_outcome_contract"), 1)
    def test_establish_goal_contract_has_no_execution_claim(self):
        result = establish_goal_contract("Check battery", "Battery status is reported")
        self.assertIn("Goal contract established.", result)
        self.assertIn("Status: ACTIVE", result)
        self.assertIn("no action was executed", result)
        self.assertNotIn("VERIFIED", result)

    def test_client_routes_explicit_goal_contract_requests_locally(self):
        contents = [{
            "role": "user",
            "parts": [{"text": "Establish a goal contract for checking battery with success condition battery status is reported."}],
        }]
        self.assertEqual(
            GeminiClient._requested_local_tool(contents),
            "establish_goal_contract",
        )

    def test_goal_contract_is_registered_once(self):
        self.assertIn("establish_goal_contract", TOOL_HANDLERS)
        names = [item["name"] for item in TOOL_DECLARATIONS]
        self.assertEqual(names.count("establish_goal_contract"), 1)


    def test_verifies_supported_outcome_from_observed_evidence(self):
        result = verify_outcome_contract("Open settings", "Settings page is visible", "Foreground changes to settings", "Observed UI identifies settings", "Settings page is not visible", "Post-action evidence: Settings page is visible and the observed UI identifies settings.")
        self.assertIn("Outcome status: SUPPORTED", result)

    def test_does_not_treat_execution_success_as_outcome_proof(self):
        result = verify_outcome_contract("Open settings", "Settings page is visible", "Foreground changes to settings", "Observed UI identifies settings", "Settings page is not visible", "Tool execution: SUCCESS")
        self.assertIn("Outcome status: INSUFFICIENT", result)

    def test_verifies_contradicted_outcome_from_observed_evidence(self):
        result = verify_outcome_contract("Open settings", "Settings page is visible", "Foreground changes to settings", "Observed UI identifies settings", "Settings page is not visible", "Post-action evidence: Settings page is not visible.")
        self.assertIn("Outcome status: CONTRADICTED", result)

    def test_outcome_verification_is_registered_once(self):
        self.assertIn("verify_outcome_contract", TOOL_HANDLERS)
        names = [item["name"] for item in TOOL_DECLARATIONS]
        self.assertEqual(names.count("verify_outcome_contract"), 1)


    def test_diagnoses_achieved_outcome_and_stops(self):
        from gemini_agent.tools import diagnose_outcome_discrepancy
        result = diagnose_outcome_discrepancy("Open settings", "Settings page is visible", "Foreground changes to settings", "Settings page is not visible", "Post-action evidence: Settings page is visible.")
        self.assertIn("Outcome state: ACHIEVED", result)
        self.assertIn("Next decision: STOP", result)

    def test_diagnoses_mismatch_and_replans(self):
        from gemini_agent.tools import diagnose_outcome_discrepancy
        result = diagnose_outcome_discrepancy("Open settings", "Settings page is visible", "Foreground changes to settings", "Settings page is not visible", "Post-action evidence: Settings page is not visible.")
        self.assertIn("Outcome state: MISMATCH", result)
        self.assertIn("Next decision: REPLAN", result)

    def test_does_not_treat_tool_success_as_outcome(self):
        from gemini_agent.tools import diagnose_outcome_discrepancy
        result = diagnose_outcome_discrepancy("Open settings", "Settings page is visible", "Foreground changes to settings", "Settings page is not visible", "Tool execution: SUCCESS")
        self.assertIn("Outcome state: MISMATCH_OR_UNKNOWN", result)
        self.assertIn("Next decision: REPLAN_OR_VERIFY", result)

    def test_outcome_discrepancy_is_registered_once(self):
        self.assertIn("diagnose_outcome_discrepancy", TOOL_HANDLERS)
        names = [item["name"] for item in TOOL_DECLARATIONS]
        self.assertEqual(names.count("diagnose_outcome_discrepancy"), 1)


    def test_diagnoses_explicit_negative_observation_as_mismatch(self):
        from gemini_agent.tools import diagnose_outcome_discrepancy
        result = diagnose_outcome_discrepancy(
            "Identify foreground app",
            "Foreground app is identified and safe read-only inspection is supported",
            "Foreground package and activity become established",
            "Foreground app cannot be safely identified",
            "The observed activity is wrong and read-only inspection is not supported.",
        )
        self.assertIn("Outcome state: MISMATCH", result)
        self.assertIn("Next decision: REPLAN", result)

    def test_client_executes_outcome_discrepancy_diagnosis_without_provider_reinterpretation(self):
        from gemini_agent.tools import TOOL_HANDLERS
        client = GeminiClient.__new__(GeminiClient)
        client.tool_handlers = TOOL_HANDLERS
        client.tool_declarations = [*TOOL_DECLARATIONS]
        prompt = (
            'Diagnose the outcome discrepancy for the goal "Identify foreground app". '
            'The success condition was "Foreground app is identified and safe read-only inspection is supported". '
            'The expected transition was "Foreground package and activity become established". '
            'The failure condition was "Foreground app cannot be safely identified". '
            'The supplied observed evidence is "The observed activity is wrong and read-only inspection is not supported."'
        )
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        requested_tool = client._requested_local_tool(contents)
        self.assertEqual(requested_tool, "diagnose_outcome_discrepancy")
        result = client.tool_handlers[requested_tool](
            goal="Identify foreground app",
            success_condition="Foreground app is identified and safe read-only inspection is supported",
            expected_transition="Foreground package and activity become established",
            failure_condition="Foreground app cannot be safely identified",
            observed_evidence="The observed activity is wrong and read-only inspection is not supported.",
        )
        self.assertIn("Outcome state: MISMATCH", result)
        self.assertIn("Next decision: REPLAN", result)


    def test_autonomy_boundary_stops_on_verified_outcome(self):
        from gemini_agent.tools import assess_autonomy_boundary
        result = assess_autonomy_boundary(
            "Check battery",
            "VERIFIED",
            "none",
            "Battery status was observed and verified.",
            "none",
            "low risk, read-only",
        )
        self.assertIn("Autonomy decision: STOP", result)
        self.assertIn("No action was executed", result)

    def test_autonomy_boundary_investigates_uncertain_safe_state(self):
        from gemini_agent.tools import assess_autonomy_boundary
        result = assess_autonomy_boundary(
            "Identify foreground app",
            "INCONCLUSIVE",
            "foreground component is unknown",
            "No reliable foreground observation yet.",
            "inspect or observe the environment using a bounded read-only mechanism",
            "low risk, read-only, bounded",
        )
        self.assertIn("Autonomy decision: INVESTIGATE", result)

    def test_autonomy_boundary_replans_mismatch_when_alternative_exists(self):
        from gemini_agent.tools import assess_autonomy_boundary
        result = assess_autonomy_boundary(
            "Open settings",
            "MISMATCH",
            "expected target was not reached",
            "Observed wrong activity.",
            "replan using an alternative bounded action",
            "low risk, reversible",
        )
        self.assertIn("Autonomy decision: REPLAN", result)

    def test_autonomy_boundary_escalates_material_uncertainty(self):
        from gemini_agent.tools import assess_autonomy_boundary
        result = assess_autonomy_boundary(
            "Perform consequential action",
            "INCONCLUSIVE",
            "the user approval requirement is unknown",
            "Evidence is incomplete.",
            "continue with the action",
            "high risk and irreversible",
        )
        self.assertIn("Autonomy decision: ESCALATE", result)

    def test_autonomy_boundary_is_registered_once(self):
        from gemini_agent.tools import TOOL_HANDLERS, TOOL_DECLARATIONS
        self.assertIn("assess_autonomy_boundary", TOOL_HANDLERS)
        names = [item["name"] for item in TOOL_DECLARATIONS]
        self.assertEqual(names.count("assess_autonomy_boundary"), 1)

    def test_client_routes_autonomy_boundary_requests_locally(self):
        contents = [{"role": "user", "parts": [{"text": "Assess the autonomy boundary for this goal and decide whether to continue or escalate."}]}]
        self.assertEqual(GeminiClient._requested_local_tool(contents), "assess_autonomy_boundary")
