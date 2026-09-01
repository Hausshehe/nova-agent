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


def _action_history(decision: Decision, step: int, *, accepted: bool, changed: bool, verified: bool, error: str | None = None) -> dict[str, Any]:
    target = decision.action.target
    return {
        "step": step,
        "action_type": decision.action.type.value,
        "target_id": target.element_id if target else None,
        "target_text": target.text if target else "",
        "target_content_description": target.content_description if target else "",
        "accepted": accepted,
        "changed": changed,
        "verified": verified,
        "error": error,
    }


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
                history.append(
                    _action_history(
                        decision,
                        step,
                        accepted=False,
                        changed=False,
                        verified=False,
                        error=result.error,
                    )
                )
                continue

            try:
                after = self.bridge.wait_for_fresh_observation(state, self.settle_timeout)
            except TimeoutError:
                history.append(
                    _action_history(
                        decision,
                        step,
                        accepted=True,
                        changed=False,
                        verified=False,
                        error="fresh observation timeout",
                    )
                )
                continue

            changed = after != state
            verified = self.verifier.verify(state, after, ExecutionResult(True, changed, False))
            history.append(
                _action_history(
                    decision,
                    step,
                    accepted=True,
                    changed=changed,
                    verified=verified,
                )
            )

            state = after
            if self.evaluator.evaluate(goal, state):
                return True

        return False
