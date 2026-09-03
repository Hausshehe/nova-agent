from __future__ import annotations

import argparse
import sys

from .android_bridge import AndroidBridge, AndroidBridgeError
from .reasoning_provider import ReasoningProvider
from .runtime import create_reasoning_provider, create_task_executor


class TracingReasoningProvider:
    """Print each reasoning decision while preserving the production provider."""

    def __init__(self, provider: ReasoningProvider):
        self._provider = provider

    def decide(self, context):
        print(f"LLM_STEP goal={context.goal!r} observation={context.state.observation_id}")
        try:
            decision = self._provider.decide(context)
        except Exception as exc:
            print(f"LLM_ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
            raise
        target = decision.action.target
        print(f"LLM_ACTION {decision.action.type.value}")
        print(f"LLM_TARGET {target.element_id if target else None}")
        print(f"LLM_TARGET_TEXT {target.text if target else ''!r}")
        print(f"LLM_RATIONALE {decision.rationale}")
        return decision


class TracingBridge(AndroidBridge):
    """Print execution and observation transitions for the real-device smoke."""

    def observe(self):
        state = super().observe()
        print(f"OBSERVATION {state.observation_id} ELEMENTS {len(state.elements)}")
        for element in state.elements:
            label = " ".join(
                part for part in (element.text, element.content_description) if part
            ).strip()
            if label:
                print(f"OBSERVED_TEXT id={element.id} text={label!r}")
        return state

    def execute(self, action):
        target = action.target
        print(
            f"EXECUTE {action.type.value} "
            f"target={target.element_id if target else None}"
        )
        result = super().execute(action)
        print(
            f"EXECUTION_RESULT accepted={result.accepted} "
            f"changed={result.changed} error={result.error!r}"
        )
        return result

    def wait_for_fresh_observation(self, previous, timeout=2.0):
        print(f"WAIT_FRESH after={previous.observation_id} timeout={timeout}")
        state = super().wait_for_fresh_observation(previous, timeout)
        print(f"FRESH_OBSERVATION {state.observation_id}")
        return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova multi-step LLM navigation smoke test"
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-steps", type=int, default=3)
    args = parser.parse_args()

    bridge = TracingBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch()
            print(f"LAUNCH {launch}")

        provider = create_reasoning_provider("groq", model=args.model)
        tracing_provider = TracingReasoningProvider(provider)
        executor = create_task_executor(
            bridge,
            reasoning_provider=tracing_provider,
            max_steps=args.max_steps,
        )

        achieved = executor.run(args.goal)
        print(f"GOAL {'ACHIEVED' if achieved else 'NOT ACHIEVED'}")
        return 0 if achieved else 1
    except (AndroidBridgeError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"SMOKE FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
