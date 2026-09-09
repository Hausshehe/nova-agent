"""Evidence-backed mission state for one Nova Agent run."""

from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, ExecutionResult, Goal, Observation


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

    def observed(self, observation: Observation) -> "MissionState":
        return MissionState(
            self.goal, observation, self.last_decision, self.last_execution,
            self.successful_actions, self.changed_actions, self.failed_actions,
            self.goal_verified,
        )

    def decided(self, decision: Decision) -> "MissionState":
        return MissionState(
            self.goal, self.observation, decision, self.last_execution,
            self.successful_actions, self.changed_actions, self.failed_actions,
            False,
        )

    def executed(self, result: ExecutionResult) -> "MissionState":
        return MissionState(
            self.goal, self.observation, self.last_decision, result,
            self.successful_actions + int(result.accepted),
            self.changed_actions + int(result.accepted and result.changed),
            self.failed_actions + int(not result.accepted),
            False,
        )

    def verified(self, observation: Observation, goal_achieved: bool) -> "MissionState":
        return MissionState(
            self.goal, observation, self.last_decision, self.last_execution,
            self.successful_actions, self.changed_actions, self.failed_actions,
            goal_achieved,
        )
