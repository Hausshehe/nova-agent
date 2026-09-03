from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import Action, ActionType, Decision
from .runtime import create_task_runtime


class TracingProvider:
    def __init__(self, provider):
        self.provider = provider

    def decide(self, context):
        print(f"LLM_STEP goal={context.goal!r} observation={context.state.observation_id}")
        decision = self.provider.decide(context)
        print(f"LLM_ACTION {decision.action.type.value}")
        if decision.action.target:
            print(f"LLM_TARGET {decision.action.target.element_id}")
            print(f"LLM_TARGET_TEXT {decision.action.target.text!r}")
        print(f"LLM_RATIONALE {decision.rationale}")
        return decision


def wait_for_label(bridge: AndroidBridge, label: str, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while True:
        state = bridge.observe()
        if any(e.text == label or e.content_description == label for e in state.elements):
            return state
        if time.monotonic() >= deadline:
            raise RuntimeError(f"target {label!r} not observable")
        time.sleep(0.2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Nova clean runtime Groq navigation smoke")
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    bridge = AndroidBridge()
    try:
        if args.launch_nova:
            print(f"LAUNCH {bridge.launch(root=True)}")
        wait_for_label(bridge, "Multi-Step Test")
        from .runtime import create_reasoning_provider
        provider = TracingProvider(create_reasoning_provider("groq", model=args.model))
        runtime = create_task_runtime(
            bridge,
            reasoning_provider=provider,
            max_steps=args.max_steps,
        )
        achieved = runtime.run(args.goal)
        print(f"TASK {'COMPLETED' if achieved else 'NOT COMPLETED'}")
        print(f"HISTORY {runtime.runtime_state.history}")
        if runtime.current_state:
            print(f"FINAL_OBSERVATION {runtime.current_state.observation_id}")
        return 0 if achieved else 1
    except (AndroidBridgeError, RuntimeError, TimeoutError) as exc:
        print(f"CLEAN RUNTIME SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
