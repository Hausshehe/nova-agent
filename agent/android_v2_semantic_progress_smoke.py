"""Real-device smoke for semantic plan-intent completion."""

from __future__ import annotations

import argparse
import subprocess
import time

from agent.android_bridge import AndroidBridge
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Action, ActionType, Decision, Goal, RunStatus
from nova_core.planning import Plan, PlanStep
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"


class SemanticProgressPlanner:
    def plan(self, context: ReasoningContext) -> Plan:
        return Plan((PlanStep("Attempt Recovery Primary Action"),), revision=0)

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        return Plan((PlanStep("Complete Recovery with Recovery Fallback Action"),), revision=previous.revision + 1)


class SemanticProgressReasoner:
    def decide(self, context: ReasoningContext) -> Decision:
        assert context.plan is not None and context.plan.current is not None
        intent = context.plan.current.description.casefold()
        target_id = (
            f"{PACKAGE_NAME}:id/recovery_fallback"
            if "fallback" in intent
            else f"{PACKAGE_NAME}:id/recovery_primary"
        )
        return Decision(Action(ActionType.TAP, target_id=target_id), reason=context.plan.current.description)


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
    runtime = Runtime(
        Goal("Complete Recovery"),
        adapter,
        SemanticProgressReasoner(),
        adapter,
        verifier,
        intent_verifier=verifier,
        max_steps=2,
        max_replans=1,
        planner=SemanticProgressPlanner(),
    )
    result = runtime.run()
    history = runtime.controller.history
    plan = runtime.brain.plan

    print(f"SEMANTIC_RUNTIME_STATUS={result.status.value}")
    print(f"SEMANTIC_RUNTIME_STEPS={result.steps}")
    print(f"SEMANTIC_REPLANS={runtime.replans}")
    print(f"SEMANTIC_PLAN_CURSOR={plan.cursor if plan else None}")
    print(f"SEMANTIC_PLAN_REVISION={plan.revision if plan else None}")
    for index, step in enumerate(history, start=1):
        print(
            f"SEMANTIC_ACTION_{index}=target:{step.decision.action.target_id!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed}"
        )

    expected = (
        result.status is RunStatus.SUCCEEDED
        and runtime.replans == 1
        and len(history) == 4
        and history[0].execution.changed
        and history[1].execution.accepted
        and not history[1].execution.changed
        and history[2].execution.accepted
        and not history[2].execution.changed
        and history[3].execution.changed
        and history[3].decision.action.target_id == f"{PACKAGE_NAME}:id/recovery_fallback"
    )
    print(f"SEMANTIC_PROGRESS_ANDROID_SMOKE={'PASS' if expected else 'FAIL'}")
    return 0 if expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
