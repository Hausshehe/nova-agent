from __future__ import annotations

import argparse

from .android_bridge import AndroidBridge, AndroidBridgeError


def _matches_text(element, target_text: str) -> bool:
    return element.text == target_text or element.content_description == target_text


def _print_elements(state) -> None:
    for element in state.elements:
        if element.text or element.content_description:
            print(f"{element.id} | text={element.text!r} | desc={element.content_description!r} | clickable={element.clickable}")


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
        _print_elements(state)

        if args.click_text is not None:
            target = next((e for e in state.elements if _matches_text(e, args.click_text)), None)
            if target is None:
                print(f"TARGET NOT FOUND: {args.click_text!r}")
                return 2
            before = state
            bridge.click(target.id)
            fresh = bridge.wait_for_fresh_observation(before)
            print(f"CLICKED {target.id}")
            print(f"FRESH_OBSERVATION {fresh.observation_id}")
            print(f"FRESH_ELEMENTS {len(fresh.elements)}")
            _print_elements(fresh)
        return 0
    except AndroidBridgeError as exc:
        print(f"BRIDGE ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
