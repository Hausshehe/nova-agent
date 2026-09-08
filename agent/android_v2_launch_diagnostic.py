"""Diagnostic for the launch-to-accessibility observation window.

This intentionally does not modify Nova runtime behavior. It launches Nova with
-S, then samples the bridge observations for a short period so we can determine
whether the first accessibility snapshot still reflects the previous app.
"""

from __future__ import annotations

import argparse
import subprocess
import time

from agent.android_bridge import AndroidBridge

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"


def reset_nova() -> None:
    commands = [
        ["su", "-c", f"am start -S -n {MAIN_ACTIVITY}"],
        ["am", "start", "-S", "-n", MAIN_ACTIVITY],
    ]
    errors: list[str] = []
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                check=True,
                timeout=3.0,
                capture_output=True,
                text=True,
            )
            print(
                f"LAUNCH_COMMAND={command!r} "
                f"stdout={completed.stdout.strip()!r} "
                f"stderr={completed.stderr.strip()!r}"
            )
            return
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{command[0]}: {exc}")
    raise RuntimeError("unable to launch Nova: " + "; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect observations immediately after launching Nova")
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--interval-ms", type=int, default=200)
    args = parser.parse_args()

    if args.samples < 1:
        parser.error("--samples must be at least 1")
    if args.interval_ms < 1:
        parser.error("--interval-ms must be at least 1")

    bridge = AndroidBridge()
    reset_nova()

    start = time.monotonic()
    for index in range(args.samples):
        state = bridge.observe()
        elapsed_ms = int((time.monotonic() - start) * 1000)
        preview = [
            {
                "id": element.id,
                "text": element.text,
                "description": element.content_description,
                "clickable": element.clickable,
            }
            for element in state.elements[:12]
        ]
        print(
            f"LAUNCH_SAMPLE={index + 1} "
            f"elapsed_ms={elapsed_ms} "
            f"observation_id={state.observation_id!r} "
            f"package={state.package!r} "
            f"activity={state.activity!r} "
            f"element_count={len(state.elements)} "
            f"elements={preview!r}"
        )
        if index + 1 < args.samples:
            time.sleep(args.interval_ms / 1000.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
