from __future__ import annotations

import argparse
import sys

from .android_bridge import AndroidBridge, AndroidBridgeError


TARGET_TEXT = "Finish Multi-Step"


def _matches_text(element, target_text: str) -> bool:
    return element.text == target_text or element.content_description == target_text


def _find(state, target_text: str):
    return next((e for e in state.elements if _matches_text(e, target_text)), None)


def _scroll_candidates(state):
    return [element for element in state.elements if element.scrollable and element.visible and element.enabled]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova Android accessibility scroll smoke test"
    )
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch()
            print(f"LAUNCH {launch}")

        before = bridge.observe()
        print(f"OBSERVATION {before.observation_id}")
        print(f"PACKAGE {before.package}")
        print(f"ACTIVITY {before.activity}")

        target = _find(before, TARGET_TEXT)
        if target is None:
            raise RuntimeError(f"TARGET NOT FOUND: {TARGET_TEXT!r}")
        print(f"TARGET {target.id} visible={target.visible} enabled={target.enabled}")
        if target.visible:
            raise RuntimeError(f"TARGET IS ALREADY VISIBLE: {TARGET_TEXT!r}")

        scrollables = _scroll_candidates(before)
        if not scrollables:
            raise RuntimeError("NO VISIBLE ENABLED SCROLLABLE CANDIDATE")
        scroll_target = scrollables[0]
        print(f"SCROLL_TARGET {scroll_target.id}")

        response = bridge.scroll(scroll_target.id)
        print(f"SCROLL_RESULT {response}")
        if not response.get("accepted", response.get("ok", False)):
            raise RuntimeError(f"SCROLL NOT ACCEPTED: {response}")

        after = bridge.wait_for_fresh_observation(before)
        print(f"FRESH_OBSERVATION {after.observation_id}")

        target_after = _find(after, TARGET_TEXT)
        if target_after is None:
            raise RuntimeError(f"TARGET DISAPPEARED AFTER SCROLL: {TARGET_TEXT!r}")
        print(f"TARGET_AFTER_SCROLL {target_after.id} visible={target_after.visible}")
        if not target_after.visible:
            raise RuntimeError(f"TARGET STILL NOT VISIBLE AFTER SCROLL: {TARGET_TEXT!r}")

        print("ANDROID_SCROLL_SMOKE PASSED")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError) as exc:
        print(f"ANDROID_SCROLL_SMOKE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
