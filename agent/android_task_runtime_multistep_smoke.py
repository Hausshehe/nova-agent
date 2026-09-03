from __future__ import annotations

import argparse
import time

from agent.android_bridge import AndroidBridge
from agent.core import Action, ActionType, Decision, Target
from agent.task_runtime import TaskExecutor


STARTUP_POLL_SECONDS = 0.2
STARTUP_TIMEOUT_SECONDS = 5.0


def _find_target(context, text: str) -> Target | None:
    wanted = text.strip().casefold()
    for candidate in context.candidates:
        if (
            candidate.action_type == ActionType.CLICK
            and candidate.target is not None
            and candidate.target.text
            and candidate.target.text.strip().casefold() == wanted
        ):
            return candidate.target
    return None


class MultiStepRuntimePlanner:
    """Drive the Android multi-step fixture through the new TaskExecutor boundary."""

    def decide(self, context):
        labels = {element.text for element in context.state.elements if element.text}
        normalized_labels = {label.strip().casefold() for label in labels}

        # The fixture keeps all three buttons visible at every step. The status
        # text is therefore the authoritative representation of the fixture's
        # current state, rather than button visibility.
        if "multi-step ready" in normalized_labels:
            target_text = "Multi-Step Test"
            rationale = "r7: enter multi-step test"
        elif any(
            label.startswith("run ") and label.endswith(": step 1 started")
            for label in normalized_labels
        ):
            target_text = "Continue Multi-Step"
            rationale = "r7: continue multi-step test"
        elif "step 2 started" in normalized_labels:
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


def _wait_for_target(
    bridge: AndroidBridge,
    target_text: str,
    timeout: float = STARTUP_TIMEOUT_SECONDS,
):
    """Wait for the launched fixture to become observable, without a blind sleep."""
    wanted = target_text.strip().casefold()
    deadline = time.monotonic() + timeout
    while True:
        state = bridge.observe()
        if any(
            element.text
            and element.text.strip().casefold() == wanted
            and element.clickable
            for element in state.elements
        ):
            return state
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for target {target_text!r} after {timeout:.1f}s")
        time.sleep(STARTUP_POLL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()
    if args.launch_nova:
        print(f"LAUNCH {bridge.launch()}")

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
            raise RuntimeError(f"expected {expected!r}, got {actual!r}")

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
