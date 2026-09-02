from __future__ import annotations

import argparse
import time

from agent.android_bridge import AndroidBridge
from agent.core import Action, ActionType, Decision, Target
from agent.task_runtime import TaskExecutor


def _find_target(context, text: str) -> Target | None:
    for candidate in context.candidates:
        if candidate.element.text == text:
            return candidate.target
    return None


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


def _wait_for_target(bridge: AndroidBridge, target_text: str, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while True:
        state = bridge.observe()
        if any(element.text == target_text and element.clickable for element in state.elements):
            return state
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for target {target_text!r}")
        time.sleep(0.2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()
    if args.launch_nova:
        print(f"LAUNCH {bridge.launch(root=True)}")

    try:
        ready = _wait_for_target(bridge, "Multi-Step Test")
        print(f"READY observation={ready.observation_id} target=Multi-Step Test")

        runtime = TaskExecutor(
            bridge=bridge,
            planner=MultiStepRuntimePlanner(),
            max_steps=3,
        )
        completed = runtime.run("Multi-Step Test completed")

        history = [
            item
            for item in runtime.history
            if item.get("action_type") == ActionType.CLICK.value
        ]
        expected = ["Multi-Step Test", "Continue Multi-Step", "Finish Multi-Step"]
        actual = [item.get("target_text", "") for item in history]
        normalized_actual = [value.strip().casefold() for value in actual]
        normalized_expected = [value.casefold() for value in expected]

        if normalized_actual != normalized_expected:
            raise RuntimeError(
                f"expected {expected!r}, got {actual!r}"
            )

        if not completed:
            raise RuntimeError("TaskExecutor did not report task completion")

        final_state = runtime.current_state
        if final_state is None or "Multi-Step Test completed" not in {
            element.text for element in final_state.elements if element.text
        }:
            raise RuntimeError("completion was not observed in the final fresh state")

        if not all(item.get("verified") for item in history):
            raise RuntimeError("not all multi-step transitions were verified")

        print(f"HISTORY {actual}")
        print(f"FINAL_OBSERVATION {final_state.observation_id}")
        print("ALL THREE ACTION TRANSITIONS VERIFIED")
        print("GOAL VERIFIED IN FRESH STATE: Multi-Step Test completed")
        print("TASK EXECUTOR MULTI-STEP MIGRATION VERIFIED")
        print("TASK COMPLETED")
        return 0
    except Exception as exc:
        print(f"R7 ACTION SEQUENCE FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
