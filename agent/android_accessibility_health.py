"""Check whether Nova is operational after install/relaunch without using root."""

from __future__ import annotations

import argparse
import sys

from .android_bridge import AndroidBridge, AndroidBridgeError


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Nova bridge and Accessibility service health")
    parser.add_argument("--require-operational", action="store_true")
    args = parser.parse_args()
    try:
        health = AndroidBridge().health()
    except AndroidBridgeError as exc:
        print(f"ACCESSIBILITY_HEALTH_ERROR={exc}", file=sys.stderr)
        return 1
    print(f"ACCESSIBILITY_HEALTH={health}")
    if args.require_operational and not bool(health.get("operational", False)):
        print("ACCESSIBILITY_HEALTH=FAIL", file=sys.stderr)
        return 1
    print("ACCESSIBILITY_HEALTH=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
