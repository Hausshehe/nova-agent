from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError


def _matches_text(element, target_text: str) -> bool:
    return element.text == target_text or element.content_description == target_text


def _print_elements(state) -> None:
    for element in state.elements:
        if element.text or element.content_description:
            print(
                f"{element.id} | text={element.text!r} | "
                f"desc={element.content_description!r} | clickable={element.clickable}"
            )


def _find_text(state, target_text: str):
    return next((e for e in state.elements if _matches_text(e, target_text)), None)


def _click_and_wait(bridge: AndroidBridge, state, target_text: str):
    target = _find_text(state, target_text)
    if target is None:
        raise RuntimeError(f"TARGET NOT FOUND: {target_text!r}")
    bridge.click(target.id)
    fresh = bridge.wait_for_fresh_observation(state)
    print(f"CLICKED {target.id}")
    print(f"FRESH_OBSERVATION {fresh.observation_id}")
    return fresh


def _require_status(state, expected: str) -> None:
    if not any(element.text == expected for element in state.elements):
        raise RuntimeError(f"EXPECTED STATUS NOT FOUND: {expected!r}")
    print(f"STATUS OK: {expected}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova Android multi-step navigation smoke test"
    )
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch()
            print(f"LAUNCH {launch}")
            time.sleep(0.5)

        state = bridge.observe()
        print(f"OBSERVATION {state.observation_id}")
        print(f"PACKAGE {state.package}")
        print(f"ACTIVITY {state.activity}")
        print(f"ELEMENTS {len(state.elements)}")
        _print_elements(state)

        state = _click_and_wait(bridge, state, "Multi-Step Test")
        _require_status(state, "Run 1: Step 1 started")

        state = _click_and_wait(bridge, state, "Continue Multi-Step")
        _require_status(state, "Step 2 started")

        state = _click_and_wait(bridge, state, "Finish Multi-Step")
        _require_status(state, "Multi-Step Test completed")

        print("MULTI_STEP_SMOKE PASSED")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError) as exc:
        print(f"MULTI_STEP_SMOKE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
