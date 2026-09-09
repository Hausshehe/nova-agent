from nova_core.improvement.diagnosis import FailureCategory, FailureDiagnosis
from nova_core.improvement.proposer import LLMRepairProposer, RepairProposalContext, build_repair_prompt


def test_proposer_builds_bounded_evidence_prompt() -> None:
    diagnosis = FailureDiagnosis(
        FailureCategory.STEP_BUDGET,
        "step budget exhausted",
        ("runtime_error=step budget exhausted", "steps=3"),
    )
    prompt = build_repair_prompt(RepairProposalContext(diagnosis, "abc123"))
    assert "abc123" in prompt
    assert "step_budget" in prompt
    assert "runtime_error=step budget exhausted" in prompt
    assert "return_unified_diff_only" in prompt


def test_proposer_returns_valid_candidate() -> None:
    diagnosis = FailureDiagnosis(FailureCategory.STEP_BUDGET, "budget exhausted", ())

    def responder(prompt: str):
        assert "step_budget" in prompt
        return {
            "description": "Increase the bounded test budget",
            "patch": "--- a/value.py\n+++ b/value.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
            "paths": ["value.py"],
        }

    candidate = LLMRepairProposer(responder).propose(RepairProposalContext(diagnosis, "abc123"))
    assert candidate.description == "Increase the bounded test budget"
    assert candidate.paths == ("value.py",)


def test_proposer_rejects_malformed_response() -> None:
    diagnosis = FailureDiagnosis(FailureCategory.RUNTIME_FAILURE, "broken", ())

    def responder(prompt: str):
        return {"description": "missing patch"}

    try:
        LLMRepairProposer(responder).propose(RepairProposalContext(diagnosis, "abc123"))
    except ValueError as exc:
        assert "patch" in str(exc)
    else:
        raise AssertionError("malformed repair proposal was accepted")
