"""Bounded runtime orchestration for Nova Agent v2."""

from __future__ import annotations

from .action_guard import ActionGuard
from .evidence import EvidenceTracker
from .models import ExecutionResult, Goal, RunResult, RunStatus
from .ports import Executor, FreshObserver, Observer, Reasoner, Verifier
from .reasoning import ReasoningContext
from .run_controller import RunController
from .state_machine import RunState


class Runtime:
    """Drive one bounded controller lifecycle with evidence and action guarding."""

    def __init__(
        self,
        goal: Goal,
        observer: Observer,
        reasoner: Reasoner,
        executor: Executor,
        verifier: Verifier,
        *,
        max_steps: int = 20,
        max_invalid_decisions: int = 3,
        action_guard: ActionGuard | None = None,
    ) -> None:
        if max_invalid_decisions < 0:
            raise ValueError("max_invalid_decisions must not be negative")
        self.controller = RunController(goal, max_steps=max_steps)
        self.observer = observer
        self.reasoner = reasoner
        self.executor = executor
        self.verifier = verifier
        self.action_guard = action_guard or ActionGuard()
        self.evidence = EvidenceTracker(max_rejections=max(1, max_invalid_decisions + 2))
        self.invalid_decisions = 0
        self.max_invalid_decisions = max_invalid_decisions

    def step(self) -> RunState:
        state = self.controller.state

        if state is RunState.CREATED:
            self.controller.move(RunState.OBSERVING)
            return self.controller.state

        if state is RunState.OBSERVING:
            observation = self.observer.observe()
            self.evidence.observe(observation)
            self.controller.record_observation(observation)
            self.controller.move(RunState.DECIDING)
            return self.controller.state

        if state is RunState.DECIDING:
            assert self.controller.observation is not None
            context = ReasoningContext(
                goal=self.controller.goal,
                observation=self.controller.observation,
                history=self.controller.history,
                evidence=self.evidence.snapshot(self.controller.history),
            )
            try:
                decision = self.reasoner.decide(context)
            except ValueError as exc:
                self.invalid_decisions += 1
                self.evidence.record_rejection(self.controller.decision, str(exc))
                if self.invalid_decisions > self.max_invalid_decisions:
                    self.controller.finish(RunStatus.FAILED, str(exc))
                else:
                    self.controller.move(RunState.OBSERVING)
                return self.controller.state
            except RuntimeError as exc:
                self.controller.finish(RunStatus.FAILED, str(exc))
                return self.controller.state
            self.controller.record_decision(decision)
            self.controller.move(RunState.EXECUTING)
            return self.controller.state

        if state is RunState.EXECUTING:
            assert self.controller.decision is not None
            guard = self.action_guard.check(
                self.controller.decision, self.controller.observation  # type: ignore[arg-type]
            )
            if not guard.allowed:
                execution = ExecutionResult(False, False, guard.reason)
            else:
                execution = self.executor.execute(self.controller.decision.action)
            self.controller.record_execution(execution)
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
            self.evidence.observe(after)
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
                self.controller.move(RunState.OBSERVING)
            return self.controller.state

        return self.controller.state

    def run(self) -> RunResult:
        # Invalid decisions and guarded actions are bounded recovery events.
        phase_budget = self.controller.max_steps * 8 + self.max_invalid_decisions * 2 + 1
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
