"""Real-device smoke test for the v2 Android adapter.

This deliberately exercises only the Android seam. It does not invoke a
reasoner or the v2 runtime, so failures here can be attributed to Android
transport/translation rather than planning semantics.
"""

from __future__ import annotations

import argparse

from agent.android_bridge import AndroidBridge
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Action, ActionType


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _find_element(observation, text: str):
    needle = _normalize(text)
    for element in observation.elements:
        values = (element.text, element.content_description)
        if any(value and _normalize(value) == needle for value in values):
            return element
    return None


def _print_observed_elements(observation) -> None:
    print("OBSERVED_ELEMENTS:")
    for element in observation.elements:
        text = _normalize(element.text) if element.text else ""
        description = _normalize(element.content_description) if element.content_description else ""
        if text or description:
            print(
                f"  id={element.id!r} text={text!r} "
                f"content_description={description!r} "
                f"clickable={element.clickable} enabled={element.enabled} visible={element.visible}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Nova v2 Android adapter on a real device")
    parser.add_argument("--launch-nova", action="store_true", help="launch Nova before observing")
    parser.add_argument("--click-text", required=True, help="exact visible text/content description to tap")
    args = parser.parse_args()

    bridge = AndroidBridge()
    adapter = AndroidBridgeAdapter(bridge)

    if args.launch_nova:
        bridge.launch()

    before_legacy = bridge.observe()
    before = adapter.observe()
    print(f"V2_OBSERVATION revision={before.revision} package={before.package} activity={before.activity}")
    print(f"V2_ELEMENTS count={len(before.elements)}")

    target = _find_element(before, args.click_text)
    if target is None:
        print(f"ERROR target not found: {args.click_text!r}")
        _print_observed_elements(before)
        return 1
    if not target.clickable or not target.enabled or not target.visible:
        print(
            "ERROR target not actionable: "
            f"clickable={target.clickable} enabled={target.enabled} visible={target.visible}"
        )
        return 1

    result = adapter.execute(Action(ActionType.TAP, target_id=target.id))
    print(
        "V2_EXECUTION "
        f"accepted={result.accepted} changed={result.changed} error={result.error!r}"
    )
    if not result.accepted or not result.changed:
        return 1

    try:
        after_legacy = bridge.wait_for_fresh_observation(before_legacy, timeout=2.0, poll_seconds=0.2)
    except TimeoutError as exc:
        print(f"ERROR no fresh Android observation: {exc}")
        return 1

    after = adapter.observe()
    print(f"V2_AFTER revision={after.revision} package={after.package} activity={after.activity}")
    print(f"V2_AFTER_ELEMENTS count={len(after.elements)}")
    print(f"ANDROID_OBSERVATION_CHANGED={after_legacy != before_legacy}")
    print(f"V2_REVISION_ADVANCED={after.revision > before.revision}")

    if after_legacy == before_legacy or after.revision <= before.revision:
        print("ERROR v2 adapter did not observe a fresh changed state")
        return 1

    print("V2_ANDROID_SMOKE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
