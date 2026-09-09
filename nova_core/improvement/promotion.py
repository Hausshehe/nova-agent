"""Controlled promotion gate for validated Nova self-repair candidates.

A candidate is promoted only after repository validation has already accepted it
and a policy-controlled real-device validation command succeeds. Promotion is
transactional: a known-good baseline is captured first and restored on failure.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .repair import RepairCandidate
from .sandbox import SandboxResult
from .validation import ValidationRecord, ValidationStatus


class PromotionStatus(str, Enum):
    REJECTED = "rejected"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass(frozen=True)
class PromotionPolicy:
    """Fixed device-gate command and resource bounds.

    The command is deliberately supplied by trusted Nova configuration rather
    than by the repair model. The repair model has no command authority.
    """

    device_command: tuple[str, ...]
    timeout_seconds: int = 120
    max_output_chars: int = 12_000
    commit_message: str = "promote validated self-repair"

    def __post_init__(self) -> None:
        if not self.device_command or any(not part.strip() for part in self.device_command):
            raise ValueError("device validation command must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("device validation timeout must be positive")
        if self.max_output_chars <= 0:
            raise ValueError("device validation output limit must be positive")
        if not self.commit_message.strip():
            raise ValueError("promotion commit message must not be empty")


@dataclass(frozen=True)
class PromotionResult:
    status: PromotionStatus
    baseline_revision: str
    promoted_revision: str | None = None
    device_validation: ValidationRecord | None = None
    reason: str = ""


class RepairPromotionGate:
    """Promote an already sandbox-accepted candidate with rollback protection."""

    def __init__(self, source_root: str | Path, policy: PromotionPolicy) -> None:
        self.source_root = Path(source_root).resolve()
        self.policy = policy

    def _git(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *args),
            cwd=self.source_root,
            text=True,
            capture_output=True,
            timeout=self.policy.timeout_seconds,
            check=check,
        )

    def _revision(self) -> str:
        result = self._git("rev-parse", "HEAD")
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("could not determine source revision")
        return result.stdout.strip()

    def _clean(self) -> bool:
        result = self._git("status", "--porcelain")
        return result.returncode == 0 and not result.stdout.strip()

    def _output(self, stdout: str, stderr: str) -> str:
        return (stdout + stderr)[-self.policy.max_output_chars :]

    def _rollback(self, baseline: str) -> None:
        result = self._git("reset", "--hard", baseline)
        if result.returncode != 0:
            raise RuntimeError(f"rollback failed: {self._output(result.stdout, result.stderr)}")

    def promote(
        self,
        candidate: RepairCandidate,
        sandbox: SandboxResult,
    ) -> PromotionResult:
        """Apply, device-test, and commit a trusted candidate or restore baseline."""
        baseline = self._revision()

        if not sandbox.accepted:
            return PromotionResult(
                PromotionStatus.REJECTED,
                baseline,
                reason="candidate has not passed sandbox validation",
            )

        candidate.validate()

        if not self._clean():
            return PromotionResult(
                PromotionStatus.REJECTED,
                baseline,
                reason="source tree must be clean before promotion",
            )

        patch_file = self.source_root / ".nova-promotion.patch"
        try:
            patch_file.write_text(candidate.patch, encoding="utf-8")
            preflight = self._git("apply", "--check", str(patch_file))
            if preflight.returncode != 0:
                return PromotionResult(
                    PromotionStatus.REJECTED,
                    baseline,
                    reason="candidate failed promotion preflight",
                )

            applied = self._git("apply", str(patch_file))
            if applied.returncode != 0:
                return PromotionResult(
                    PromotionStatus.REJECTED,
                    baseline,
                    reason="candidate could not be applied for promotion",
                )

            try:
                device = subprocess.run(
                    self.policy.device_command,
                    cwd=self.source_root,
                    text=True,
                    capture_output=True,
                    timeout=self.policy.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                record = ValidationRecord(
                    self.policy.device_command,
                    ValidationStatus.TIMED_OUT,
                    -1,
                    self._output(exc.stdout or "", exc.stderr or ""),
                )
                self._rollback(baseline)
                return PromotionResult(
                    PromotionStatus.ROLLED_BACK,
                    baseline,
                    device_validation=record,
                    reason="device validation timed out; baseline restored",
                )

            record = ValidationRecord(
                self.policy.device_command,
                ValidationStatus.PASSED if device.returncode == 0 else ValidationStatus.FAILED,
                device.returncode,
                self._output(device.stdout, device.stderr),
            )

            if device.returncode != 0:
                self._rollback(baseline)
                return PromotionResult(
                    PromotionStatus.ROLLED_BACK,
                    baseline,
                    device_validation=record,
                    reason="device validation failed; baseline restored",
                )

            committed = self._git("add", "--", *candidate.paths)
            if committed.returncode != 0:
                self._rollback(baseline)
                return PromotionResult(
                    PromotionStatus.ROLLED_BACK,
                    baseline,
                    device_validation=record,
                    reason="could not stage promoted files; baseline restored",
                )

            committed = self._git("commit", "-m", self.policy.commit_message)
            if committed.returncode != 0:
                self._rollback(baseline)
                return PromotionResult(
                    PromotionStatus.ROLLED_BACK,
                    baseline,
                    device_validation=record,
                    reason="could not commit promotion; baseline restored",
                )

            return PromotionResult(
                PromotionStatus.PROMOTED,
                baseline,
                promoted_revision=self._revision(),
                device_validation=record,
                reason="device validation passed and candidate was promoted",
            )
        finally:
            patch_file.unlink(missing_ok=True)
