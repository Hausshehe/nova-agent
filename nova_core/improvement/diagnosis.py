"""Evidence-based failure diagnosis for Nova's future self-improvement loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..models import RunResult, RunStatus
from ..reasoning import ReasoningStep


class FailureCategory(str, Enum):
    INVALID_DECISION = "invalid_decision"
    EXECUTION_REJECTED = "execution_rejected"
    EXECUTION_UNCHANGED = "execution_unchanged"
    STEP_BUDGET = "step_budget"
    REPLAN_BUDGET = "replan_budget"
    PROVIDER_FAILURE = "provider_failure"
    OBSERVATION_FAILURE = "observation_failure"
    VERIFICATION_FAILURE = "verification_failure"
    RUNTIME_FAILURE = "runtime_failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FailureDiagnosis:
    """A bounded, auditable explanation of why a run failed."""

    category: FailureCategory
    summary: str
    evidence: tuple[str, ...] = ()
    repairable: bool = True


def diagnose_run(result: RunResult, history: tuple[ReasoningStep, ...] = ()) -> FailureDiagnosis | None:
    """Classify a failed run using runtime evidence, never model speculation."""
    if result.status is not RunStatus.FAILED:
        return None

    error = (result.error or "").strip()
    lowered = error.lower()
    evidence: list[str] = [f"run_status={result.status.value}", f"steps={result.steps}"]
    if error:
        evidence.append(f"runtime_error={error}")

    rejected = sum(not step.execution.accepted for step in history)
    unchanged = sum(step.execution.accepted and not step.execution.changed for step in history)
    if rejected:
        evidence.append(f"rejected_actions={rejected}")
    if unchanged:
        evidence.append(f"unchanged_actions={unchanged}")

    if "invalid decision" in lowered:
        category = FailureCategory.INVALID_DECISION
    elif "replan budget" in lowered:
        category = FailureCategory.REPLAN_BUDGET
    elif "step budget" in lowered:
        category = FailureCategory.STEP_BUDGET
    elif "observation" in lowered or "timed out" in lowered:
        category = FailureCategory.OBSERVATION_FAILURE
    elif "provider" in lowered or "api" in lowered or "rate limit" in lowered:
        category = FailureCategory.PROVIDER_FAILURE
    elif rejected:
        category = FailureCategory.EXECUTION_REJECTED
    elif unchanged:
        category = FailureCategory.EXECUTION_UNCHANGED
    elif "verif" in lowered or "goal" in lowered:
        category = FailureCategory.VERIFICATION_FAILURE
    elif error:
        category = FailureCategory.RUNTIME_FAILURE
    else:
        category = FailureCategory.UNKNOWN

    return FailureDiagnosis(
        category=category,
        summary=error or "run failed without a reported error",
        evidence=tuple(evidence),
        repairable=category is not FailureCategory.UNKNOWN,
    )
