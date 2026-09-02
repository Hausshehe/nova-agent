from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import Action, ActionType, Decision
from .goal_evaluator import GoalEvaluator
from .task_runtime import TaskExecutor


def _matches(element, text: str) -> bool:
    return element.text == text or element.content_description == text


def _find(context, text: str):
    return next(
        (
            candidate.target
            for candidate in context.candidates
            if candidate.target is not None
            and _matches_candidate(candidate, text)
        ),
        None,
    )


def _matches_candidate(candidate, text: str) -> bool:
    target = candidate.target
    return target is not None and (
        target.text == text or target.content_description == text
    )


class MultiStepRuntimePlanner:
    """Drive the Android multi-step fixture through the new TaskExecutor boundary."""

    def decide(self, context):
        labels = {
            element.text
            for element in context.state.elements
            if element.text
        }

        if "Multi-Step Test" in labels:
            target = _find(context, "Multi-Step Test")
            rationale = "r7: enter multi-step test"
        elif "Continue Multi-Step" in labels:
            target = _find(context, "Continue Multi-Step")
            rationale = "r7: continue multi-step test"
        elif "Finish Multi-Step" in labels:
            target = _find(context, "Finish Multi-Step")
            rationale = "r7: finish multi-step test"
        else:
            raise RuntimeError(
                "multi-step fixture is not in an expected state; "
                f"visible labels={sorted(labels)!r}"
            )

        if target is None:
            raise RuntimeError("expected multi-step target was not available")
        return Decision(Action(ActionType.CLICK, target), rationale)


def _wait_for_target(bridge: AndroidBridge, text: str, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while True:
        state = bridge.observe()
        if any(_matches(element, text) for element in state.elements):
            return state
        if time.monotonic() >= deadline:
            raise RuntimeError(f"target {text!r} not observable before timeout")
        time.sleep(0.2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device R7 TaskExecutor multi-step migration smoke test"
    )
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--max-steps", type=int, default=3)
    args = parser.parse_args()

    bridge = AndroidBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch(root=True)
            print(f"LAUNCH {launch}")

        ready = _wait_for_target(bridge, "Multi-Step Test")
        print(f"READY observation={ready.observation_id} target=Multi-Step Test")

        executor = TaskExecutor(
            bridge=bridge,
            planner=MultiStepRuntimePlanner(),
            evaluator=GoalEvaluator(),
            max_steps=args.max_steps,
        )
        achieved = executor.run("Multi-Step Test completed")

        expected_statuses = [
            "Run 1: Step 1 started",
            "Step 2 started",
            "Multi-Step Test completed",
        ]
        observed_statuses = [
            element.text
            for element in (executor.current_state.elements if executor.current_state else ())
            if element.text
        ]
        if not achieved:
            print("R7 MULTI-STEP FAILED: TaskExecutor did not complete the goal", file=sys.stderr)
            return 1
        if "Multi-Step Test completed" not in observed_statuses:
            print(
                "R7 GOAL VERIFICATION FAILED: final TaskExecutor state does not contain "
                "'Multi-Step Test completed'",
                file=sys.stderr,
            )
            return 1

        action_history = [
            item.get("target_text") or item.get("target_id")
            for item in executor.history
        ]
        print(f"HISTORY {action_history}")
        print(f"FINAL_OBSERVATION {executor.current_state.observation_id}")
        print(f"GOAL VERIFIED IN FRESH STATE: Multi-Step Test completed")
        print("TASK EXECUTOR MULTI-STEP MIGRATION VERIFIED")
        print(f"TASK {'COMPLETED' if achieved else 'NOT COMPLETED'}")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError, StopIteration) as exc:
        print(f"R7 MULTI-STEP SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
