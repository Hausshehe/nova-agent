"""Small orchestration boundary for Nova Agent v2.

The controller owns run-state progression and the step budget, but it does
not observe Android, call a reasoning provider, or execute actions. Runtime
adapters will be connected later.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Goal, Observation, Decision, ExecutionResult, RunResult, RunStatus
from .state_machine import InvalidTransition, RunState, is_terminal, transition


@dataclass
class RunController:
    """Own one bounded run without performing runtime work."""

    goal: Goal
    max_steps: int = 20
    state: RunState = RunState.CREATED
    steps: int = 0
    observation: Observation | None = None
    decision: Decision | None = None
    last_execution: ExecutionResult | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")

    def move(self, target: RunState) -> RunState:
        """Perform exactly one validated state transition."""
        self.state = transition(self.state, target)
        return self.state

    def record_observation(self, observation: Observation) -> None:
        """Attach an observation; state progression remains explicit."""
        if self.state != RunState.OBSERVING:
            raise InvalidTransition("observation can only be recorded while observing")
        self.observation = observation

    def record_decision(self, decision: Decision) -> None:
        """Attach a decision; no execution occurs here."""
        if self.state != RunState.DECIDING:
            raise InvalidTransition("decision can only be recorded while deciding")
        self.decision = decision

    def record_execution(self, result: ExecutionResult) -> None:
        """Attach an execution result and consume one bounded step."""
        if self.state != RunState.EXECUTING:
            raise InvalidTransition("execution can only be recorded while executing")
        if self.steps >= self.max_steps:
            raise RuntimeError("step budget exhausted")
        self.last_execution = result
        self.steps += 1

    def finish(self, status: RunStatus, error: str | None = None) -> RunResult:
        """Enter one terminal state explicitly and return the run result."""
        targets = {
            RunStatus.SUCCEEDED: RunState.SUCCEEDED,
            RunStatus.FAILED: RunState.FAILED,
            RunStatus.ABORTED: RunState.ABORTED,
        }
        if status not in targets:
            raise ValueError("finish requires a terminal RunStatus")
        self.error = error
        self.move(targets[status])
        return RunResult(status=status, steps=self.steps, error=error)

    def result(self) -> RunResult | None:
        """Return a result only after the controller reaches a terminal state."""
        if not is_terminal(self.state):
            return None
        status = RunStatus(self.state.value)
        return RunResult(status=status, steps=self.steps, error=self.error)
