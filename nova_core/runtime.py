"""Bounded runtime orchestration for Nova Agent v2.

The runtime coordinates the core ports without implementing any adapter
behavior. ``step`` advances one lifecycle phase, while ``run`` provides a
bounded convenience entrypoint for completing one run.
"""

from __future__ import annotations

from .models import Goal, RunResult, RunStatus
from .ports import Executor, Observer, Reasoner, Verifier
from .run_controller import RunController
from .state_machine import RunState


class Runtime:
    """Drive one bounded controller step using injected capabilities."""

    def __init__(
        self,
        goal: Goal,
        observer: Observer,
        reasoner: Reasoner,
        executor: Executor,
        verifier: Verifier,
        *,
        max_steps: int = 20,
    ) -> None:
        self.controller = RunController(goal, max_steps=max_steps)
        self.observer = observer
        self.reasoner = reasoner
        self.executor = executor
        self.verifier = verifier

    def step(self) -> RunState:
        """Advance through one lifecycle phase or execute one action."""
        state = self.controller.state

        if state is RunState.CREATED:
            self.controller.move(RunState.OBSERVING)
            return self.controller.state

        if state is RunState.OBSERVING:
            self.controller.record_observation(self.observer.observe())
            self.controller.move(RunState.DECIDING)
            return self.controller.state

        if state is RunState.DECIDING:
            assert self.controller.observation is not None
            self.controller.record_decision(
                self.reasoner.decide(self.controller.goal, self.controller.observation)
            )
            self.controller.move(RunState.EXECUTING)
            return self.controller.state

        if state is RunState.EXECUTING:
            assert self.controller.decision is not None
            self.controller.record_execution(
                self.executor.execute(self.controller.decision.action)
            )
            self.controller.move(RunState.VERIFYING)
            return self.controller.state

        if state is RunState.VERIFYING:
            assert self.controller.observation is not None
            assert self.controller.decision is not None
            assert self.controller.last_execution is not None
            after = self.observer.observe()
            achieved = self.verifier.verify(
                self.controller.goal,
                self.controller.observation,
                self.controller.decision.action,
                self.controller.last_execution,
                after,
            )
            if achieved:
                self.controller.finish(RunStatus.SUCCEEDED)
            elif self.controller.steps >= self.controller.max_steps:
                self.controller.finish(RunStatus.FAILED, "step budget exhausted")
            else:
                self.controller.move(RunState.OBSERVING)
            return self.controller.state

        return self.controller.state

    def run(self) -> RunResult:
        """Complete the run using a finite lifecycle budget.

        Four non-terminal phases are possible per action, plus the initial
        creation transition. The bound is derived from the action budget, so
        this method cannot spin indefinitely.
        """
        phase_budget = self.controller.max_steps * 4 + 1
        for _ in range(phase_budget):
            if self.controller.result() is not None:
                return self.controller.result()  # type: ignore[return-value]
            self.step()

        if self.controller.result() is None:
            self.controller.finish(RunStatus.FAILED, "runtime phase budget exhausted")
        return self.controller.result()  # type: ignore[return-value]
