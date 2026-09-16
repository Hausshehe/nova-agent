from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from .agent_state import AgentState
from .core import Action, ActionType, Decision, ExecutionResult, TransitionVerifier, WorldState
from .goal_evaluator import GoalEvaluator
from .reasoning_context import ReasoningContext, build_reasoning_context
from .reasoning_provider import ReasoningProvider


class NavigationBridge(Protocol):
    def observe(self) -> WorldState: ...
    def execute(self, action: Action) -> ExecutionResult: ...
    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState: ...


class LegacyPlanner(Protocol):
    """Backward-compatible interface for pre-provider planners."""

    def plan(self, context: ReasoningContext) -> Decision: ...


def _decide(provider: ReasoningProvider | LegacyPlanner, context: ReasoningContext) -> Decision:
    """Use the provider boundary while keeping old plan()-based callers working."""
    decide = getattr(provider, "decide", None)
    if callable(decide):
        return decide(context)
    plan = getattr(provider, "plan", None)
    if callable(plan):
        return plan(context)
    raise TypeError("reasoning provider must implement decide() or legacy plan()")


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
    planner: ReasoningProvider | LegacyPlanner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    max_steps: int = 5
    settle_timeout: float = 2.0

    def run(
        self,
        goal: str,
        *,
        initial_state: WorldState | None = None,
        observe: Callable[[], WorldState] | None = None,
        refresh: Callable[[WorldState], WorldState] | None = None,
    ) -> bool:
        """Run navigation with an explicit, bounded working state.

        The callbacks let TaskExecutor own observation acquisition/refresh while
        preserving this loop as a compatibility planner/execution engine.
        Direct callers still use the bridge when callbacks are omitted.
        """
        observe_fn = observe or self.bridge.observe
        refresh_fn = refresh or (
            lambda previous: self.bridge.wait_for_fresh_observation(previous, self.settle_timeout)
        )
        world = initial_state if initial_state is not None else observe_fn()
        runtime_state = AgentState(goal=goal, world=world)
        action_goal = self.evaluator.is_action_goal(goal)

        if not action_goal and self.evaluator.evaluate(goal, world):
            runtime_state = runtime_state.transition(status="complete")
            return True

        for step in range(1, self.max_steps + 1):
            context = build_reasoning_context(
                goal,
                runtime_state.world,
                runtime_state.history,
                agent_state=runtime_state,
            )
            decision = _decide(self.planner, context)

            # WAIT is a synchronization/observation primitive, not an Android
            # command and not a state-transition requirement.
            is_wait = decision.action.type is ActionType.WAIT
            if is_wait:
                result = ExecutionResult(True, False)
            else:
                result = self.bridge.execute(decision.action)

            if not result.accepted:
                runtime_state = runtime_state.record(
                    _action_history(
                        decision,
                        step,
                        accepted=False,
                        changed=False,
                        verified=False,
                        error=result.error,
                    ),
                    failure=True,
                    error=result.error,
                )
                # A rejected action is not a verified transition, but the bridge
                # must still provide the next fresh observation before replanning.
                # Calling observe() here can return the same cached snapshot and
                # would make valid recovery targets invisible to the provider.
                try:
                    refreshed = refresh_fn(runtime_state.world)
                except TimeoutError:
                    refreshed = observe_fn()
                runtime_state = runtime_state.transition(world=refreshed)
                continue

            try:
                # Real state-changing actions require a fresh observation whose
                # identity differs from the previous state. WAIT only requires
                # a successful observation; an unchanged UI is valid.
                after = observe_fn() if is_wait else refresh_fn(runtime_state.world)
            except TimeoutError:
                runtime_state = runtime_state.record(
                    _action_history(
                        decision,
                        step,
                        accepted=True,
                        changed=False,
                        verified=False,
                        error="fresh observation timeout",
                    ),
                    failure=True,
                    error="fresh observation timeout",
                )
                continue

            changed = after != runtime_state.world
            verified = True if is_wait else self.verifier.verify(
                runtime_state.world, after, ExecutionResult(True, changed, False)
            )
            runtime_state = runtime_state.record(
                _action_history(
                    decision,
                    step,
                    accepted=True,
                    changed=changed,
                    verified=verified,
                ),
                world=after,
                error=None,
            )

            if action_goal and verified:
                runtime_state = runtime_state.transition(status="complete")
                return True
            if self.evaluator.evaluate(goal, runtime_state.world):
                runtime_state = runtime_state.transition(status="complete")
                return True

        return False
