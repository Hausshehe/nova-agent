"""Real-device smoke for semantic plan-intent completion."""

from __future__ import annotations

import argparse
import json
import subprocess
import time

from nova_core.capability_runtime import build_capability_runtime

from agent.android_bridge import AndroidBridge
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Goal, RunStatus

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"


def _planning_responder_factory():
    calls = 0

    def respond(prompt: str):
        nonlocal calls
        calls += 1
        if calls > 1:
            return {"steps": ["Complete Recovery with Recovery Fallback Action"]}
        return {"steps": ["Attempt Recovery Primary Action"]}

    return respond


def _action_responder(prompt: str):
    payload = json.loads(prompt)
    current = payload["plan"]["current"]
    actions = payload["observation"]["actions"]

    if "fallback" in current.casefold():
        fallback_id = f"{PACKAGE_NAME}:id/recovery_fallback"
        if any(item["id"] == fallback_id and item.get("tap") for item in actions):
            return {"action_type": "tap", "target_id": fallback_id, "reason": current}

        scroll_target = next(
            (
                item["id"]
                for item in actions
                if item.get("scroll")
                and "scrollview" in item.get("class_name", "").casefold()
            ),
            None,
        )
        if scroll_target is not None:
            return {"action_type": "scroll", "target_id": scroll_target, "reason": current}

    return {
        "action_type": "tap",
        "target_id": f"{PACKAGE_NAME}:id/recovery_primary",
        "reason": current,
    }


class RecoveryVerifier:
    def verify(self, goal, before, decision, result, after) -> bool:
        if not result.accepted or not result.changed:
            return False
        return any(
            "recovery completed" in f"{element.text} {element.content_description}".casefold()
            and not element.clickable
            for element in after.elements
        )


def _reset_nova() -> None:
    subprocess.run(["am", "start", "-S", "-n", MAIN_ACTIVITY], check=True, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()
    if args.launch_nova:
        _reset_nova()
    else:
        bridge.launch(root=False)

    deadline = time.monotonic() + 3.0
    while True:
        try:
            bridge.observe()
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.2)

    adapter = AndroidBridgeAdapter(bridge, expected_package=PACKAGE_NAME)
    verifier = RecoveryVerifier()
    planning_responder = _planning_responder_factory()
    runtime = build_capability_runtime(
        Goal("Complete Recovery"), adapter, adapter, verifier,
        action_responders=[("cerebras", _action_responder)],
        planning_responders=[("cerebras", planning_responder)],
        intent_verifier=verifier, max_steps=4, max_replans=1,
    )
    result = runtime.run()
    history = runtime.controller.history
    plan = runtime.brain.plan

    print(f"SEMANTIC_RUNTIME_STATUS={result.status.value}")
    print(f"SEMANTIC_RUNTIME_STEPS={result.steps}")
    print(f"SEMANTIC_REPLANS={runtime.replans}")
    print(f"SEMANTIC_PLAN_CURSOR={plan.cursor if plan else None}")
    print(f"SEMANTIC_PLAN_REVISION={plan.revision if plan else None}")
    print(f"SEMANTIC_PLAN_CURRENT={plan.current.description if plan and plan.current else None!r}")
    for index, step in enumerate(history, start=1):
        print(f"SEMANTIC_ACTION_{index}=target:{step.decision.action.target_id!r} accepted:{step.execution.accepted} changed:{step.execution.changed}")

    expected = (
        result.status is RunStatus.SUCCEEDED and runtime.replans == 1 and len(history) == 4
        and history[0].execution.changed
        and history[1].execution.accepted and not history[1].execution.changed
        and history[2].execution.accepted and not history[2].execution.changed
        and history[3].execution.changed
        and history[3].decision.action.target_id == f"{PACKAGE_NAME}:id/recovery_fallback"
    )
    print(f"SEMANTIC_PROGRESS_ANDROID_SMOKE={'PASS' if expected else 'FAIL'}")
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
