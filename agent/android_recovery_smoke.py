from __future__ import annotations

import argparse
import sys

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import Action, ActionType, Decision, ExecutionResult, WorldState
from .goal_evaluator import GoalEvaluator
from .task_runtime import TaskExecutor


class InjectedFailureBridge:
    """Inject one rejected action, then delegate all later actions to Android."""

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
        if not self.failed_once:
            self.failed_once = True
            print("INJECTED FAILURE: primary action rejected")
            return ExecutionResult(accepted=False, changed=False, error="injected recovery failure")
        return self.bridge.execute(action)


class RecoverySmokePlanner:
    """Choose the primary action first and the fallback during recovery."""

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

        executor = TaskExecutor(
            bridge=bridge,
            planner=RecoverySmokePlanner(),
            evaluator=GoalEvaluator(),
            max_steps=args.max_steps,
        )
        achieved = executor.run("Recovery completed")

        if bridge.failed_once:
            print("RECOVERY BOUNDARY: failure routed through recovery path")
        else:
            print("RECOVERY BOUNDARY FAILED: failure injection did not run", file=sys.stderr)
            return 1

        print(f"TASK {'COMPLETED' if achieved else 'NOT COMPLETED'}")
        return 0 if achieved else 1
    except (AndroidBridgeError, TimeoutError, RuntimeError, StopIteration) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
