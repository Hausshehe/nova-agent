"""Isolated workspace for evaluating untrusted repair candidates."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .repair import RepairCandidate
from .validation import ValidationPolicy


@dataclass(frozen=True)
class SandboxResult:
    accepted: bool
    return_code: int
    stdout: str
    stderr: str
    workspace: str


class RepairSandbox:
    """Evaluate a candidate in a temporary copy; never mutate the source tree."""

    def __init__(self, source_root: str | Path, policy: ValidationPolicy | None = None) -> None:
        self.source_root = Path(source_root).resolve()
        self.policy = policy or ValidationPolicy()

    def validate_candidate(self, candidate: RepairCandidate) -> None:
        candidate.validate()
        if not candidate.patch.lstrip().startswith(("diff --git ", "--- ")):
            raise ValueError("repair candidate must be a unified diff")

    def evaluate(self, candidate: RepairCandidate) -> SandboxResult:
        self.validate_candidate(candidate)
        with tempfile.TemporaryDirectory(prefix="nova-repair-") as tmp:
            workspace = Path(tmp) / "repo"
            shutil.copytree(self.source_root, workspace, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
            patch_file = workspace / ".nova-repair.patch"
            patch_file.write_text(candidate.patch, encoding="utf-8")
            try:
                patch = subprocess.run(
                    ("git", "apply", "--check", str(patch_file)),
                    cwd=workspace, text=True, capture_output=True, timeout=self.policy.timeout_seconds,
                )
                if patch.returncode != 0:
                    return SandboxResult(False, patch.returncode, patch.stdout, patch.stderr, str(workspace))
                applied = subprocess.run(
                    ("git", "apply", str(patch_file)),
                    cwd=workspace, text=True, capture_output=True, timeout=self.policy.timeout_seconds,
                )
                if applied.returncode != 0:
                    return SandboxResult(False, applied.returncode, applied.stdout, applied.stderr, str(workspace))
                outputs: list[str] = []
                for command in self.policy.commands:
                    tests = subprocess.run(
                        command, cwd=workspace, text=True, capture_output=True,
                        timeout=self.policy.timeout_seconds,
                    )
                    combined = (tests.stdout + tests.stderr)[-self.policy.max_output_chars:]
                    outputs.append(f"$ {' '.join(command)}\n{combined}")
                    if tests.returncode != 0:
                        return SandboxResult(False, tests.returncode, "\n".join(outputs), "validation failed", str(workspace))
                return SandboxResult(True, 0, "\n".join(outputs), "", str(workspace))
            except subprocess.TimeoutExpired:
                return SandboxResult(False, -1, "", "validation timed out", str(workspace))
