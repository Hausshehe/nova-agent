"""Evidence-backed mission state for one Nova Agent run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ActionType, Decision, ExecutionResult, Goal, Observation, RunResult
from .outcome_memory import ActionOutcome, OutcomeMemory
from .uncertainty import UncertaintyAssessment, UncertaintyResolutionPolicy


@dataclass(frozen=True)
class MissionState:
    """Compact, deterministic state derived only from runtime evidence."""

    goal: Goal
    observation: Observation | None = None
    last_decision: Decision | None = None
    last_execution: ExecutionResult | None = None
    successful_actions: int = 0
    changed_actions: int = 0
    failed_actions: int = 0
    goal_verified: bool = False
    outcome_memory: OutcomeMemory = OutcomeMemory()
    resolved_unknowns: tuple[str, ...] = ()

    @property
    def progress_evidence(self) -> tuple[str, ...]:
        """Return facts the runtime can prove without semantic guessing."""
        evidence: list[str] = []
        if self.observation is not None:
            evidence.append(f"current_observation_revision={self.observation.revision}")
        if self.last_decision is not None:
            evidence.append(f"last_action_type={self.last_decision.action.type.value}")
            if self.last_decision.action.target_id:
                evidence.append(f"last_target_id={self.last_decision.action.target_id}")
            if self.last_decision.target_label:
                evidence.append(f"last_target_label={self.last_decision.target_label}")
        if self.last_execution is not None:
            evidence.append(f"last_execution_accepted={self.last_execution.accepted}")
            evidence.append(f"last_execution_changed={self.last_execution.changed}")
            if self.last_execution.error:
                evidence.append(f"last_execution_error={self.last_execution.error}")
        evidence.extend((
            f"successful_actions={self.successful_actions}",
            f"changed_actions={self.changed_actions}",
            f"failed_actions={self.failed_actions}",
            f"goal_verified={self.goal_verified}",
        ))
        return tuple(evidence)

    @property
    def assessment(self) -> dict[str, str]:
        """Classify the mission only from evidence, never from LLM belief."""
        if self.goal_verified:
            return {"status": "verified", "confidence": "high", "basis": "goal verifier"}
        if self.last_execution is not None:
            if not self.last_execution.accepted:
                return {"status": "blocked", "confidence": "high", "basis": "execution rejected"}
            if not self.last_execution.changed:
                return {"status": "stalled", "confidence": "medium", "basis": "accepted action produced no observable change"}
            return {"status": "progressing", "confidence": "medium", "basis": "accepted action produced observable change"}
        if self.observation is not None:
            return {"status": "observed", "confidence": "low", "basis": "current UI observed but no action outcome yet"}
        return {"status": "unknown", "confidence": "none", "basis": "no mission evidence yet"}

    @property
    def uncertainty(self) -> UncertaintyAssessment:
        """State explicitly what remains unknown after the latest evidence."""
        if self.goal_verified:
            return UncertaintyAssessment(level="low", basis="goal completion was verified")
        if self.last_execution is not None:
            if not self.last_execution.accepted:
                return self._with_resolved_unknowns(
                    "high", "execution was rejected",
                    ("whether another viable action exists", "goal completion"),
                )
            if not self.last_execution.changed:
                return self._with_resolved_unknowns(
                    "high", "accepted action produced no observable change",
                    (
                        "whether the action had the intended effect",
                        "whether another action is required",
                        "goal completion",
                    ),
                )
            return self._with_resolved_unknowns(
                "medium", "action changed the UI but goal completion is not verified",
                ("whether the observed change advances the goal", "goal completion"),
            )
        if self.observation is not None:
            return UncertaintyAssessment(
                level="high", basis="current UI is known but no action outcome exists yet",
                unknowns=("which action best advances the goal", "goal completion"),
            )
        return UncertaintyAssessment(
            level="high", basis="no mission evidence exists",
            unknowns=("current UI state", "best next action", "goal completion"),
        )

    def _with_resolved_unknowns(
        self,
        level: str,
        basis: str,
        unknowns: tuple[str, ...],
    ) -> UncertaintyAssessment:
        remaining = tuple(unknown for unknown in unknowns if unknown not in self.resolved_unknowns)
        return UncertaintyAssessment(level=level, basis=basis, unknowns=remaining)

    def uncertainty_resolution(self):
        """Return current-UI actions that could reduce explicit uncertainty."""
        if self.observation is None:
            return None
        excluded: tuple[str, ...] = ()
        if self.last_execution is not None and self.last_execution.accepted and not self.last_execution.changed:
            if self.last_decision is not None and self.last_decision.action.target_id:
                excluded = (self.last_decision.action.target_id,)
        return UncertaintyResolutionPolicy().resolve(
            self.uncertainty,
            self.observation,
            self.goal,
            excluded_target_ids=excluded,
        )

    def reasoning_snapshot(self) -> dict[str, Any]:
        """Return bounded state facts for model reasoning and planning."""
        snapshot: dict[str, Any] = {
            "goal_verified": self.goal_verified,
            "assessment": self.assessment,
            "uncertainty": self.uncertainty.snapshot(),
            "successful_actions": self.successful_actions,
            "changed_actions": self.changed_actions,
            "failed_actions": self.failed_actions,
            "progress_evidence": list(self.progress_evidence),
            "recent_action_outcomes": self.outcome_memory.snapshot(),
            "resolved_unknowns": list(self.resolved_unknowns),
        }
        resolution = self.uncertainty_resolution()
        if resolution is not None:
            snapshot["uncertainty_resolution"] = resolution.snapshot()
        if self.observation is not None:
            snapshot["current_observation_revision"] = self.observation.revision
        if self.last_decision is not None:
            snapshot["last_action"] = self.last_decision.action.type.value
            if self.last_decision.action.target_id:
                snapshot["last_target_id"] = self.last_decision.action.target_id
            if self.last_decision.target_label:
                snapshot["last_target_label"] = self.last_decision.target_label
        if self.last_execution is not None:
            snapshot["last_execution"] = {
                "accepted": self.last_execution.accepted,
                "changed": self.last_execution.changed,
                "error": self.last_execution.error,
            }
        return snapshot

    def observed(self, observation: Observation) -> "MissionState":
        return MissionState(
            self.goal, observation, self.last_decision, self.last_execution,
            self.successful_actions, self.changed_actions, self.failed_actions,
            self.goal_verified, self.outcome_memory, self.resolved_unknowns,
        )

    def decided(self, decision: Decision) -> "MissionState":
        return MissionState(
            self.goal, self.observation, decision, self.last_execution,
            self.successful_actions, self.changed_actions, self.failed_actions,
            False, self.outcome_memory, (),
        )

    def executed(self, result: ExecutionResult) -> "MissionState":
        decision = self.last_decision
        outcome = ActionOutcome.from_execution(
            decision.action.type if decision else ActionType.WAIT,
            decision.action.target_id if decision else None,
            decision.target_label if decision else "",
            result,
        )
        return MissionState(
            self.goal, self.observation, self.last_decision, result,
            self.successful_actions + int(result.accepted),
            self.changed_actions + int(result.accepted and result.changed),
            self.failed_actions + int(not result.accepted),
            False,
            self.outcome_memory.remember(outcome),
            (),
        )

    def verified(self, observation: Observation, goal_achieved: bool) -> "MissionState":
        resolved = self.resolved_unknowns
        before = self.observation
        execution = self.last_execution
        if (
            before is not None
            and execution is not None
            and observation.revision != before.revision
            and execution.accepted
            and not execution.changed
        ):
            resolved = tuple(dict.fromkeys((*resolved, "whether the action had the intended effect")))
        return MissionState(
            self.goal, observation, self.last_decision, self.last_execution,
            self.successful_actions, self.changed_actions, self.failed_actions,
            goal_achieved, self.outcome_memory, resolved,
        )
