from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError

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


def _status_labels(state) -> list[str]:
    return [
        element.text
        for element in state.elements
        if element.text and not element.clickable
    ]


def _print_state(label: str, state) -> None:
    print(f"{label} observation={state.observation_id} package={state.package}")
    print(f"{label} statuses={_status_labels(state)!r}")


def _click_and_wait(bridge: AndroidBridge, state, target_text: str):
    target = _find_text(state, target_text)
    if target is None:
        raise RuntimeError(f"TARGET NOT FOUND: {target_text!r}")
    result = bridge.click(target.id)
    print(f"CLICK {target_text!r} id={target.id!r} result={result}")
    fresh = bridge.wait_for_fresh_observation(state)
    _print_state("FRESH", fresh)
    return fresh


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose completion observation timing for the v2 Android runtime"
    )
    parser.add_argument("--launch-nova", action="store_true")
    args = parser.parse_args()

    bridge = AndroidBridge()
    try:
        if args.launch_nova:
            print(f"LAUNCH {bridge.launch(root=True)}")
            time.sleep(0.5)

        state = bridge.observe()
        _print_state("INITIAL", state)

        for target in TARGETS:
            state = _click_and_wait(bridge, state, target)

        print("AFTER_FINISH_SETTLING_START")
        for index in range(1, 7):
            time.sleep(0.2)
            state = bridge.observe()
            _print_state(f"POST_FINISH_{index}", state)
        print("AFTER_FINISH_SETTLING_END")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError) as exc:
        print(f"COMPLETION_DIAGNOSTIC_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
