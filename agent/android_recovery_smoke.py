from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import Action, ActionType, Decision, ExecutionResult, WorldState
from .goal_evaluator import GoalEvaluator
from .task_runtime import TaskExecutor


def _matches_element_id(actual: str, expected: str) -> bool:
    """Match Android resource IDs whether namespaced or shorthand."""
    return actual == expected or actual.endswith(f":id/{expected}")


class InjectedFailureBridge:
    """Execute the primary click on Android, then report a synthetic failure."""

    def __init__(self, bridge: AndroidBridge):
        self.bridge = bridge
        self.failed_once = False
        self.executed_actions: list[str] = []

    def observe(self) -> WorldState:
        return self.bridge.observe()

    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState:
        return self.bridge.wait_for_fresh_observation(previous, timeout)

    def launch(self, **kwargs):
        return self.bridge.launch(**kwargs)

    def execute(self, action: Action) -> ExecutionResult:
        target_id = action.target.element_id if action.target is not None else None

        if action.type is ActionType.CLICK and target_id is not None:
            if _matches_element_id(target_id, "recovery_primary") and not self.failed_once:
                self.failed_once = True
                print("ACTION 1: CLICK recovery_primary")
                result = self.bridge.execute(action)
                if not result.accepted:
                    print("PHYSICAL ACTION FAILED: recovery_primary was rejected by Android")
                    return result
                self.executed_actions.append("recovery_primary")
                print("PHYSICAL ACTION EXECUTED: recovery_primary")
                print("INJECTED FAILURE: primary action reported as failed after physical click")
                return ExecutionResult(
                    accepted=False,
                    changed=False,
                    error="injected recovery failure after physical primary click",
                )

            if _matches_element_id(target_id, "recovery_fallback"):
                print("ACTION 2: CLICK recovery_fallback")
                result = self.bridge.execute(action)
                if result.accepted:
                    self.executed_actions.append("recovery_fallback")
                    print("PHYSICAL ACTION EXECUTED: recovery_fallback")
                return result

        return self.bridge.execute(action)


class RecoverySmokePlanner:
    """Choose the primary action first and the fallback after recovery."""

    def decide(self, context):
        if not any(
            _matches_element_id(item.get("target_id", ""), "recovery_primary")
            for item in context.history
        ):
            target = next(
                candidate.target
                for candidate in context.candidates
                if candidate.target
                and _matches_element_id(candidate.target.element_id, "recovery_primary")
            )
            return Decision(
                Action(ActionType.CLICK, target),
                "smoke: choose primary before injected failure",
            )

        target = next(
            candidate.target
            for candidate in context.candidates
            if candidate.target
            and _matches_element_id(candidate.target.element_id, "recovery_fallback")
        )
        return Decision(
            Action(ActionType.CLICK, target),
            "smoke: choose fallback during recovery",
        )


def _wait_for_target(bridge: AndroidBridge, element_id: str, timeout: float = 2.0) -> WorldState:
    """Wait for the launched activity's target to become observable."""
    deadline = time.monotonic() + timeout
    while True:
        state = bridge.observe()
        if any(_matches_element_id(element.id, element_id) for element in state.elements):
            return state
        if time.monotonic() >= deadline:
            ids = ", ".join(element.id for element in state.elements)
            raise RuntimeError(f"target {element_id!r} not observable; current ids: {ids}")
        time.sleep(0.2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova RecoveryEngine physical recovery smoke test"
    )
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--max-steps", type=int, default=2)
    args = parser.parse_args()

    android = AndroidBridge()
    bridge = InjectedFailureBridge(android)

    try:
        if args.launch_nova:
            launch = bridge.launch(root=True)
            print(f"LAUNCH {launch}")

        ready = _wait_for_target(android, "recovery_primary")
        print(f"READY observation={ready.observation_id} target=recovery_primary")

        executor = TaskExecutor(
            bridge=bridge,
            planner=RecoverySmokePlanner(),
            evaluator=GoalEvaluator(),
            max_steps=args.max_steps,
        )
        achieved = executor.run("Recovery completed")

        if bridge.executed_actions != ["recovery_primary", "recovery_fallback"]:
            print(
                "RECOVERY BOUNDARY FAILED: expected physical action sequence "
                f"['recovery_primary', 'recovery_fallback'], got {bridge.executed_actions!r}",
                file=sys.stderr,
            )
            return 1

        fallback_used = any(
            _matches_element_id(item.get("target_id", ""), "recovery_fallback")
            and item.get("accepted")
            for item in executor.history
        )
        if not fallback_used:
            print("RECOVERY BOUNDARY FAILED: fallback was not accepted", file=sys.stderr)
            return 1

        final_state = bridge.observe()
        if not any(element.text == "Recovery completed" for element in final_state.elements):
            print("RECOVERY BOUNDARY FAILED: final observation lacks 'Recovery completed'", file=sys.stderr)
            return 1

        print("PHYSICAL SEQUENCE VERIFIED: recovery_primary -> recovery_fallback")
        print("RECOVERY BOUNDARY: physical failure routed through recovery path")
        print(f"TASK {'COMPLETED' if achieved else 'NOT COMPLETED'}")
        return 0 if achieved else 1
    except (AndroidBridgeError, TimeoutError, RuntimeError, StopIteration) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
