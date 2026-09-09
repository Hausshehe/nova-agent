"""Bounded self-improvement orchestration for Nova.

This capability diagnoses failed missions, proposes a repair, and evaluates it
in isolation. It never mutates the live source tree or adopts a candidate.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..models import Observation, RunResult
from ..reasoning import ReasoningStep
from .device_context import DeviceEvidence
from .diagnosis import FailureDiagnosis, diagnose_run
from .policy import ImprovementDecision, ImprovementPolicy
from .proposer import LLMRepairProposer, RepairProposalContext, RepairResponder
from .repair import RepairCandidate
from .sandbox import RepairSandbox, SandboxResult
from .validation import ValidationPolicy


@dataclass(frozen=True)
class ImprovementResult:
    """Auditable result of one bounded self-improvement attempt."""

    decision: ImprovementDecision
    diagnosis: FailureDiagnosis | None = None
    candidate: RepairCandidate | None = None
    sandbox: SandboxResult | None = None
    source_revision: str | None = None
    error: str | None = None

    @property
    def accepted(self) -> bool:
        return self.sandbox is not None and self.sandbox.accepted


def _source_revision(source_root: Path) -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=source_root,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("could not determine source revision")
    revision = result.stdout.strip()
    if not revision:
        raise RuntimeError("source revision was empty")
    return revision


class SelfImprovementOrchestrator:
    """Connect Nova's failure evidence to proposal and isolated validation."""

    def __init__(
        self,
        source_root: str | Path,
        responder: RepairResponder,
        policy: ImprovementPolicy | None = None,
        validation_policy: ValidationPolicy | None = None,
    ) -> None:
        self.source_root = Path(source_root).resolve()
        self.policy = policy or ImprovementPolicy()
        self.proposer = LLMRepairProposer(responder)
        self.validation_policy = validation_policy or ValidationPolicy()

    def improve(
        self,
        result: RunResult,
        history: tuple[ReasoningStep, ...] = (),
        observation: Observation | None = None,
        previous_observation: Observation | None = None,
        proposals_used: int = 0,
    ) -> ImprovementResult:
        diagnosis = diagnose_run(result, history)
        if diagnosis is None:
            return ImprovementResult(ImprovementDecision.NO_ACTION)

        decision = self.policy.decide(diagnosis, proposals_used)
        if decision is not ImprovementDecision.PROPOSE:
            return ImprovementResult(decision, diagnosis=diagnosis)

        try:
            revision = _source_revision(self.source_root)
            device = None
            if observation is not None:
                device = DeviceEvidence.from_runtime(
                    observation,
                    history[-1].decision if history else None,
                    history[-1].execution if history else None,
                    previous_observation,
                )
            context = RepairProposalContext(diagnosis, revision, device)
            candidate = self.proposer.propose(context)
            sandbox = RepairSandbox(self.source_root, self.validation_policy).evaluate(candidate)
            return ImprovementResult(
                decision,
                diagnosis=diagnosis,
                candidate=candidate,
                sandbox=sandbox,
                source_revision=revision,
            )
        except Exception as exc:
            return ImprovementResult(decision, diagnosis=diagnosis, error=str(exc))
