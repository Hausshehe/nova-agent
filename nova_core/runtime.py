"""Bounded runtime orchestration for Nova Agent v2."""

from __future__ import annotations

import inspect

from .action_guard import ActionGuard
from .evidence import EvidenceTracker
from .learning_memory import LearningMemory, MissionLearningRecord
from .learning_policy import LearningApplicationPolicy
from .models import ExecutionResult, Goal, RunResult
from .planning import GoalPlanner, Planner, Plan
from .ports import Executor, FreshObserver, Observer, Reasoner, Verifier
from .run_controller import RunController
from .runtime_brain import RuntimeBrain
from .state_machine import RunState
from .uncertainty import UncertaintyResolutionPolicy


_UNCHANGED_ACTIONS_BEFORE_REPLAN = 2


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
        max_replans: int = 2,
        action_guard: ActionGuard | None = None,
        planner: Planner | None = None,
        replan_after_progress: bool = False,
        learning_memory: LearningMemory | None = None,
        learning_policy: LearningApplicationPolicy | None = None,
        intent_verifier: Verifier | None = None,
    ) -> None:
        if max_invalid_decisions < 0:
            raise ValueError("max_invalid_decisions must not be negative")
        if max_replans < 0:
            raise ValueError("max_replans must not be negative")
        self.brain = RuntimeBrain.create(goal, max_steps=max_steps)
        self.controller: RunController = self.brain.controller
        self.observer = observer
        self.reasoner = reasoner
        self.executor = executor
        self.verifier = verifier
        self.intent_verifier = intent_verifier
        self.action_guard = action_guard or ActionGuard()
        self.evidence = EvidenceTracker(max_rejections=max(1, max_invalid_decisions + 2))
        self.invalid_decisions = 0
        self.max_invalid_decisions = max_invalid_decisions
        self.planner = planner or GoalPlanner()
        self.replan_after_progress = replan_after_progress
        self.max_replans = max_replans
        self.replans = 0
        self.learning_memory = learning_memory or LearningMemory()
        self.learning_policy = learning_policy or LearningApplicationPolicy()
        self.uncertainty_policy = UncertaintyResolutionPolicy()
        self._learning_recorded = False
        self._replan_requested = False
        self._unchanged_actions = 0

    def _record_invalid_decision(self, error: str) -> None:
        """Record one model/guard rejection without consuming action progress."""
        self.invalid_decisions += 1
        self.evidence.record_rejection(self.controller.decision, error)

    def _uncertainty_resolution(self):
        observation = self.brain.memory.observation
        if observation is None:
            return None
        excluded: tuple[str, ...] = ()
        last_execution = self.brain.mission.last_execution
        last_decision = self.brain.mission.last_decision
        if last_execution is not None and last_execution.accepted and not last_execution.changed and last_decision is not None:
            if last_decision.action.target_id:
                excluded = (last_decision.action.target_id,)
        return self.uncertainty_policy.resolve(
            self.brain.mission.uncertainty,
            observation,
            self.brain.goal,
            excluded_target_ids=excluded,
        )

    def _reasoning_context(self):
        relevant_learning = self.learning_memory.retrieve(self.brain.goal.text)
        assess = self.learning_policy.assess
        if "goal" in inspect.signature(assess).parameters:
            learning_assessment = assess(relevant_learning, goal=self.brain.goal.text)
        else:
            learning_assessment = assess(relevant_learning)
        return self.brain.reasoning_context(
            evidence=self.evidence.snapshot(self.controller.history),
            relevant_learning=relevant_learning,
            learning_assessment=learning_assessment,
            uncertainty_resolution=self._uncertainty_resolution(),
        )

    def _record_learning(self, result: RunResult) -> RunResult:
        if not self._learning_recorded:
            record = MissionLearningRecord.from_mission(self.brain.mission, result)
            self.learning_memory = self.learning_memory.remember(record)
            self._learning_recorded = True
        return result

    @staticmethod
    def _skip_replayed_replan_intents(previous: Plan, replacement: Plan, evidence: object) -> Plan:
        """Do not immediately replay an intent that just produced no progress."""
        if (
            getattr(evidence, "last_execution_accepted", None) is not True
            or getattr(evidence, "last_execution_changed", None) is not False
            or previous.current is None
        ):
            return replacement

        failed_intent = previous.current.description.strip().casefold()
        adjusted = replacement
        while adjusted.current is not None and adjusted.current.description.strip().casefold() == failed_intent:
            adjusted = adjusted.advance()
        return adjusted

    def _update_plan_after_observation(self) -> None:
        """Create or replace the bounded plan only from fresh runtime evidence."""
        if self.controller.steps >= self.controller.max_steps:
            self.brain.fail("step budget exhausted")
            return

        context = self._reasoning_context()
        try:
            if self.brain.plan is None:
                self.brain.set_plan(self.planner.plan(context))
            elif self._replan_requested:
                if self.replans >= self.max_replans:
                    self.brain.fail("replan budget exhausted")
                    return
                previous = self.brain.plan
                replacement = self.planner.replan(context, previous)
                replacement = self._skip_replayed_replan_intents(previous, replacement, context.evidence)
                if replacement.complete:
                    self.brain.fail("replan produced no new executable intent")
                    return
                self.brain.set_plan(replacement)
                self.replans += 1
                self._replan_requested = False
                self._unchanged_actions = 0
        except (ValueError, RuntimeError) as exc:
            self.brain.fail(f"planning failed: {exc}")

    @staticmethod
    def _target_is_present(observation, target_id: str | None) -> bool:
        """Return whether the exact action target remains in fresh UI evidence."""
        if not target_id:
            return True
        return any(element.id == target_id for element in observation.elements)

    def _refresh_missing_target(self, guard):
        """Refresh live UI evidence once when a selected target is missing.

        Planning and action selection operate on a sampled observation. Android
        accessibility trees can transiently lag that sample, so a missing
        target at the execution boundary gets one fresh observation before the
        action is rejected. This keeps the guard authoritative without turning
        every action into a second observation.
        """
        if guard.allowed or not isinstance(self.observer, FreshObserver):
            return guard
        if guard.reason not in {
            "tap target is not present",
            "type target is not present",
            "scroll target is not scrollable and available",
            "swipe target is not available",
        }:
            return guard

        previous = self.controller.observation
        if previous is None:
            return guard

        try:
            refreshed = self.observer.observe_fresh(previous)
        except (TimeoutError, RuntimeError, ValueError):
            return guard

        self.controller.observation = refreshed
        self.brain.memory.observe(refreshed)
        self.brain.mission = self.brain.mission.observed(refreshed)
        self.evidence.observe(refreshed)
        return self.action_guard.check(
            self.controller.decision,  # type: ignore[arg-type]
            refreshed,
            self.evidence.snapshot(self.controller.history),
        )

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
            context = self._reasoning_context()
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
            guard = self.action_guard.check(self.controller.decision, self.controller.observation)  # type: ignore[arg-type]
            guard = self._refresh_missing_target(guard)
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
            if isinstance(self.observer, FreshObserver) and execution.accepted:
                after = self.observer.observe_fresh(before)
            else:
                after = self.observer.observe()
            self.evidence.observe(after)
            achieved = self.verifier.verify(self.controller.goal, before, decision, execution, after)
            current_intent = self.brain.plan.current if self.brain.plan is not None else None
            if self.intent_verifier is None:
                intent_achieved = execution.accepted and execution.changed
            elif current_intent is not None and execution.accepted and execution.changed:
                intent_achieved = self.intent_verifier.verify(
                    Goal(current_intent.description),
                    before,
                    decision,
                    execution,
                    after,
                )
            else:
                intent_achieved = False
            if achieved:
                self.brain.finish_verification(after, goal_achieved=True)
            elif self.invalid_decisions > self.max_invalid_decisions:
                self.brain.fail("invalid decision budget exhausted")
            else:
                if execution.accepted and execution.changed:
                    self._unchanged_actions = 0
                    if self.replan_after_progress:
                        self._replan_requested = True
                    else:
                        self._replan_requested = False
                        if intent_achieved:
                            self.brain.advance_plan()
                elif not execution.accepted:
                    self._unchanged_actions = 0
                    self._replan_requested = True
                else:
                    target_id = decision.action.target_id
                    if not self._target_is_present(after, target_id):
                        self._unchanged_actions = 0
                        self._replan_requested = True
                    else:
                        self._unchanged_actions += 1
                        self._replan_requested = self._unchanged_actions >= _UNCHANGED_ACTIONS_BEFORE_REPLAN
                self.brain.finish_verification(after, goal_achieved=False)
                if self.controller.steps >= self.controller.max_steps:
                    self.brain.fail("step budget exhausted")
            return self.brain.state
        return self.brain.state

    def run(self) -> RunResult:
        phase_budget = self.controller.max_steps * 8 + self.max_invalid_decisions * 2 + self.max_replans * 2 + 1
        for _ in range(phase_budget):
            result = self.controller.result()
            if result is not None:
                return self._record_learning(result)
            self.step()
        if self.controller.result() is None:
            self.brain.fail("runtime phase budget exhausted")
        result = self.controller.result()
        assert result is not None
        return self._record_learning(result)
