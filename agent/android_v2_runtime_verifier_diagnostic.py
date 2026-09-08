"""Diagnose the exact observations passed through the real v2 runtime verifier."""

from __future__ import annotations

import argparse
import os
import subprocess
from typing import Any, Callable, Mapping

from agent.android_bridge import AndroidBridge
from agent.cerebras_responder import CerebrasResponder
from agent.fallback_responder import FallbackResponder
from agent.gemini_responder import GeminiResponder
from agent.groq_responder import GroqResponder
from agent.mistral_responder import MistralResponder
from agent.openrouter_responder import OpenRouterResponder
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Goal, Observation, RunStatus
from nova_core.reasoning_adapter import LLMReasoner
from nova_core.runtime import Runtime
from nova_core.semantic_verifier import SemanticGoalVerifier

PACKAGE_NAME = "com.hausshehe.nova"
MAIN_ACTIVITY = f"{PACKAGE_NAME}/.MainActivity"
SUPPORTED_PROVIDERS = ("groq", "openrouter", "gemini", "mistral", "cerebras")


def _reset_nova_process(timeout_seconds: float) -> None:
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
                errors.append(f"{command[0]}: exit={exc.returncode} stderr={exc.stderr!r}")
            elif isinstance(exc, subprocess.TimeoutExpired):
                errors.append(f"{command[0]}: timeout after {timeout_seconds}s")
            else:
                errors.append(f"{command[0]}: {exc}")
    raise RuntimeError("unable to reset and launch Nova: " + "; ".join(errors))


def _configured_responders(model: str | None) -> list[tuple[str, object]]:
    available: dict[str, object] = {}
    if os.environ.get("GROQ_API_KEY"):
        available["groq"] = GroqResponder(model=model)
    if os.environ.get("OPENROUTER_API_KEY"):
        available["openrouter"] = OpenRouterResponder()
    if os.environ.get("GEMINI_API_KEY"):
        available["gemini"] = GeminiResponder()
    if os.environ.get("MISTRAL_API_KEY"):
        available["mistral"] = MistralResponder()
    if os.environ.get("CEREBRAS_API_KEY"):
        available["cerebras"] = CerebrasResponder()
    raw_order = os.environ.get("V2_REASONING_PROVIDER_ORDER", "groq,openrouter,gemini,mistral,cerebras")
    requested = [name.strip().lower() for name in raw_order.split(",") if name.strip()]
    unknown = [name for name in requested if name not in SUPPORTED_PROVIDERS]
    if unknown:
        raise ValueError("unknown reasoning providers: " + ", ".join(unknown))
    return [(name, available[name]) for name in requested if name in available]


def _instrument_responders(responders: list[tuple[str, object]]) -> list[tuple[str, Callable[[str], Mapping[str, Any]]]]:
    wrapped: list[tuple[str, Callable[[str], Mapping[str, Any]]]] = []
    for name, responder in responders:
        def measured(prompt: str, *, _name=name, _responder=responder) -> Mapping[str, Any]:
            print(f"V2_REASONING_PROMPT_CHARS provider={_name} chars={len(prompt)}")
            return _responder(prompt)  # type: ignore[operator]
        wrapped.append((name, measured))
    return wrapped


class _LoggingVerifier:
    """Log every field relevant to completion verification, then delegate unchanged."""

    def __init__(self) -> None:
        self.inner = SemanticGoalVerifier()

    @staticmethod
    def _visible_elements(observation: Observation) -> list[dict[str, object]]:
        return [
            {
                "id": e.id,
                "text": e.text,
                "content_description": e.content_description,
                "visible": e.visible,
                "clickable": e.clickable,
                "enabled": e.enabled,
            }
            for e in observation.elements
            if e.visible
        ]

    def verify(self, goal, before, decision, result, after) -> bool:
        verdict = self.inner.verify(goal, before, decision, result, after)
        print(
            f"V2_VERIFIER goal={goal.text!r} action={decision.action.type.value!r} "
            f"target={decision.action.target_id!r} accepted={result.accepted} changed={result.changed} "
            f"before_revision={before.revision} after_revision={after.revision} verdict={verdict}"
        )
        print(f"V2_VERIFIER_BEFORE_VISIBLE={self._visible_elements(before)!r}")
        print(f"V2_VERIFIER_AFTER_VISIBLE={self._visible_elements(after)!r}")
        return verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Instrument v2 runtime goal verification on a real Android device")
    parser.add_argument("--launch-nova", action="store_true")
    parser.add_argument("--goal", default="Finish Multi-Step")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-steps", type=int, default=5)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps must be at least 1")

    responders = _configured_responders(args.model)
    if not responders:
        parser.error("no configured provider from V2_REASONING_PROVIDER_ORDER")
    responders = _instrument_responders(responders)

    print("V2_REASONING_PROVIDER_ORDER=" + ",".join(name for name, _ in responders))
    print("V2_REASONING_PROVIDER_BACKUP=" + (",".join(name for name, _ in responders[1:]) or "NONE"))

    bridge = AndroidBridge()
    if args.launch_nova:
        _reset_nova_process(bridge.timeout)
    else:
        bridge.launch()

    adapter = AndroidBridgeAdapter(bridge, expected_package=PACKAGE_NAME)
    runtime = Runtime(
        Goal(args.goal),
        adapter,
        LLMReasoner(FallbackResponder(responders)),
        adapter,
        _LoggingVerifier(),
        max_steps=args.max_steps,
    )
    result = runtime.run()
    print(f"V2_RUNTIME_STATUS={result.status.value}")
    print(f"V2_RUNTIME_STEPS={result.steps}")
    print(f"V2_RUNTIME_ERROR={result.error!r}")
    for index, step in enumerate(runtime.controller.history, start=1):
        action = step.decision.action
        print(
            f"V2_ACTION_{index}=type:{action.type.value} target_id:{action.target_id!r} "
            f"accepted:{step.execution.accepted} changed:{step.execution.changed} "
            f"error:{step.execution.error!r} reason:{step.decision.reason!r}"
        )
    return 0 if result.status is RunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
