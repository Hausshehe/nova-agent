from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import Action, ActionType, Decision
from .goal_evaluator import GoalEvaluator
from .task_runtime import TaskExecutor


def _matches_candidate(candidate, text: str) -> bool:
    target = candidate.target
    return target is not None and (
        target.text == text or target.content_description == text
    )


def _find_target(context, text: str):
    return next(
        (
            candidate.target
            for candidate in context.candidates
            if _matches_candidate(candidate, text)
        ),
        None,
    )


class MultiStepRuntimePlanner:
    """Drive the Android multi-step fixture through the new TaskExecutor boundary."""

    def decide(self, context):
        labels = {element.text for element in context.state.elements if element.text}

        # The fixture keeps all three buttons visible at every step. The status
        # text is therefore the authoritative representation of the fixture's
        # current state, rather than button visibility.
        if "Multi-Step ready" in labels:
            target_text = "Multi-Step Test"
            rationale = "r7: enter multi-step test"
        elif any(label.startswith("Run ") and label.endswith(": Step 1 started") for label in labels):
            target_text = "Continue Multi-Step"
            rationale = "r7: continue multi-step test"
        elif "Step 2 started" in labels:
            target_text = "Finish Multi-Step"
            rationale = "r7: finish multi-step test"
        else:
            raise RuntimeError(
                "multi-step fixture is not in an expected state; "
                f"visible labels={sorted(labels)!r}"
            )

        target = _find_target(context, target_text)
        if target is None:
            raise RuntimeError(f"expected multi-step target {target_text!r} was not available")
        return Decision(Action(ActionType.CLICK, target), rationale)


def _wait_for_target(bridge: AndroidBridge, text: str, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while True:
        state = bridge.observe()
        if any(
            element.text == text or element.content_description == text
            for element in state.elements
        ):
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

        if not achieved:
            print("R7 MULTI-STEP FAILED: TaskExecutor did not complete the goal", file=sys.stderr)
            return 1

        final_state = executor.current_state
        if final_state is None or not any(
            element.text == "Multi-Step Test completed" for element in final_state.elements
        ):
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
        if action_history != ["Multi-Step Test", "Continue Multi-Step", "Finish Multi-Step"]:
            print(
                "R7 ACTION SEQUENCE FAILED: expected "
                "['Multi-Step Test', 'Continue Multi-Step', 'Finish Multi-Step'], "
                f"got {action_history!r}",
                file=sys.stderr,
            )
            return 1

        if not all(item.get("verified") for item in executor.history):
            print("R7 TRANSITION VERIFICATION FAILED: an action was not verified", file=sys.stderr)
            return 1

        print(f"HISTORY {action_history}")
        print(f"FINAL_OBSERVATION {final_state.observation_id}")
        print("ALL THREE ACTION TRANSITIONS VERIFIED")
        print("GOAL VERIFIED IN FRESH STATE: Multi-Step Test completed")
        print("TASK EXECUTOR MULTI-STEP MIGRATION VERIFIED")
        print("TASK COMPLETED")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError, StopIteration) as exc:
        print(f"R7 MULTI-STEP SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
