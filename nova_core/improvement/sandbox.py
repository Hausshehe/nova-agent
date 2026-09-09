"""Isolated workspace for evaluating untrusted repair candidates."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .repair import RepairCandidate


@dataclass(frozen=True)
class SandboxResult:
    accepted: bool
    return_code: int
    stdout: str
    stderr: str
    workspace: str


class RepairSandbox:
    """Evaluate a candidate in a temporary copy; never mutate the source tree."""

    def __init__(self, source_root: str | Path, timeout_seconds: int = 60) -> None:
        self.source_root = Path(source_root).resolve()
        self.timeout_seconds = timeout_seconds

    def validate_candidate(self, candidate: RepairCandidate) -> None:
        candidate.validate()
        if not candidate.patch.lstrip().startswith(("diff --git ", "--- ")):
            raise ValueError("repair candidate must be a unified diff")

    def evaluate(self, candidate: RepairCandidate, command: tuple[str, ...] = ("python", "-m", "pytest", "-q")) -> SandboxResult:
        self.validate_candidate(candidate)
        with tempfile.TemporaryDirectory(prefix="nova-repair-") as tmp:
            workspace = Path(tmp) / "repo"
            shutil.copytree(self.source_root, workspace, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
            patch_file = workspace / ".nova-repair.patch"
            patch_file.write_text(candidate.patch, encoding="utf-8")
            try:
                patch = subprocess.run(
                    ("git", "apply", "--check", str(patch_file)),
                    cwd=workspace, text=True, capture_output=True, timeout=self.timeout_seconds,
                )
                if patch.returncode != 0:
                    return SandboxResult(False, patch.returncode, patch.stdout, patch.stderr, str(workspace))
                applied = subprocess.run(
                    ("git", "apply", str(patch_file)),
                    cwd=workspace, text=True, capture_output=True, timeout=self.timeout_seconds,
                )
                if applied.returncode != 0:
                    return SandboxResult(False, applied.returncode, applied.stdout, applied.stderr, str(workspace))
                tests = subprocess.run(command, cwd=workspace, text=True, capture_output=True, timeout=self.timeout_seconds)
                return SandboxResult(tests.returncode == 0, tests.returncode, tests.stdout, tests.stderr, str(workspace))
            except subprocess.TimeoutExpired as exc:
                return SandboxResult(False, -1, exc.stdout or "", exc.stderr or "timeout", str(workspace))
