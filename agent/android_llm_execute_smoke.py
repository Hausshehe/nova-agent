from __future__ import annotations

import argparse
import sys

from .android_bridge import AndroidBridge, AndroidBridgeError
from .core import ActionType, ExecutionResult, TransitionVerifier
from .groq import groq_transport
from .llm_reasoning_provider import LLMReasoningProvider
from .reasoning_context import build_reasoning_context


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova observation to Groq decision and single-action execution smoke test"
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

        before = bridge.observe()
        print(f"BEFORE_OBSERVATION {before.observation_id}")
        print(f"PACKAGE {before.package}")
        print(f"ACTIVITY {before.activity}")
        print(f"BEFORE_ELEMENTS {len(before.elements)}")

        context = build_reasoning_context(args.goal, before, [])
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

        if decision.action.type is not ActionType.CLICK or decision.action.target is None:
            print("SMOKE FAILED: expected a clickable target decision", file=sys.stderr)
            return 2

        result = bridge.execute(decision.action)
        print(f"EXECUTION_ACCEPTED {result.accepted}")
        print(f"EXECUTION_CHANGED {result.changed}")
        print(f"EXECUTION_ERROR {result.error!r}")

        if not result.accepted:
            print("SMOKE FAILED: Android rejected the LLM action", file=sys.stderr)
            return 2

        after = bridge.wait_for_fresh_observation(before, timeout=2.0)
        changed = after != before
        verification_result = ExecutionResult(
            accepted=True,
            changed=changed,
            verified=False,
            error=result.error,
        )
        verified = TransitionVerifier().verify(before, after, verification_result)

        print(f"AFTER_OBSERVATION {after.observation_id}")
        print(f"AFTER_ELEMENTS {len(after.elements)}")
        print(f"STATE_CHANGED {changed}")
        print(f"TRANSITION_VERIFIED {verified}")

        if not verified:
            print("SMOKE FAILED: executed action did not produce a verified state transition", file=sys.stderr)
            return 2

        print("EXECUTED True")
        print("SMOKE PASSED")
        return 0
    except (AndroidBridgeError, RuntimeError, TimeoutError, ValueError) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
