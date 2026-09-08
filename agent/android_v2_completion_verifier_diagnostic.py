from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from nova_core.models import Action, ActionType, Decision, Goal
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.semantic_verifier import SemanticGoalVerifier

TARGETS = (
    "Multi-Step Test",
    "Continue Multi-Step",
    "Finish Multi-Step",
)


def _find_text(state, target_text: str):
    return next(
        (
            element
            for element in state.elements
            if element.text == target_text or element.content_description == target_text
        ),
        None,
    )


def _status_labels(observation) -> list[str]:
    return [
        element.text
        for element in observation.elements
        if element.text and not element.clickable
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose v2 semantic completion verification against real Android observations"
    )
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()
    adapter = AndroidBridgeAdapter(bridge, expected_package="com.hausshehe.nova")
    verifier = SemanticGoalVerifier()
    goal = Goal("Finish Multi-Step Test")

    try:
        if args.launch_nova:
            print(f"LAUNCH {bridge.launch(root=True)}")
            time.sleep(0.5)

        before = adapter.observe()
        print(f"INITIAL revision={before.revision} package={before.package}")
        print(f"INITIAL statuses={_status_labels(before)!r}")

        for target_text in TARGETS:
            target = _find_text(bridge.observe(), target_text)
            if target is None:
                raise RuntimeError(f"TARGET NOT FOUND: {target_text!r}")

            decision = Decision(
                action=Action(ActionType.TAP, target_id=target.id),
                reason="controlled completion diagnostic",
                target_label=target_text,
            )
            result = adapter.execute(decision.action)
            after = adapter.observe_fresh(before)
            verified = verifier.verify(goal, before, decision, result, after)

            print(
                f"STEP target={target_text!r} accepted={result.accepted} "
                f"changed={result.changed} before_revision={before.revision} "
                f"after_revision={after.revision} verified={verified}"
            )
            print(f"AFTER statuses={_status_labels(after)!r}")

            before = after

        if not verified:
            print("V2_COMPLETION_VERIFIER=FAIL")
            return 1

        print("V2_COMPLETION_VERIFIER=PASS")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError) as exc:
        print(f"COMPLETION_VERIFIER_DIAGNOSTIC_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
