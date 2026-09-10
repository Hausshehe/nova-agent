"""Bounded real-provider smoke test for F.7 LLM mission replanning."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from typing import Any

from agent.android_bridge import AndroidBridge
from agent.groq_responder import GroqResponder
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.llm_planner import LLMPlanner
from nova_core.models import Action, ActionType, Decision, Goal, RunStatus
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"
BRIDGE_READY_TIMEOUT_SECONDS = 3.0
BRIDGE_READY_POLL_SECONDS = 0.2


def _reset_nova_process(timeout_seconds: float) -> None:
    command = ["am", "start", "-S", "-n", MAIN_ACTIVITY]
    try:
        completed = subprocess.run(
            command,
            check=True,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Android 'am' command was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Nova reset timed out after {timeout_seconds}s") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or f"exit={exc.returncode}").strip()
        raise RuntimeError(f"Nova reset failed: {details}") from exc
    if completed.stdout.strip() or completed.stderr.strip():
        print(
            f"RESET_COMMAND_OUTPUT={command!r} "
            f"stdout={completed.stdout.strip()!r} stderr={completed.stderr.strip()!r}"
        )


def _wait_for_bridge(bridge: AndroidBridge) -> None:
    deadline = time.monotonic() + BRIDGE_READY_TIMEOUT_SECONDS
    last_error: Exception | None = None
    while True:
        try:
            bridge.observe()
            return
        except Exception as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                break
            time.sleep(BRIDGE_READY_POLL_SECONDS)
    raise RuntimeError(f"Nova bridge did not become ready: {last_error}")


class LLMReplanningReasoner:
    """Keep action selection deterministic so this smoke isolates LLM planning."""

    def decide(self, context: ReasoningContext) -> Decision:
        assert context.plan is not None
        assert context.plan.current is not None
        intent = context.plan.current.description.lower()
        if "fallback" in intent:
            target_id = "com.hausshehe.nova:id/recovery_fallback"
        elif "primary" in intent:
            target_id = "com.hausshehe.nova:id/recovery_primary"
        else:
            raise ValueError(f"LLM planner produced unsupported smoke intent: {context.plan.current.description!r}")
        return Decision(Action(ActionType.TAP, target_id=target_id), reason=context.plan.current.description)


class RecoverySmokeVerifier:
    """Verify the concrete recovery result without testing the general verifier."""

    def verify(self, goal, before, decision, result, after) -> bool:
        if not result.accepted or not result.changed:
            return False
        # The recovery status is the authoritative completion marker for this
        # harness. It may be outside the current viewport because the controls
        # live inside a ScrollView, so Accessibility visibility is not a safe
        # requirement for this smoke's terminal-state assertion.
        return any(
            "recovery completed" in f"{element.text} {element.content_description}".casefold()
            and not element.clickable
            for element in after.elements
        )


def _groq_planner(model: str | None) -> tuple[LLMPlanner, GroqResponder]:
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not configured")
    responder = GroqResponder(model=model, task="planning")

    def complete(prompt: str) -> str:
        print(f"V2_PLANNING_PROMPT_CHARS provider=groq chars={len(prompt)}")
        payload = responder(prompt)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    return LLMPlanner(complete), responder


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded real-Groq F.7 replanning on Android")
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    planner, _ = _groq_planner(args.model)
    bridge = AndroidBridge()
    if args.launch_nova:
        _reset_nova_process(bridge.timeout)
    else:
        bridge.launch(root=False)
    _wait_for_bridge(bridge)

    adapter = AndroidBridgeAdapter(bridge, expected_package=PACKAGE_NAME)
    reasoner = LLMReplanningReasoner()
    goal = Goal(
        "Complete Recovery: the initial plan must attempt Recovery Primary Action twice; "
        "if the primary action stops making observable progress, replan to Recovery Fallback Action."
    )
    runtime = Runtime(
        goal,
        adapter,
        reasoner,
        adapter,
        RecoverySmokeVerifier(),
        max_steps=2,
        max_replans=1,
        planner=planner,
    )
    result = runtime.run()

    plan = runtime.brain.plan
    print(f"F7_LLM_PLAN_CALLS=1")
    print(f"F7_LLM_REPLAN_COUNT={runtime.replans}")
    print(f"F7_LLM_RUNTIME_STATUS={result.status.value}")
    print(f"F7_LLM_RUNTIME_STEPS={result.steps}")
    print(f"F7_LLM_RUNTIME_ERROR={result.error!r}")
    if plan is not None:
        print(f"F7_LLM_FINAL_PLAN revision={plan.revision} cursor={plan.cursor} complete={plan.complete}")
        for index, step in enumerate(plan.steps, start=1):
            print(f"F7_LLM_FINAL_PLAN_{index}={step.description!r}")
    print("F7_LLM_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(
            f"F7_LLM_ACTION_{index}=type:{action.type.value} target_id:{action.target_id!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed} "
            f"error:{step.execution.error!r} reason:{step.decision.reason!r}"
        )
    print("F7_LLM_ACTION_TRACE_END")

    history = runtime.controller.history
    expected = (
        result.status is RunStatus.SUCCEEDED
        and result.steps == 2
        and result.error is None
        and runtime.replans == 1
        and len(history) == 4
        and history[0].execution.accepted
        and history[0].execution.changed
        and history[1].execution.accepted
        and not history[1].execution.changed
        and history[2].execution.accepted
        and not history[2].execution.changed
        and history[3].execution.accepted
        and history[3].execution.changed
        and history[3].decision.action.target_id == "com.hausshehe.nova:id/recovery_fallback"
        and plan is not None
        and plan.revision == 1
    )
    if expected:
        print("F7_LLM_ANDROID_REPLAN_SMOKE=PASS")
        return 0
    print("F7_LLM_ANDROID_REPLAN_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
