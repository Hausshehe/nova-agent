from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError


TARGET_TEXT = "Finish Multi-Step"


def _find_target(state):
    return next(
        (
            element
            for element in state.elements
            if element.text == TARGET_TEXT
            or element.content_description == TARGET_TEXT
        ),
        None,
    )


def _print_state(label: str, state) -> None:
    print(
        f"{label}: observation={state.observation_id} "
        f"package={state.package} activity={state.activity} "
        f"elements={len(state.elements)}"
    )
    for element in state.elements:
        if element.text or element.content_description:
            print(
                f"  {element.id} | text={element.text!r} | "
                f"desc={element.content_description!r} | "
                f"clickable={element.clickable} enabled={element.enabled}"
            )


def _attempt_click(bridge: AndroidBridge, state, attempt: int):
    target = _find_target(state)
    if target is None:
        raise RuntimeError(f"TARGET NOT FOUND: {TARGET_TEXT!r}")

    print(
        f"ATTEMPT {attempt}: target={target.id} "
        f"clickable={target.clickable} enabled={target.enabled}"
    )
    started = time.monotonic()
    try:
        response = bridge.click(target.id)
        elapsed = time.monotonic() - started
        print(f"CLICK {attempt}: RETURNED in {elapsed:.3f}s response={response}")
    except AndroidBridgeError as exc:
        elapsed = time.monotonic() - started
        print(f"CLICK {attempt}: ERROR in {elapsed:.3f}s error={exc}")

    observed_started = time.monotonic()
    try:
        fresh = bridge.observe()
        observed_elapsed = time.monotonic() - observed_started
        _print_state(f"POST_CLICK_{attempt} ({observed_elapsed:.3f}s)", fresh)
        return fresh
    except AndroidBridgeError as exc:
        observed_elapsed = time.monotonic() - observed_started
        print(f"POST_CLICK_{attempt}: OBSERVE ERROR in {observed_elapsed:.3f}s error={exc}")
        return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Controlled real-device reproduction for repeated Android bridge clicks"
    )
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--attempts", type=int, default=2)
    args = parser.parse_args()

    if args.attempts < 1:
        parser.error("--attempts must be >= 1")

    # A short client timeout makes a server-side performAction hang observable
    # without waiting several seconds for every attempt.
    bridge = AndroidBridge(timeout=1.0)

    try:
        if args.launch_nova:
            launch = bridge.launch()
            print(f"LAUNCH {launch}")
            time.sleep(0.5)

        state = bridge.observe()
        _print_state("INITIAL", state)

        for attempt in range(1, args.attempts + 1):
            state = _attempt_click(bridge, state, attempt)

        print("BRIDGE_REPEAT_CLICK_SMOKE COMPLETED")
        print("Interpret timings and errors above; this diagnostic intentionally does not claim the bridge is healthy.")
        return 0
    except (AndroidBridgeError, TimeoutError, RuntimeError) as exc:
        print(f"BRIDGE_REPEAT_CLICK_SMOKE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
