from __future__ import annotations

import argparse
import sys
import time

from .android_bridge import AndroidBridge, AndroidBridgeError
from .deterministic_reasoner import DeterministicReasoner
from .goal_evaluator import GoalEvaluator
from .task_runtime import TaskExecutor


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Real-device Nova TaskExecutor observation-boundary smoke test"
    )
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

        executor = TaskExecutor(
            bridge=bridge,
            planner=DeterministicReasoner(),
            evaluator=GoalEvaluator(),
            max_steps=args.max_steps,
        )
        achieved = executor.run(args.goal)
        print(f"TASK {'COMPLETED' if achieved else 'NOT COMPLETED'}")
        return 0 if achieved else 1
    except (AndroidBridgeError, TimeoutError, RuntimeError) as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
