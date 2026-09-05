"""Bounded runtime orchestration for Nova Agent v2."""

from __future__ import annotations

from .models import Goal, RunResult, RunStatus
from .ports import Executor, FreshObserver, Observer, Reasoner, Verifier
from .reasoning import ReasoningContext
from .run_controller import RunController
from .state_machine import RunState


class Runtime:
    """Drive one bounded controller lifecycle."""

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
            context = ReasoningContext(
                goal=self.controller.goal,
                observation=self.controller.observation,
                history=self.controller.history,
            )
            try:
                decision = self.reasoner.decide(context)
            except ValueError as exc:
                self.controller.finish(RunStatus.FAILED, str(exc))
                return self.controller.state
            except RuntimeError as exc:
                self.controller.finish(RunStatus.FAILED, str(exc))
                return self.controller.state
            self.controller.record_decision(decision)
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
            before = self.controller.observation
            decision = self.controller.decision
            execution = self.controller.last_execution
            assert before is not None and decision is not None and execution is not None

            if isinstance(self.observer, FreshObserver):
                after = self.observer.observe_fresh(before)
            else:
                after = self.observer.observe()

            self.controller.record_post_observation(after)

            achieved = self.verifier.verify(
                self.controller.goal,
                before,
                decision,
                execution,
                after,
            )
            if achieved:
                self.controller.finish(RunStatus.SUCCEEDED)
            elif self.controller.steps >= self.controller.max_steps and execution.accepted and execution.changed:
                self.controller.finish(RunStatus.FAILED, "step budget exhausted")
            else:
                # Rejected, unchanged, and WAIT decisions are recovery events,
                # not successful progress. They do not consume the action budget.
                self.controller.move(RunState.OBSERVING)
            return self.controller.state

        return self.controller.state

    def run(self) -> RunResult:
        phase_budget = self.controller.max_steps * 4 + 1
        for _ in range(phase_budget):
            result = self.controller.result()
            if result is not None:
                return result
            self.step()

        if self.controller.result() is None:
            self.controller.finish(RunStatus.FAILED, "runtime phase budget exhausted")
        result = self.controller.result()
        assert result is not None
        return result
