"""Diagnostic for the launch-to-accessibility observation window."""

from __future__ import annotations

import argparse
import subprocess
import time

from agent.android_bridge import AndroidBridge

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"


def reset_nova() -> None:
    command = ["am", "start", "-S", "-n", MAIN_ACTIVITY]
    try:
        completed = subprocess.run(command, check=True, timeout=3.0, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"unable to launch Nova without root: {exc}") from exc
    print(f"LAUNCH_COMMAND={command!r} stdout={completed.stdout.strip()!r} stderr={completed.stderr.strip()!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect observations immediately after launching Nova")
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--interval-ms", type=int, default=200)
    args = parser.parse_args()
    if args.samples < 1: parser.error("--samples must be at least 1")
    if args.interval_ms < 1: parser.error("--interval-ms must be at least 1")
    bridge = AndroidBridge()
    reset_nova()
    start = time.monotonic()
    for index in range(args.samples):
        state = bridge.observe()
        elapsed_ms = int((time.monotonic() - start) * 1000)
        preview = [{"id": e.id, "text": e.text, "description": e.content_description, "clickable": e.clickable, "enabled": e.enabled} for e in state.elements[:12]]
        print(f"LAUNCH_SAMPLE={index + 1} elapsed_ms={elapsed_ms} observation_id={state.observation_id!r} package={state.package!r} activity={state.activity!r} element_count={len(state.elements)} elements={preview!r}")
        if index + 1 < args.samples: time.sleep(args.interval_ms / 1000.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
