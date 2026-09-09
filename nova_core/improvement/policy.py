"""Safety policy for Nova's self-improvement loop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .diagnosis import FailureCategory, FailureDiagnosis


class ImprovementDecision(str, Enum):
    NO_ACTION = "no_action"
    DIAGNOSE = "diagnose"
    PROPOSE = "propose"


@dataclass(frozen=True)
class ImprovementPolicy:
    """Keep self-improvement bounded and prevent runtime self-modification."""

    max_proposals_per_run: int = 1
    allow_runtime_mutation: bool = False

    def decide(self, diagnosis: FailureDiagnosis, proposals_used: int = 0) -> ImprovementDecision:
        if not diagnosis.repairable:
            return ImprovementDecision.NO_ACTION
        if proposals_used >= self.max_proposals_per_run:
            return ImprovementDecision.NO_ACTION
        if self.allow_runtime_mutation:
            raise ValueError("runtime mutation is not supported by this policy")
        if diagnosis.category in {
            FailureCategory.PROVIDER_FAILURE,
            FailureCategory.OBSERVATION_FAILURE,
            FailureCategory.RUNTIME_FAILURE,
            FailureCategory.UNKNOWN,
        }:
            return ImprovementDecision.DIAGNOSE
        return ImprovementDecision.PROPOSE
