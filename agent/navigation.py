from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .core import Action, Decision, ExecutionResult, TransitionVerifier, WorldState
from .goal_evaluator import GoalEvaluator
from .reasoning_context import ReasoningContext, build_reasoning_context


class NavigationBridge(Protocol):
    def observe(self) -> WorldState: ...
    def execute(self, action: Action) -> ExecutionResult: ...
    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState: ...


class Planner(Protocol):
    def plan(self, context: ReasoningContext) -> Decision: ...


@dataclass
class NavigationLoop:
    bridge: NavigationBridge
    planner: Planner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    max_steps: int = 5
    settle_timeout: float = 2.0

    def run(self, goal: str) -> bool:
        history: list[Mapping[str, Any]] = []
        state = self.bridge.observe()

        if self.evaluator.evaluate(goal, state):
            return True

        for step in range(1, self.max_steps + 1):
            context = build_reasoning_context(goal, state, history)
            decision = self.planner.plan(context)
            result = self.bridge.execute(decision.action)

            if not result.accepted:
                history.append({"step": step, "accepted": False, "changed": False, "verified": False})
                continue

            try:
                after = self.bridge.wait_for_fresh_observation(state, self.settle_timeout)
            except TimeoutError:
                history.append({"step": step, "accepted": True, "changed": False, "verified": False})
                continue

            changed = after != state
            verified = self.verifier.verify(state, after, ExecutionResult(True, changed, False))
            history.append({
                "step": step,
                "target_id": decision.action.target.element_id if decision.action.target else None,
                "target_text": decision.action.target.text if decision.action.target else "",
                "target_content_description": decision.action.target.content_description if decision.action.target else "",
                "accepted": True,
                "changed": changed,
                "verified": verified,
            })

            state = after
            if self.evaluator.evaluate(goal, state):
                return True

        return False
