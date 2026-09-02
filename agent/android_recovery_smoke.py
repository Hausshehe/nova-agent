from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import Action, ActionType, Decision, ExecutionResult, WorldState
from .goal_evaluator import GoalEvaluator
from .task_runtime import TaskExecutor


class InjectedFailureBridge:
    """Reject exactly the primary recovery action, then delegate to Android."""

    def __init__(self, bridge: AndroidBridge):
        self.bridge = bridge
        self.failed_once = False

    def observe(self) -> WorldState:
        return self.bridge.observe()

    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState:
        return self.bridge.wait_for_fresh_observation(previous, timeout)

    def launch(self, **kwargs):
        return self.bridge.launch(**kwargs)

    def execute(self, action: Action) -> ExecutionResult:
        if action.type is ActionType.CLICK and action.target is not None:
            if action.target.element_id == "recovery_primary" and not self.failed_once:
                self.failed_once = True
                print("INJECTED FAILURE: primary action rejected")
                return ExecutionResult(
                    accepted=False,
                    changed=False,
                    error="injected recovery failure",
                )
        return self.bridge.execute(action)


class RecoverySmokePlanner:
    """Choose the primary action first and the fallback after recovery."""

    def decide(self, context):
        if not any(item.get("target_id") == "recovery_primary" for item in context.history):
            target = next(
                candidate.target
                for candidate in context.candidates
                if candidate.target and candidate.target.element_id == "recovery_primary"
            )
            return Decision(
                Action(ActionType.CLICK, target),
                "smoke: choose primary before injected failure",
            )

        target = next(
            candidate.target
            for candidate in context.candidates
            if candidate.target and candidate.target.element_id == "recovery_fallback"
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
        if any(element.id == element_id for element in state.elements):
            return state
        if time.monotonic() >= deadline:
            ids = ", ".join(element.id for element in state.elements)
            raise RuntimeError(f"target {element_id!r} not observable; current ids: {ids}")
        time.sleep(0.2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova RecoveryEngine boundary smoke test"
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

        if not bridge.failed_once:
            print("RECOVERY BOUNDARY FAILED: primary failure was not injected", file=sys.stderr)
            return 1

        fallback_used = any(
            item.get("target_id") == "recovery_fallback" and item.get("accepted")
            for item in executor.history
        )
        if not fallback_used:
            print("RECOVERY BOUNDARY FAILED: fallback was not executed", file=sys.stderr)
            return 1

        print("RECOVERY BOUNDARY: failure routed through recovery path")
        print(f"TASK {'COMPLETED' if achieved else 'NOT COMPLETED'}")
        return 0 if achieved else 1
    except (AndroidBridgeError, TimeoutError, RuntimeError, StopIteration) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
