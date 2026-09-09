"""Bounded self-improvement primitives for Nova Agent."""

from .diagnosis import FailureCategory, FailureDiagnosis, diagnose_run
from .policy import ImprovementDecision, ImprovementPolicy

__all__ = [
    "FailureCategory",
    "FailureDiagnosis",
    "ImprovementDecision",
    "ImprovementPolicy",
    "diagnose_run",
]
