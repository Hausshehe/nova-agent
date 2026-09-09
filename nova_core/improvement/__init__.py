"""Bounded self-improvement primitives for Nova Agent."""

from .diagnosis import FailureCategory, FailureDiagnosis, diagnose_run
from .policy import ImprovementDecision, ImprovementPolicy
from .proposer import LLMRepairProposer, RepairProposalContext, build_repair_prompt
from .repair import RepairCandidate
from .validation import ValidationPolicy, ValidationRecord, ValidationReport, ValidationStatus

__all__ = [
    "FailureCategory",
    "FailureDiagnosis",
    "ImprovementDecision",
    "ImprovementPolicy",
    "LLMRepairProposer",
    "RepairCandidate",
    "RepairProposalContext",
    "ValidationPolicy",
    "ValidationRecord",
    "ValidationReport",
    "ValidationStatus",
    "build_repair_prompt",
    "diagnose_run",
]
