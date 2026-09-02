from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import Action, ActionType, Decision, Target, WorldState
from .goal_evaluator import GoalEvaluator
from .reasoning_context import ReasoningContext
from .task_runtime import TaskExecutor


STARTUP_POLL_SECONDS = 0.2
STARTUP_TIMEOUT_SECONDS = 5.0
STALE_TARGET_ID = "stale_target"
STALE_TEST_ID = "com.hausshehe.nova:id/stale_test"
INVALIDATE_TARGET_ID = "com.hausshehe.nova:id/stale_invalidate"
FRESH_TARGET_ID = "stale_fresh_target"
GOAL = "Stale transition safety completed"


def _matches_text(element, target_text: str) -> bool:
    """Match the requested label against either visible text or content description."""
    target = target_text.casefold()
    return target in {
        (element.text or "").casefold(),
        (element.content_description or "").casefold(),
    }


class StaleTransitionBridge(AndroidBridge):
    """Inject a real Android transition immediately before a stale action."""

    def __init__(self) -> None:
        super().__init__()
        self.invalidated = False
        self.attempted_stale_click = False
        self.physical_actions: list[str] = []

    def execute(self, action: Action):
        if action.type is ActionType.CLICK and action.target is not None:
            self.physical_actions.append(action.target.element_id)
            if action.target.element_id.endswith(STALE_TARGET_ID) and not self.invalidated:
                invalidate = Action(
                    ActionType.CLICK,
                    Target(INVALIDATE_TARGET_ID, "Invalidate Stale Target", "Invalidate Stale Target"),
                )
                self.physical_actions.append(INVALIDATE_TARGET_ID)
                invalidate_result = super().execute(invalidate)
                if not invalidate_result.accepted:
                    raise RuntimeError(f"failed to invalidate stale target: {invalidate_result}")
                self.invalidated = True
                self.attempted_stale_click = True
        return super().execute(action)


def _wait_for_target(bridge: AndroidBridge, target_text: str) -> WorldState:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while True:
        state = bridge.observe()
        if any(
            _matches_text(element, target_text) and element.clickable and element.visible
            for element in state.elements
        ):
            return state
        if time.monotonic() >= deadline:
            raise RuntimeError(f"target not ready: {target_text}")
        time.sleep(STARTUP_POLL_SECONDS)


def _reset_stale_fixture(bridge: StaleTransitionBridge) -> None:
    """Reset the Android fixture so repeated smoke runs start from the same state."""
    state = _wait_for_target(bridge, "Stale Safety Test")
    reset = Action(
        ActionType.CLICK,
        Target(STALE_TEST_ID, "Stale Safety Test", "Stale Safety Test"),
    )
    result = bridge.execute(reset)
    if not result.accepted:
        raise RuntimeError(f"failed to reset stale fixture: {result}")
    bridge.physical_actions.clear()
    bridge.invalidated = False
    bridge.attempted_stale_click = False
    bridge.wait_for_fresh_observation(state, timeout=2.0)


class StaleSafetyPlanner:
    """Choose the old target once, then require the fresh target after invalidation."""

    def __init__(self) -> None:
        self.calls = 0
        self.observations: list[WorldState] = []

    def decide(self, context: ReasoningContext) -> Decision:
        self.calls += 1
        self.observations.append(context.state)
        ids = {candidate.target.element_id for candidate in context.candidates if candidate.target}
        if self.calls == 1:
            if not any(element.id.endswith(STALE_TARGET_ID) for element in context.state.elements):
                raise AssertionError("initial observation did not contain stale target")
            return Decision(
                Action(ActionType.CLICK, Target(STALE_TARGET_ID, "Stale Target", "Stale Target")),
                "Choose target from initial observation",
            )
        if not any(element.id.endswith(FRESH_TARGET_ID) for element in context.state.elements):
            raise AssertionError("recovery planner did not receive fresh target")
        if any(element.id.endswith(STALE_TARGET_ID) and element.visible for element in context.state.elements):
            raise AssertionError("recovery planner received stale target as visible")
        if FRESH_TARGET_ID not in ids and not any(
            element.id.endswith(FRESH_TARGET_ID) for element in context.state.elements
        ):
            raise AssertionError("fresh target missing from recovery candidates")
        return Decision(
            Action(ActionType.CLICK, Target(FRESH_TARGET_ID, "Fresh Target", "Fresh Target")),
            "Replan from fresh observation after stale target invalidation",
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device TaskExecutor stale observation / transition safety smoke test"
    )
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = StaleTransitionBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch(root=True)
            print(f"LAUNCH {launch}")
            time.sleep(0.5)

        _reset_stale_fixture(bridge)
        ready = _wait_for_target(bridge, "Stale Target")
        print(f"READY observation={ready.observation_id} target=Stale Target")

        planner = StaleSafetyPlanner()
        executor = TaskExecutor(
            bridge=bridge,
            planner=planner,
            evaluator=GoalEvaluator(),
            max_steps=3,
        )
        achieved = executor.run(GOAL)

        if not bridge.attempted_stale_click:
            raise AssertionError("stale-target transition was not injected")
        if bridge.physical_actions[:2] != [STALE_TARGET_ID, INVALIDATE_TARGET_ID]:
            raise AssertionError(
                f"unexpected physical sequence before recovery: {bridge.physical_actions}"
            )
        if executor.current_state is None or not any(
            element.id.endswith(FRESH_TARGET_ID) and element.visible
            for element in executor.current_state.elements
        ):
            raise AssertionError("final observation did not contain fresh target")
        if any(
            element.id.endswith(STALE_TARGET_ID) and element.visible
            for element in planner.observations[-1].elements
        ):
            raise AssertionError("planner was allowed to act on stale target after transition")
        if not achieved:
            raise AssertionError(f"task did not complete; history={executor.history}")
        if bridge.physical_actions[-1] != FRESH_TARGET_ID:
            raise AssertionError(f"fresh target was not executed last: {bridge.physical_actions}")

        print(f"PLANNER CALLS {planner.calls}")
        print(f"OBSERVATIONS {[state.observation_id for state in planner.observations]}")
        print(f"PHYSICAL ACTIONS {bridge.physical_actions}")
        print("STALE TARGET INVALIDATED BEFORE STALE ACTION")
        print("FRESH OBSERVATION FORCED REPLAN")
        print("FRESH TARGET EXECUTED")
        print("GOAL VERIFIED IN FRESH STATE")
        print("TASK EXECUTOR STALE TRANSITION SAFETY VERIFIED")
        print("TASK COMPLETED")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError, AssertionError) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
