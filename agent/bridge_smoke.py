from __future__ import annotations

import argparse

from .android_bridge import AndroidBridge, AndroidBridgeError


def _matches_text(element, target_text: str) -> bool:
    return element.text == target_text or element.content_description == target_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Nova Android bridge connectivity")
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--click-text", default=None)
    args = parser.parse_args()

    bridge = AndroidBridge()
    try:
        if args.launch_nova:
            bridge.launch()
        state = bridge.observe()
        print(f"OBSERVATION {state.observation_id}")
        print(f"PACKAGE {state.package}")
        print(f"ACTIVITY {state.activity}")
        print(f"ELEMENTS {len(state.elements)}")
        for element in state.elements:
            if element.text or element.content_description:
                print(f"{element.id} | text={element.text!r} | desc={element.content_description!r} | clickable={element.clickable}")

        if args.click_text is not None:
            target = next((e for e in state.elements if _matches_text(e, args.click_text)), None)
            if target is None:
                print(f"TARGET NOT FOUND: {args.click_text!r}")
                return 2
            before = state.observation_id
            bridge.click(target.id)
            fresh = bridge.wait_for_fresh_observation(before)
            print(f"CLICKED {target.id}")
            print(f"FRESH_OBSERVATION {fresh.observation_id}")
        return 0
    except AndroidBridgeError as exc:
        print(f"BRIDGE ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
