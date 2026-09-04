"""Controlled real-device smoke test for the v2 LLM reasoning boundary.

The responder is deterministic on purpose. This test validates that the v2
runtime can consume a model-shaped structured response without involving a
network provider or API key.
"""

from __future__ import annotations

import argparse
import json

from agent.android_bridge import AndroidBridge
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Goal, RunStatus
from nova_core.reasoning_adapter import LLMReasoner
from nova_core.runtime import Runtime
from nova_core.semantic_verifier import SemanticGoalVerifier


def _controlled_responder(prompt: str) -> dict[str, object]:
    payload = json.loads(prompt)
    elements = payload["observation"]["elements"]
    target = next(
        (
            element
            for element in elements
            if element["text"].casefold() == "test navigation action"
            and element["clickable"]
            and element["enabled"]
            and element["visible"]
        ),
        None,
    )
    if target is None:
        return {
            "action_type": "tap",
            "target_id": "missing",
            "reason": "controlled smoke responder found no safe target",
        }
    return {
        "action_type": "tap",
        "target_id": target["id"],
        "reason": "controlled model-shaped decision",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the v2 LLM reasoning boundary against a real Android device"
    )
    parser.add_argument("--launch-nova", action="store_true", help="launch Nova before running")
    parser.add_argument(
        "--goal",
        default="Tap Test Navigation Action",
        help="goal used by the controlled responder",
    )
    args = parser.parse_args()

    bridge = AndroidBridge()
    if args.launch_nova:
        bridge.launch()

    adapter = AndroidBridgeAdapter(bridge)
    runtime = Runtime(
        Goal(args.goal),
        adapter,
        LLMReasoner(_controlled_responder),
        adapter,
        SemanticGoalVerifier(),
        max_steps=1,
    )

    result = runtime.run()
    print(f"V2_LLM_RUNTIME_STATUS={result.status.value}")
    print(f"V2_LLM_RUNTIME_STEPS={result.steps}")
    print(f"V2_LLM_RUNTIME_ERROR={result.error!r}")

    print("V2_LLM_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(
            f"V2_LLM_ACTION_{index}=type:{action.type.value} "
            f"target_id:{action.target_id!r} value:{action.value!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed} "
            f"error:{step.execution.error!r} reason:{step.decision.reason!r}"
        )
    print("V2_LLM_ACTION_TRACE_END")

    if result.status is RunStatus.SUCCEEDED:
        print("V2_LLM_ANDROID_SMOKE=PASS")
        return 0

    print("V2_LLM_ANDROID_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
