from nova_core.improvement import (
    FailureCategory,
    ImprovementDecision,
    ImprovementPolicy,
    diagnose_run,
)
from nova_core.models import Action, ActionType, Decision, ExecutionResult, RunResult, RunStatus
from nova_core.reasoning import ReasoningStep


def _step(*, accepted: bool, changed: bool, error: str | None = None) -> ReasoningStep:
    return ReasoningStep(
        decision=Decision(Action(ActionType.TAP, target_id="button")),
        execution=ExecutionResult(accepted=accepted, changed=changed, error=error),
    )


def test_diagnose_run_classifies_step_budget_and_preserves_evidence() -> None:
    diagnosis = diagnose_run(
        RunResult(RunStatus.FAILED, steps=3, error="step budget exhausted"),
        (_step(accepted=True, changed=True),) * 3,
    )

    assert diagnosis is not None
    assert diagnosis.category is FailureCategory.STEP_BUDGET
    assert "runtime_error=step budget exhausted" in diagnosis.evidence
    assert diagnosis.repairable is True


def test_diagnose_run_prioritizes_rejected_execution_when_no_specific_runtime_error() -> None:
    diagnosis = diagnose_run(
        RunResult(RunStatus.FAILED, steps=1),
        (_step(accepted=False, changed=False, error="target blocked"),),
    )

    assert diagnosis is not None
    assert diagnosis.category is FailureCategory.EXECUTION_REJECTED
    assert "rejected_actions=1" in diagnosis.evidence


def test_diagnose_run_ignores_successful_runs() -> None:
    assert diagnose_run(RunResult(RunStatus.SUCCEEDED, steps=2)) is None


def test_policy_proposes_bounded_repairs_without_runtime_mutation() -> None:
    diagnosis = diagnose_run(RunResult(RunStatus.FAILED, 2, "step budget exhausted"))
    assert diagnosis is not None

    policy = ImprovementPolicy(max_proposals_per_run=1)
    assert policy.decide(diagnosis) is ImprovementDecision.PROPOSE
    assert policy.decide(diagnosis, proposals_used=1) is ImprovementDecision.NO_ACTION


def test_policy_requires_diagnosis_for_provider_and_observation_failures() -> None:
    for error in ("provider request failed", "timed out waiting for observation"):
        diagnosis = diagnose_run(RunResult(RunStatus.FAILED, 0, error))
        assert diagnosis is not None
        assert policy_decision(diagnosis) is ImprovementDecision.DIAGNOSE


def policy_decision(diagnosis):
    return ImprovementPolicy().decide(diagnosis)
