"""Deterministic real-device smoke test for F.7 safe replanning."""

from __future__ import annotations

import argparse

from agent.android_bridge import AndroidBridge
from agent.android_v2_groq_smoke import _reset_nova_process, _wait_for_bridge
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Action, ActionType, Decision, Goal, RunStatus
from nova_core.planning import Plan, PlanStep
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime
from nova_core.semantic_verifier import SemanticGoalVerifier

PACKAGE_NAME = "com.hausshehe.nova"


class ReplanningSmokePlanner:
    """Force unchanged primary actions, then replace them with fallback."""

    def __init__(self) -> None:
        self.plan_calls = 0
        self.replan_calls = 0

    def plan(self, context: ReasoningContext) -> Plan:
        self.plan_calls += 1
        return Plan(
            (
                PlanStep("tap Recovery Primary Action"),
                PlanStep("tap Recovery Primary Action"),
            ),
            revision=0,
        )

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        self.replan_calls += 1
        return Plan((PlanStep("tap Recovery Fallback Action"),), revision=previous.revision + 1)


class ReplanningSmokeReasoner:
    """Translate the deterministic smoke plan into real Android actions."""

    def decide(self, context: ReasoningContext) -> Decision:
        assert context.plan is not None
        assert context.plan.current is not None
        description = context.plan.current.description
        if "Fallback" in description:
            target_id = "com.hausshehe.nova:id/recovery_fallback"
        else:
            target_id = "com.hausshehe.nova:id/recovery_primary"
        return Decision(
            Action(ActionType.TAP, target_id=target_id),
            reason=description,
        )


def _print_live_target_diagnostic(bridge: AndroidBridge, target_id: str) -> None:
    """Print the live accessibility tree after an Android target-missing failure."""
    print("F7_TARGET_DIAGNOSTIC_START")
    try:
        state = bridge.observe()
    except Exception as exc:
        print(f"F7_TARGET_DIAGNOSTIC_ERROR={exc!r}")
        print("F7_TARGET_DIAGNOSTIC_END")
        return

    print(f"F7_DIAGNOSTIC_OBSERVATION_ID={state.observation_id!r}")
    print(f"F7_DIAGNOSTIC_PACKAGE={state.package!r}")
    print(f"F7_DIAGNOSTIC_ACTIVITY={state.activity!r}")
    print(f"F7_DIAGNOSTIC_ELEMENT_COUNT={len(state.elements)}")

    target = next((element for element in state.elements if element.id == target_id), None)
    if target is None:
        print(f"F7_DIAGNOSTIC_TARGET_PRESENT=False target_id={target_id!r}")
    else:
        print(
            f"F7_DIAGNOSTIC_TARGET_PRESENT=True target_id={target.id!r} "
            f"text={target.text!r} content={target.content_description!r} "
            f"clickable={target.clickable} enabled={target.enabled} visible={target.visible} "
            f"bounds={target.bounds!r}"
        )

    for element in state.elements:
        haystack = f"{element.id} {element.text} {element.content_description}".lower()
        if "recovery" in haystack:
            print(
                f"F7_DIAGNOSTIC_RECOVERY_ELEMENT="
                f"id={element.id!r} text={element.text!r} content={element.content_description!r} "
                f"clickable={element.clickable} enabled={element.enabled} visible={element.visible} "
                f"bounds={element.bounds!r}"
            )
    print("F7_TARGET_DIAGNOSTIC_END")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the F.7 real-device accepted-unchanged replanning smoke test")
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()
    if args.launch_nova:
        _reset_nova_process(bridge.timeout)
    else:
        bridge.launch(root=False)
    _wait_for_bridge(bridge)

    adapter = AndroidBridgeAdapter(bridge, expected_package=PACKAGE_NAME)
    planner = ReplanningSmokePlanner()
    reasoner = ReplanningSmokeReasoner()
    runtime = Runtime(
        Goal("Complete Recovery"),
        adapter,
        reasoner,
        adapter,
        SemanticGoalVerifier(),
        max_steps=4,
        max_replans=1,
        planner=planner,
    )
    result = runtime.run()

    print(f"F7_REPLAN_PLAN_CALLS={planner.plan_calls}")
    print(f"F7_REPLAN_REPLAN_CALLS={planner.replan_calls}")
    print(f"F7_REPLAN_COUNT={runtime.replans}")
    print(f"F7_RUNTIME_STATUS={result.status.value}")
    print(f"F7_RUNTIME_STEPS={result.steps}")
    print(f"F7_RUNTIME_ERROR={result.error!r}")
    print("F7_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(
            f"F7_ACTION_{index}=type:{action.type.value} target_id:{action.target_id!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed} "
            f"error:{step.execution.error!r} reason:{step.decision.reason!r}"
        )
        if not step.execution.accepted and action.target_id:
            _print_live_target_diagnostic(bridge, action.target_id)
    print("F7_ACTION_TRACE_END")

    history = runtime.controller.history
    expected = (
        result.status is RunStatus.SUCCEEDED
        and result.error is None
        and planner.plan_calls == 1
        and planner.replan_calls == 1
        and runtime.replans == 1
        and len(history) == 4
        and history[0].execution.accepted
        and history[0].execution.changed
        and history[1].execution.accepted
        and not history[1].execution.changed
        and history[2].execution.accepted
        and not history[2].execution.changed
        and history[3].execution.accepted
        and history[3].execution.changed
        and history[3].decision.action.target_id == "com.hausshehe.nova:id/recovery_fallback"
    )
    if expected:
        print("F7_ANDROID_REPLAN_SMOKE=PASS")
        return 0
    print("F7_ANDROID_REPLAN_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
