"""Bounded self-improvement capabilities for Nova Agent."""

from .device_context import DeviceEvidence
from .diagnosis import FailureCategory, FailureDiagnosis, diagnose_run
from .orchestrator import ImprovementResult, SelfImprovementOrchestrator
from .policy import ImprovementDecision, ImprovementPolicy
from .proposer import LLMRepairProposer, RepairProposalContext, build_repair_prompt
from .repair import RepairCandidate
from .validation import ValidationPolicy, ValidationRecord, ValidationReport, ValidationStatus

__all__ = [
    "DeviceEvidence",
    "FailureCategory",
    "FailureDiagnosis",
    "ImprovementDecision",
    "ImprovementPolicy",
    "ImprovementResult",
    "LLMRepairProposer",
    "RepairCandidate",
    "RepairProposalContext",
    "SelfImprovementOrchestrator",
    "ValidationPolicy",
    "ValidationRecord",
    "ValidationReport",
    "ValidationStatus",
    "build_repair_prompt",
    "diagnose_run",
]
