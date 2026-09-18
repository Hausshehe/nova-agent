"""Real-device smoke test for Nova's native Android agent runtime."""

from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one real Android goal through Nova's DeepSeek-native reasoning runtime"
    )
    parser.add_argument("--goal", required=True)
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--deadline-ms", type=int, default=0)
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.deadline_ms < 0:
        parser.error("--deadline-ms must not be negative")

    bridge = AndroidBridge(timeout=5.0)

    try:
        if args.launch_nova:
            launch = bridge.launch(root=False)
            print(f"LAUNCH {launch}")
            time.sleep(1.0)

        started = bridge.start_agent(args.goal, args.deadline_ms)
        print(f"AGENT_START {started}")

        deadline = time.monotonic() + args.timeout
        last_status = None

        while time.monotonic() < deadline:
            task = bridge.agent_status().get("task")

            if not isinstance(task, dict):
                time.sleep(0.5)
                continue

            status = str(task.get("status", ""))
            summary = (
                f"status={status} "
                f"steps={task.get('steps', 0)} "
                f"observation={task.get('observationId', 0)} "
                f"last_action={task.get('lastAction', '')!r} "
                f"outcome={task.get('lastOutcome', '')!r}"
            )

            if summary != last_status:
                print(summary)
                last_status = summary

            if status == "succeeded":
                print("NATIVE_ANDROID_AGENT_SMOKE=PASS")
                return 0

            if status in {"failed", "cancelled"}:
                print(f"TASK_ERROR={task.get('error')!r}", file=sys.stderr)
                print("NATIVE_ANDROID_AGENT_SMOKE=FAIL")
                return 1

            time.sleep(0.5)

        print("NATIVE_ANDROID_AGENT_SMOKE=TIMEOUT", file=sys.stderr)
        return 2

    except (AndroidBridgeError, TimeoutError, RuntimeError, ValueError) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
