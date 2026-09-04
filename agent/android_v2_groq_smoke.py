"""Single bounded real-Groq smoke test for Nova's v2 runtime."""

from __future__ import annotations

import argparse

from agent.android_bridge import AndroidBridge
from agent.groq_responder import GroqResponder
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Goal, RunStatus
from nova_core.reasoning_adapter import LLMReasoner
from nova_core.runtime import Runtime
from nova_core.semantic_verifier import SemanticGoalVerifier


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real Groq-backed v2 Android navigation test")
    parser.add_argument("--launch-nova", action="store_true", help="launch Nova before running")
    parser.add_argument("--goal", default="Tap Test Navigation Action")
    parser.add_argument("--model", default=None, help="override NOVA_GROQ_MODEL for this run")
    args = parser.parse_args()

    bridge = AndroidBridge()
    if args.launch_nova:
        bridge.launch()

    adapter = AndroidBridgeAdapter(bridge)
    responder = GroqResponder(model=args.model)
    runtime = Runtime(
        Goal(args.goal),
        adapter,
        LLMReasoner(responder),
        adapter,
        SemanticGoalVerifier(),
        max_steps=1,
    )

    result = runtime.run()
    print(f"V2_GROQ_RUNTIME_STATUS={result.status.value}")
    print(f"V2_GROQ_RUNTIME_STEPS={result.steps}")
    print(f"V2_GROQ_RUNTIME_ERROR={result.error!r}")
    print("V2_GROQ_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(
            f"V2_GROQ_ACTION_{index}=type:{action.type.value} "
            f"target_id:{action.target_id!r} value:{action.value!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed} "
            f"error:{step.execution.error!r} reason:{step.decision.reason!r}"
        )
    print("V2_GROQ_ACTION_TRACE_END")

    if result.status is RunStatus.SUCCEEDED:
        print("V2_GROQ_ANDROID_SMOKE=PASS")
        return 0

    print("V2_GROQ_ANDROID_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
