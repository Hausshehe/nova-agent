"""Controlled real-Groq smoke for Nova's isolated self-repair boundary.

The experiment creates a disposable git repository containing one deliberately
broken Python file and a regression test that exposes the bug. Groq may propose
a patch, but the candidate is validated and applied only inside RepairSandbox.
The real nova-agent checkout is never used as the repair target and is never
mutated.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from agent.groq_responder import GroqResponder
from nova_core.improvement.orchestrator import SelfImprovementOrchestrator
from nova_core.improvement.policy import ImprovementDecision
from nova_core.improvement.validation import ValidationPolicy
from nova_core.models import RunResult, RunStatus


def _git(repo: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=repo, check=True, capture_output=True, text=True)


def run(model: str | None = None) -> int:
    with tempfile.TemporaryDirectory(prefix="nova-self-repair-") as directory:
        source = Path(directory)
        package = source / "nova_core"
        tests = source / "tests"
        package.mkdir()
        tests.mkdir()

        target = package / "bug.py"
        baseline = "def is_ready():\n    return False\n"
        target.write_text(baseline, encoding="utf-8")
        (tests / "test_bug.py").write_text(
            "from nova_core.bug import is_ready\n\n\ndef test_readiness():\n    assert is_ready() is True\n",
            encoding="utf-8",
        )

        _git(source, "init")
        _git(source, "add", ".")
        subprocess.run(
            (
                "git",
                "-c",
                "user.email=test@example.com",
                "-c",
                "user.name=Nova Smoke",
                "commit",
                "-m",
                "baseline",
            ),
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        )
        baseline_revision = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=source, check=True, capture_output=True, text=True
        ).stdout.strip()

        responder = GroqResponder(api_key=None, model=model, task="repair")
        orchestrator = SelfImprovementOrchestrator(
            source,
            responder,
            validation_policy=ValidationPolicy(
                commands=(("python", "-m", "pytest", "-q", "tests/test_bug.py"),),
            ),
        )
        result = orchestrator.improve(
            RunResult(status=RunStatus.FAILED, steps=1, error="step budget exhausted"),
            source_paths=("nova_core/bug.py",),
        )

        print(f"SELF_REPAIR_DECISION={result.decision.value}")
        print(f"SELF_REPAIR_CATEGORY={result.diagnosis.category.value if result.diagnosis else None}")
        print(f"SELF_REPAIR_ACCEPTED={result.accepted}")
        print(f"SELF_REPAIR_BASELINE_REVISION={baseline_revision}")
        if result.error:
            print(f"SELF_REPAIR_ERROR={result.error!r}")
        if result.candidate:
            print(f"SELF_REPAIR_DESCRIPTION={result.candidate.description!r}")
            print(f"SELF_REPAIR_PATHS={result.candidate.paths!r}")
            print("SELF_REPAIR_PATCH_START")
            print(result.candidate.patch, end="")
            print("SELF_REPAIR_PATCH_END")
        if result.sandbox:
            print(f"SELF_REPAIR_VALIDATION_REASON={result.sandbox.report.reason!r}")
            for record in result.sandbox.report.records:
                print(
                    "SELF_REPAIR_VALIDATION="
                    f"{record.status.value}:return_code={record.return_code}:command={record.command!r}"
                )

        live_content = target.read_text(encoding="utf-8")
        print(f"SELF_REPAIR_BASELINE_UNCHANGED={live_content == baseline}")

        if result.decision is not ImprovementDecision.PROPOSE:
            return 1
        if not result.accepted:
            return 1
        if live_content != baseline:
            return 1
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="Optional Groq model override")
    args = parser.parse_args()
    return run(args.model)


if __name__ == "__main__":
    raise SystemExit(main())
