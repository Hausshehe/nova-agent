from __future__ import annotations

import argparse
import sys

from .android_bridge import AndroidBridge, AndroidBridgeError
from .groq import groq_transport
from .llm_reasoning_provider import LLMReasoningProvider
from .reasoning_context import build_reasoning_context


def _print_elements(state) -> None:
    for element in state.elements:
        if element.text or element.content_description:
            print(
                f"{element.id} | text={element.text!r} | "
                f"desc={element.content_description!r} | clickable={element.clickable} | "
                f"enabled={element.enabled}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova observation to Groq decision smoke test"
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    bridge = AndroidBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch(root=True)
            print(f"LAUNCH {launch}")

        state = bridge.observe()
        print(f"OBSERVATION {state.observation_id}")
        print(f"PACKAGE {state.package}")
        print(f"ACTIVITY {state.activity}")
        print(f"ELEMENTS {len(state.elements)}")
        _print_elements(state)

        context = build_reasoning_context(args.goal, state, [])
        transport = groq_transport(model=args.model)
        provider = LLMReasoningProvider(transport.complete)
        decision = provider.decide(context)

        print(f"ACTION_TYPE {decision.action.type.value}")
        if decision.action.target is None:
            print("TARGET_ID None")
        else:
            print(f"TARGET_ID {decision.action.target.element_id}")
            print(f"TARGET_TEXT {decision.action.target.text!r}")
        print(f"RATIONALE {decision.rationale}")
        print("EXECUTED False")
        return 0
    except (AndroidBridgeError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
