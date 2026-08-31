from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .deterministic_reasoner import DeterministicReasoner
from .goal_evaluator import GoalEvaluator
from .navigation import NavigationLoop
from .task_runtime import LegacyNavigationExecutor, TaskRuntime


def main() -> int:
    parser = argparse.ArgumentParser(description="Real-device Nova goal-driven navigation smoke test")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--max-steps", type=int, default=5)
    args = parser.parse_args()

    bridge = AndroidBridge()

    try:
        if args.launch_nova:
            launch = bridge.launch(root=True)
            print(f"LAUNCH {launch}")
            time.sleep(0.5)

        before = bridge.observe()
        print(f"OBSERVATION {before.observation_id}")
        print(f"PACKAGE {before.package}")
        print(f"ACTIVITY {before.activity}")
        print(f"ELEMENTS {len(before.elements)}")

        loop = NavigationLoop(
            bridge=bridge,
            planner=DeterministicReasoner(),
            evaluator=GoalEvaluator(),
            max_steps=args.max_steps,
        )
        runtime = TaskRuntime(navigation=LegacyNavigationExecutor(loop))
        result = runtime.run(args.goal)
        print(f"TASK STATUS {result.status.value}")
        print(f"GOAL {'ACHIEVED' if result.success else 'NOT ACHIEVED'}")
        return 0 if result.success else 1
    except (AndroidBridgeError, TimeoutError, RuntimeError) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
