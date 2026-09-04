"""Real-device end-to-end smoke test for the native Nova Agent v2 runtime."""

from __future__ import annotations

import argparse

from agent.android_bridge import AndroidBridge
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.deterministic_reasoner import DeterministicReasoner
from nova_core.models import Goal, RunStatus
from nova_core.runtime import Runtime
from nova_core.semantic_verifier import SemanticGoalVerifier


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the native v2 deterministic runtime against a real Android device"
    )
    parser.add_argument("--launch-nova", action="store_true", help="launch Nova before running")
    parser.add_argument("--goal", required=True, help="goal, e.g. 'Tap Test Navigation Action'")
    parser.add_argument("--max-steps", type=int, default=1, help="maximum action steps")
    args = parser.parse_args()

    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1")

    bridge = AndroidBridge()
    if args.launch_nova:
        bridge.launch()

    adapter = AndroidBridgeAdapter(bridge)
    runtime = Runtime(
        Goal(args.goal),
        adapter,
        DeterministicReasoner(),
        adapter,
        SemanticGoalVerifier(),
        max_steps=args.max_steps,
    )

    result = runtime.run()
    print(f"V2_RUNTIME_STATUS={result.status.value}")
    print(f"V2_RUNTIME_STEPS={result.steps}")
    print(f"V2_RUNTIME_ERROR={result.error!r}")

    print("V2_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(
            f"V2_ACTION_{index}=type:{action.type.value} "
            f"target_id:{action.target_id!r} value:{action.value!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed} "
            f"error:{step.execution.error!r} reason:{step.decision.reason!r}"
        )
    print("V2_ACTION_TRACE_END")

    if result.status is RunStatus.SUCCEEDED:
        print("V2_ANDROID_RUNTIME_SMOKE=PASS")
        return 0

    print("V2_ANDROID_RUNTIME_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
