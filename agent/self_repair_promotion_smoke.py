"""Run one real-device promotion experiment with a trusted validation pipeline.

The Groq model proposes the repair. Nova owns every validation command:
1. build the candidate APK in the isolated promotion worktree,
2. install that APK on the connected Android device,
3. run the existing bounded LLM navigation smoke against the candidate source.

The model cannot choose, edit, reorder, or skip these commands. The live
checkout is changed only after every stage passes.
"""

from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path

from agent.groq_responder import GroqResponder
from nova_core.improvement.orchestrator import SelfImprovementOrchestrator
from nova_core.improvement.policy import ImprovementDecision
from nova_core.improvement.promotion import PromotionPolicy, RepairPromotionGate
from nova_core.improvement.validation import ValidationPolicy
from nova_core.models import RunResult, RunStatus


def _command(name: str, default: str) -> tuple[str, ...]:
    raw = os.environ.get(name, default).strip()
    if not raw:
        raise ValueError(f"{name} must not be empty")
    command = tuple(shlex.split(raw))
    if not command:
        raise ValueError(f"{name} must contain a command")
    return command


def _promotion_commands(goal: str) -> tuple[tuple[str, ...], ...]:
    build = _command("NOVA_PROMOTION_BUILD_COMMAND", "gradle :app:assembleDebug")
    install = _command(
        "NOVA_PROMOTION_INSTALL_COMMAND",
        "adb install -r app/build/outputs/apk/debug/app-debug.apk",
    )
    smoke_raw = os.environ.get(
        "NOVA_PROMOTION_SMOKE_COMMAND",
        f"python -m agent.android_v2_groq_smoke --launch-nova --goal {shlex.quote(goal)} --max-steps 3",
    ).strip()
    smoke = tuple(shlex.split(smoke_raw))
    if not smoke:
        raise ValueError("NOVA_PROMOTION_SMOKE_COMMAND must contain a command")
    return build, install, smoke


def run(model: str | None = None, goal: str = "Finish Multi-Step Test") -> int:
    source = Path.cwd().resolve()
    responder = GroqResponder(api_key=None, model=model, task="repair")
    orchestrator = SelfImprovementOrchestrator(
        source,
        responder,
        validation_policy=ValidationPolicy(
            commands=(("python", "-m", "pytest", "-q"),),
        ),
    )
    improvement = orchestrator.improve(
        RunResult(status=RunStatus.FAILED, steps=1, error="step budget exhausted"),
        source_paths=("nova_core/bug.py",),
    )

    print(f"SELF_REPAIR_DECISION={improvement.decision.value}")
    print(f"SELF_REPAIR_ACCEPTED={improvement.accepted}")
    if improvement.error:
        print(f"SELF_REPAIR_ERROR={improvement.error!r}")
    if improvement.candidate:
        print(f"SELF_REPAIR_DESCRIPTION={improvement.candidate.description!r}")
        print(f"SELF_REPAIR_PATHS={improvement.candidate.paths!r}")

    if improvement.decision is not ImprovementDecision.PROPOSE or not improvement.accepted:
        print("SELF_REPAIR_PROMOTION=NOT_ATTEMPTED")
        return 1
    assert improvement.candidate is not None
    assert improvement.sandbox is not None

    commands = _promotion_commands(goal)
    print("PROMOTION_VALIDATION_COMMANDS=")
    for index, command in enumerate(commands, start=1):
        print(f"PROMOTION_COMMAND_{index}={command!r}")

    gate = RepairPromotionGate(
        source,
        PromotionPolicy(
            validation_commands=commands,
            timeout_seconds=int(os.environ.get("NOVA_PROMOTION_TIMEOUT_SECONDS", "180")),
            commit_message="promote validated real-device self-repair",
        ),
    )
    result = gate.promote(improvement.candidate, improvement.sandbox)

    print(f"PROMOTION_STATUS={result.status.value}")
    print(f"PROMOTION_BASELINE_REVISION={result.baseline_revision}")
    print(f"PROMOTION_REVISION={result.promoted_revision!r}")
    print(f"PROMOTION_REASON={result.reason!r}")
    for index, record in enumerate(result.validations, start=1):
        print(
            f"PROMOTION_VALIDATION_{index}="
            f"{record.status.value}:return_code={record.return_code}:command={record.command!r}"
        )
        if record.output:
            print(f"PROMOTION_VALIDATION_{index}_OUTPUT={record.output!r}")

    if result.promoted_revision:
        print("SELF_REPAIR_PROMOTION=PASS")
        return 0
    print("SELF_REPAIR_PROMOTION=FAIL")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="Optional Groq repair model override")
    parser.add_argument("--goal", default="Finish Multi-Step Test")
    args = parser.parse_args()
    try:
        return run(args.model, args.goal)
    except (ValueError, OSError) as exc:
        print(f"SELF_REPAIR_PROMOTION_ERROR={exc!r}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
