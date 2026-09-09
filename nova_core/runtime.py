"""Bounded runtime orchestration for Nova Agent v2."""

from __future__ import annotations

from .action_guard import ActionGuard
from .evidence import EvidenceTracker
from .models import ExecutionResult, Goal, RunResult
from .planning import GoalPlanner, Plan, Planner
from .ports import Executor, FreshObserver, Observer, Reasoner, Verifier
from .run_controller import RunController
from .runtime_brain import RuntimeBrain
from .state_machine import RunState


class Runtime:
    """Drive one bounded Android mission through the runtime brain."""

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
        planner: Planner | None = None,
    ) -> None:
        if max_invalid_decisions < 0:
            raise ValueError("max_invalid_decisions must not be negative")
        self.brain = RuntimeBrain.create(goal, max_steps=max_steps)
        self.controller: RunController = self.brain.controller
        self.observer = observer
        self.reasoner = reasoner
        self.executor = executor
        self.verifier = verifier
        self.action_guard = action_guard or ActionGuard()
        self.evidence = EvidenceTracker(max_rejections=max(1, max_invalid_decisions + 2))
        self.invalid_decisions = 0
        self.max_invalid_decisions = max_invalid_decisions
        self.planner = planner or GoalPlanner()
        self._replan_requested = False

    def _record_invalid_decision(self, error: str) -> None:
        """Record one model/guard rejection without consuming action progress."""
        self.invalid_decisions += 1
        self.evidence.record_rejection(self.controller.decision, error)

    def _update_plan_after_observation(self) -> None:
        """Create or replace the bounded plan only from fresh runtime evidence."""
        context = self.brain.reasoning_context(
            evidence=self.evidence.snapshot(self.controller.history),
        )
        try:
            if self.brain.plan is None:
                self.brain.set_plan(self.planner.plan(context))
            elif self._replan_requested:
                self.brain.set_plan(self.planner.replan(context, self.brain.plan))
                self._replan_requested = False
        except (ValueError, RuntimeError) as exc:
            self.brain.fail(f"planning failed: {exc}")

    def step(self) -> RunState:
        state = self.brain.state

        if state is RunState.CREATED:
            self.brain.start()
            return self.brain.state

        if state is RunState.OBSERVING:
            observation = self.observer.observe()
            self.evidence.observe(observation)
            self.brain.record_observation(observation)
            if self.brain.state is RunState.DECIDING:
                self._update_plan_after_observation()
            return self.brain.state

        if state is RunState.DECIDING:
            context = self.brain.reasoning_context(
                evidence=self.evidence.snapshot(self.controller.history),
            )
            try:
                decision = self.reasoner.decide(context)
            except ValueError as exc:
                self._record_invalid_decision(str(exc))
                if self.invalid_decisions > self.max_invalid_decisions:
                    self.brain.fail(str(exc))
                else:
                    self.brain.start()
                return self.brain.state
            except RuntimeError as exc:
                self.brain.fail(str(exc))
                return self.brain.state
            self.brain.record_decision(decision)
            return self.brain.state

        if state is RunState.EXECUTING:
            assert self.controller.decision is not None
            guard = self.action_guard.check(
                self.controller.decision, self.controller.observation  # type: ignore[arg-type]
            )
            if not guard.allowed:
                self._record_invalid_decision(guard.reason)
                execution = ExecutionResult(False, False, guard.reason)
            else:
                execution = self.executor.execute(self.controller.decision.action)
            self.brain.record_execution(execution)
            return self.brain.state

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

            achieved = self.verifier.verify(
                self.controller.goal,
                before,
                decision,
                execution,
                after,
            )
            if achieved:
                self.brain.finish_verification(after, goal_achieved=True)
            elif self.invalid_decisions > self.max_invalid_decisions:
                self.brain.fail("invalid decision budget exhausted")
            elif self.controller.steps >= self.controller.max_steps and execution.accepted and execution.changed:
                self.brain.fail("step budget exhausted")
            else:
                self._replan_requested = not (execution.accepted and execution.changed)
                if execution.accepted and execution.changed:
                    self.brain.advance_plan()
                self.brain.finish_verification(after, goal_achieved=False)
            return self.brain.state

        return self.brain.state

    def run(self) -> RunResult:
        # The phase budget is a final containment boundary. Per-step invalid
        # decisions are also bounded so repeated rejected actions cannot leave
        # a manually stepped Runtime non-terminal forever.
        phase_budget = self.controller.max_steps * 8 + self.max_invalid_decisions * 2 + 1
        for _ in range(phase_budget):
            result = self.controller.result()
            if result is not None:
                return result
            self.step()

        if self.controller.result() is None:
            self.brain.fail("runtime phase budget exhausted")
        result = self.controller.result()
        assert result is not None
        return result
