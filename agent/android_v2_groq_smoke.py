"""Bounded real-provider smoke test for Nova's v2 runtime."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from typing import Any, Callable, Mapping

from agent.android_bridge import AndroidBridge
from agent.cerebras_responder import CerebrasResponder
from agent.gemini_responder import GeminiResponder
from agent.groq_responder import GroqResponder
from agent.mistral_responder import MistralResponder
from agent.openrouter_responder import OpenRouterResponder
from agent.provider_pool import ReasoningProviderPool
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.llm_planner import LLMPlanner
from nova_core.models import Goal, RunStatus
from nova_core.reasoning_adapter import LLMReasoner
from nova_core.runtime import Runtime
from nova_core.semantic_verifier import SemanticGoalVerifier

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"
SUPPORTED_PROVIDERS = ("groq", "openrouter", "gemini", "mistral", "cerebras")
BRIDGE_READY_TIMEOUT_SECONDS = 3.0
BRIDGE_READY_POLL_SECONDS = 0.2


def _reset_nova_process(timeout_seconds: float) -> None:
    command = ["am", "start", "-S", "-n", MAIN_ACTIVITY]
    try:
        completed = subprocess.run(command, check=True, timeout=timeout_seconds, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("unable to reset and launch Nova without root: Android 'am' command was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"unable to reset and launch Nova without root: reset timed out after {timeout_seconds}s") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = stderr or stdout or f"exit={exc.returncode}"
        raise RuntimeError(f"unable to reset and launch Nova without root: exit={exc.returncode}; {details}") from exc
    if completed.stdout.strip() or completed.stderr.strip():
        print(f"RESET_COMMAND_OUTPUT={command!r} stdout={completed.stdout.strip()!r} stderr={completed.stderr.strip()!r}")


def _wait_for_bridge(bridge: AndroidBridge, timeout_seconds: float = BRIDGE_READY_TIMEOUT_SECONDS,
                     poll_seconds: float = BRIDGE_READY_POLL_SECONDS) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while True:
        try:
            bridge.observe()
            return
        except Exception as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                break
            time.sleep(poll_seconds)
    raise RuntimeError(f"Nova Android bridge did not become ready within {timeout_seconds}s: {last_error}")


def _configured_responders(model: str | None) -> list[tuple[str, object]]:
    available: dict[str, object] = {}
    if os.environ.get("GROQ_API_KEY"): available["groq"] = GroqResponder(model=model)
    if os.environ.get("OPENROUTER_API_KEY"): available["openrouter"] = OpenRouterResponder()
    if os.environ.get("GEMINI_API_KEY"): available["gemini"] = GeminiResponder()
    if os.environ.get("MISTRAL_API_KEY"): available["mistral"] = MistralResponder()
    if os.environ.get("CEREBRAS_API_KEY"): available["cerebras"] = CerebrasResponder()
    requested = [name.strip().lower() for name in os.environ.get("V2_REASONING_PROVIDER_ORDER", "groq,openrouter,gemini,mistral,cerebras").split(",") if name.strip()]
    unknown = [name for name in requested if name not in SUPPORTED_PROVIDERS]
    if unknown: raise ValueError("unknown reasoning providers: " + ", ".join(unknown))
    return [(name, available[name]) for name in requested if name in available]


def _instrument_responders(responders: list[tuple[str, object]]) -> list[tuple[str, Callable[[str], Mapping[str, Any]]]]:
    instrumented = []
    for name, responder in responders:
        def measured(prompt: str, *, _name=name, _responder=responder) -> Mapping[str, Any]:
            print(f"V2_REASONING_PROMPT_CHARS provider={_name} chars={len(prompt)}")
            return _responder(prompt)  # type: ignore[operator]
        instrumented.append((name, measured))
    return instrumented


def _groq_planner(model: str | None, provider_names: list[str]) -> LLMPlanner | None:
    """Use Groq for mission planning when Groq is actually in the active provider set."""
    if "groq" not in provider_names:
        return None
    responder = GroqResponder(model=model, task="planning")

    def complete(prompt: str) -> str:
        print(f"V2_PLANNING_PROMPT_CHARS provider=groq chars={len(prompt)}")
        return json.dumps(responder(prompt), ensure_ascii=False, separators=(",", ":"))

    return LLMPlanner(complete)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one bounded real-provider v2 Android navigation test")
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--goal", default="Tap Test Navigation Action")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-steps", type=int, default=1)
    args = parser.parse_args()
    if args.max_steps < 1: parser.error("--max-steps must be at least 1")
    try: responders = _configured_responders(args.model)
    except ValueError as exc: parser.error(str(exc))
    if not responders: parser.error("no configured provider from V2_REASONING_PROVIDER_ORDER; set the required provider API key(s)")
    provider_names = [name for name, _ in responders]
    responders = _instrument_responders(responders)
    print("V2_REASONING_PROVIDER_ORDER=" + ",".join(name for name, _ in responders))
    print("V2_REASONING_PROVIDER_BACKUP=" + (",".join(name for name, _ in responders[1:]) or "NONE"))
    planner = _groq_planner(args.model, provider_names)
    print("V2_MISSION_PLANNER=" + ("groq" if planner is not None else "goal-default"))
    bridge = AndroidBridge()
    if args.launch_nova: _reset_nova_process(bridge.timeout)
    else: bridge.launch(root=False)
    _wait_for_bridge(bridge)
    adapter = AndroidBridgeAdapter(bridge, expected_package=PACKAGE_NAME)
    provider_pool = ReasoningProviderPool(responders)
    runtime = Runtime(
        Goal(args.goal), adapter, LLMReasoner(provider_pool), adapter, SemanticGoalVerifier(),
        max_steps=args.max_steps,
        planner=planner,
        replan_after_progress=planner is not None,
        max_replans=max(2, args.max_steps),
    )
    result = runtime.run()
    print("V2_PROVIDER_HEALTH=" + json.dumps(provider_pool.health(), sort_keys=True))
    if runtime.brain.plan is not None:
        plan = runtime.brain.plan
        print(f"V2_MISSION_PLAN revision={plan.revision} cursor={plan.cursor} complete={plan.complete}")
        for index, plan_step in enumerate(plan.steps, start=1):
            print(f"V2_MISSION_PLAN_{index}={plan_step.description!r}")
    print(f"V2_RUNTIME_STATUS={result.status.value}")
    print(f"V2_RUNTIME_STEPS={result.steps}")
    print(f"V2_RUNTIME_ERROR={result.error!r}")
    print("V2_ACTION_TRACE_START")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(f"V2_ACTION_{index}=type:{action.type.value} target_id:{action.target_id!r} value:{action.value!r} accepted:{step.execution.accepted} changed:{step.execution.changed} error:{step.execution.error!r} reason:{step.decision.reason!r}")
    print("V2_ACTION_TRACE_END")
    if result.status is RunStatus.SUCCEEDED:
        print("V2_ANDROID_SMOKE=PASS")
        return 0
    print("V2_ANDROID_SMOKE=FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
