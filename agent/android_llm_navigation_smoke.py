from __future__ import annotations

import argparse
import sys

from .android_bridge import AndroidBridge, AndroidBridgeError
from .groq import groq_transport
from .llm_reasoning_provider import LLMReasoningProvider
from .navigation import NavigationLoop


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova multi-step LLM navigation smoke test"
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-steps", type=int, default=3)
    args = parser.parse_args()

    bridge = AndroidBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch(root=True)
            print(f"LAUNCH {launch}")

        transport = groq_transport(model=args.model)
        provider = LLMReasoningProvider(transport.complete)
        loop = NavigationLoop(
            bridge=bridge,
            planner=provider,
            max_steps=args.max_steps,
        )

        achieved = loop.run(args.goal)
        print(f"GOAL {'ACHIEVED' if achieved else 'NOT ACHIEVED'}")
        return 0 if achieved else 1
    except (AndroidBridgeError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
