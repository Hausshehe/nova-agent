"""Bounded real-provider smoke test for Nova's v2 runtime."""

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
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"
SUPPORTED_PROVIDERS = ("groq", "openrouter", "gemini")


def _reset_nova_process(timeout_seconds: float) -> None:
    """Reset and launch Nova so Activity-local state cannot leak between runs."""
    commands = [
        ["su", "-c", f"am start -S -n {MAIN_ACTIVITY}"],
        ["am", "start", "-S", "-n", MAIN_ACTIVITY],
    ]
    errors: list[str] = []
    for command in commands:
        try:
            completed = subprocess.run(command, check=True, timeout=timeout_seconds, capture_output=True, text=True)
            if completed.stdout.strip() or completed.stderr.strip():
                print(f"RESET_COMMAND_OUTPUT={command!r} stdout={completed.stdout.strip()!r} stderr={completed.stderr.strip()!r}")
            return
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                stdout = exc.stdout.strip() if isinstance(exc.stdout, str) else ""
                stderr = exc.stderr.strip() if isinstance(exc.stderr, str) else ""
                errors.append(f"{command[0]}: exit={exc.returncode} stdout={stdout!r} stderr={stderr!r}")
            elif isinstance(exc, subprocess.TimeoutExpired):
                errors.append(f"{command[0]}: timeout after {timeout_seconds}s")
            else:
                errors.append(f"{command[0]}: {exc}")
    raise RuntimeError("unable to reset and launch Nova; refusing to run a stateful smoke test without a reset: " + "; ".join(errors))


def _configured_responders(model: str | None) -> list[tuple[str, object]]:
    available: dict[str, object] = {}
    if os.environ.get("GROQ_API_KEY"):
        available["groq"] = GroqResponder(model=model)
    if os.environ.get("OPENROUTER_API_KEY"):
        available["openrouter"] = OpenRouterResponder()
    if os.environ.get("GEMINI_API_KEY"):
        available["gemini"] = GeminiResponder()

    raw_order = os.environ.get("V2_REASONING_PROVIDER_ORDER", "groq,openrouter,gemini")
    requested = [name.strip().lower() for name in raw_order.split(",") if name.strip()]
    unknown = [name for name in requested if name not in SUPPORTED_PROVIDERS]
    if unknown:
        raise ValueError("unknown reasoning providers: " + ", ".join(unknown))

    return [(name, available[name]) for name in requested if name in available]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded real-provider v2 Android navigation test")
    parser.add_argument("--launch-nova", action="store_true", help="reset and launch Nova before running")
    parser.add_argument("--goal", default="Tap Test Navigation Action")
    parser.add_argument("--model", default=None, help="override NOVA_GROQ_MODEL for the Groq provider")
    parser.add_argument("--max-steps", type=int, default=1, help="maximum number of actions the runtime may execute")
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1")

    try:
        responders = _configured_responders(args.model)
    except ValueError as exc:
        parser.error(str(exc))
    if not responders:
        parser.error("no configured provider from V2_REASONING_PROVIDER_ORDER; set the required provider API key(s)")

    print("V2_REASONING_PROVIDER_ORDER=" + ",".join(name for name, _ in responders))
    print("V2_REASONING_PROVIDER_BACKUP=" + (",".join(name for name, _ in responders[1:]) or "NONE"))

    bridge = AndroidBridge()
    if args.launch_nova:
        _reset_nova_process(bridge.timeout)
    else:
        bridge.launch()

    adapter = AndroidBridgeAdapter(bridge)
    responder = FallbackResponder(responders)
    runtime = Runtime(Goal(args.goal), adapter, LLMReasoner(responder), adapter, SemanticGoalVerifier(), max_steps=args.max_steps)
    result = runtime.run()

    print(f"V2_GROQ_RUNTIME_STATUS={result.status.value}")
    print(f"V2_GROQ_RUNTIME_STEPS={result.steps}")
    print(f"V2_GROQ_RUNTIME_ERROR={result.error!r}")
    print("V2_GROQ_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(f"V2_GROQ_ACTION_{index}=type:{action.type.value} target_id:{action.target_id!r} value:{action.value!r} accepted:{step.execution.accepted} changed:{step.execution.changed} error:{step.execution.error!r} reason:{step.decision.reason!r}")
    print("V2_GROQ_ACTION_TRACE_END")
    if result.status is RunStatus.SUCCEEDED:
        print("V2_GROQ_ANDROID_SMOKE=PASS")
        return 0
    print("V2_GROQ_ANDROID_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
