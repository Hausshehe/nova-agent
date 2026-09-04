"""Single bounded real-provider smoke test for Nova's v2 runtime."""

from __future__ import annotations

import argparse
import os
import subprocess

from agent.android_bridge import AndroidBridge
from agent.fallback_responder import FallbackResponder
from agent.gemini_responder import GeminiResponder
from agent.groq_responder import GroqResponder
from agent.openrouter_responder import OpenRouterResponder
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Goal, RunStatus
from nova_core.reasoning_adapter import LLMReasoner
from nova_core.runtime import Runtime
from nova_core.semantic_verifier import SemanticGoalVerifier


PACKAGE_NAME = "com.hausshehe.nova"


def _reset_nova_process(timeout_seconds: float) -> None:
    """Stop Nova so Activity-local state cannot leak between smoke runs."""
    commands = [
        ["su", "-c", f"am force-stop --user 0 {PACKAGE_NAME}"],
        ["su", "-c", f"am force-stop {PACKAGE_NAME}"],
        ["am", "force-stop", "--user", "0", PACKAGE_NAME],
        ["am", "force-stop", PACKAGE_NAME],
    ]
    errors: list[str] = []

    for command in commands:
        try:
            subprocess.run(
                command,
                check=True,
                timeout=timeout_seconds,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{command[0]}: {exc}")

    raise RuntimeError(
        "unable to force-stop Nova; refusing to run a stateful smoke test without a reset: "
        + "; ".join(errors)
    )


def _configured_responders(model: str | None) -> list[tuple[str, object]]:
    responders: list[tuple[str, object]] = []
    if os.environ.get("GROQ_API_KEY"):
        responders.append(("groq", GroqResponder(model=model)))
    if os.environ.get("OPENROUTER_API_KEY"):
        responders.append(("openrouter", OpenRouterResponder()))
    if os.environ.get("GEMINI_API_KEY"):
        responders.append(("gemini", GeminiResponder()))
    return responders


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded real-provider v2 Android navigation test")
    parser.add_argument("--launch-nova", action="store_true", help="reset and launch Nova before running")
    parser.add_argument("--goal", default="Tap Test Navigation Action")
    parser.add_argument("--model", default=None, help="override NOVA_GROQ_MODEL for the Groq provider")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=1,
        help="maximum number of actions the runtime may execute",
    )
    args = parser.parse_args()

    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1")

    responders = _configured_responders(args.model)
    if not responders:
        parser.error("set at least one of GROQ_API_KEY, OPENROUTER_API_KEY, or GEMINI_API_KEY")

    bridge = AndroidBridge()
    if args.launch_nova:
        _reset_nova_process(bridge.timeout)
        bridge.launch()

    adapter = AndroidBridgeAdapter(bridge)
    responder = FallbackResponder(responders)
    runtime = Runtime(
        Goal(args.goal),
        adapter,
        LLMReasoner(responder),
        adapter,
        SemanticGoalVerifier(),
        max_steps=args.max_steps,
    )

    result = runtime.run()
    print(f"V2_GROQ_RUNTIME_STATUS={result.status.value}")
    print(f"V2_GROQ_RUNTIME_STEPS={result.steps}")
    print(f"V2_GROQ_RUNTIME_ERROR={result.error!r}")
    print("V2_GROQ_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(
            f"V2_GROQ_ACTION_{index}=type:{action.type.value} "
            f"target_id:{action.target_id!r} value:{action.value!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed} "
            f"error:{step.execution.error!r} reason:{step.decision.reason!r}"
        )
    print("V2_GROQ_ACTION_TRACE_END")

    if result.status is RunStatus.SUCCEEDED:
        print("V2_GROQ_ANDROID_SMOKE=PASS")
        return 0

    print("V2_GROQ_ANDROID_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
