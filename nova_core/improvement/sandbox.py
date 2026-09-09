"""Isolated workspace for evaluating untrusted repair candidates."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .repair import RepairCandidate
from .validation import ValidationPolicy, ValidationRecord, ValidationReport, ValidationStatus


@dataclass(frozen=True)
class SandboxResult:
    report: ValidationReport
    workspace: str

    @property
    def accepted(self) -> bool:
        return self.report.accepted


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
                    record = ValidationRecord(("git", "apply", "--check"), ValidationStatus.FAILED, patch.returncode, self._output(patch.stdout, patch.stderr))
                    return SandboxResult(ValidationReport((record,), False, "candidate patch failed preflight"), str(workspace))
                applied = subprocess.run(
                    ("git", "apply", str(patch_file)),
                    cwd=workspace, text=True, capture_output=True, timeout=self.policy.timeout_seconds,
                )
                if applied.returncode != 0:
                    record = ValidationRecord(("git", "apply"), ValidationStatus.FAILED, applied.returncode, self._output(applied.stdout, applied.stderr))
                    return SandboxResult(ValidationReport((record,), False, "candidate patch could not be applied"), str(workspace))
                records: list[ValidationRecord] = []
                for command in self.policy.commands:
                    try:
                        result = subprocess.run(command, cwd=workspace, text=True, capture_output=True, timeout=self.policy.timeout_seconds)
                    except subprocess.TimeoutExpired as exc:
                        output = self._output(exc.stdout or "", exc.stderr or "")
                        records.append(ValidationRecord(command, ValidationStatus.TIMED_OUT, -1, output))
                        return SandboxResult(ValidationReport(tuple(records), False, "validation timed out"), str(workspace))
                    status = ValidationStatus.PASSED if result.returncode == 0 else ValidationStatus.FAILED
                    records.append(ValidationRecord(command, status, result.returncode, self._output(result.stdout, result.stderr)))
                    if status is ValidationStatus.FAILED:
                        return SandboxResult(ValidationReport(tuple(records), False, "a required validation failed"), str(workspace))
                return SandboxResult(ValidationReport(tuple(records), True, "all required validations passed"), str(workspace))
            except subprocess.TimeoutExpired:
                return SandboxResult(ValidationReport((), False, "sandbox operation timed out"), str(workspace))

    def _output(self, stdout: str, stderr: str) -> str:
        return (stdout + stderr)[-self.policy.max_output_chars:]
