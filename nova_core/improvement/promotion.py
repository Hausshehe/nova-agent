"""Controlled promotion gate for validated Nova self-repair candidates.

Candidates are validated from an isolated git worktree before the live checkout
is changed. Only a candidate that passes the trusted device gate is applied to
the live checkout and committed. The repair model never controls commands.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
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

    The command is supplied by trusted Nova configuration rather than by the
    repair model. The repair model has no command authority.
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
    """Promote an already sandbox-accepted candidate with isolated device testing."""

    def __init__(self, source_root: str | Path, policy: PromotionPolicy) -> None:
        self.source_root = Path(source_root).resolve()
        self.policy = policy

    def _git(
        self,
        *args: str,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *args),
            cwd=cwd or self.source_root,
            text=True,
            capture_output=True,
            timeout=self.policy.timeout_seconds,
            check=False,
        )

    def _revision(self, cwd: Path | None = None) -> str:
        result = self._git("rev-parse", "HEAD", cwd=cwd)
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("could not determine source revision")
        return result.stdout.strip()

    def _clean(self) -> bool:
        result = self._git("status", "--porcelain")
        return result.returncode == 0 and not result.stdout.strip()

    def _output(self, stdout: str | bytes, stderr: str | bytes) -> str:
        def text(value: str | bytes) -> str:
            return value.decode(errors="replace") if isinstance(value, bytes) else value

        return (text(stdout) + text(stderr))[-self.policy.max_output_chars :]

    def _rollback(self, baseline: str) -> None:
        result = self._git("reset", "--hard", baseline)
        if result.returncode != 0:
            raise RuntimeError(f"rollback failed: {self._output(result.stdout, result.stderr)}")

    def _create_worktree(self, baseline: str) -> Path:
        parent = Path(tempfile.mkdtemp(prefix="nova-promotion-"))
        worktree = parent / "candidate"
        result = self._git("worktree", "add", "--detach", str(worktree), baseline)
        if result.returncode != 0:
            shutil.rmtree(parent, ignore_errors=True)
            raise RuntimeError(f"could not create promotion worktree: {self._output(result.stdout, result.stderr)}")
        return worktree

    def _remove_worktree(self, worktree: Path) -> None:
        self._git("worktree", "remove", "--force", str(worktree))
        shutil.rmtree(worktree.parent, ignore_errors=True)

    def _apply_patch(self, root: Path, candidate: RepairCandidate) -> bool:
        patch_file = root / ".nova-promotion.patch"
        try:
            patch_file.write_text(candidate.patch, encoding="utf-8")
            preflight = self._git("apply", "--check", str(patch_file), cwd=root)
            if preflight.returncode != 0:
                return False
            applied = self._git("apply", str(patch_file), cwd=root)
            return applied.returncode == 0
        finally:
            patch_file.unlink(missing_ok=True)

    def promote(
        self,
        candidate: RepairCandidate,
        sandbox: SandboxResult,
    ) -> PromotionResult:
        """Test the candidate outside the live checkout, then promote atomically."""
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

        worktree: Path | None = None
        try:
            worktree = self._create_worktree(baseline)
            if not self._apply_patch(worktree, candidate):
                return PromotionResult(
                    PromotionStatus.REJECTED,
                    baseline,
                    reason="candidate failed promotion preflight in isolated worktree",
                )

            try:
                device = subprocess.run(
                    self.policy.device_command,
                    cwd=worktree,
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
                return PromotionResult(
                    PromotionStatus.ROLLED_BACK,
                    baseline,
                    device_validation=record,
                    reason="device validation timed out; live source was not changed",
                )

            record = ValidationRecord(
                self.policy.device_command,
                ValidationStatus.PASSED if device.returncode == 0 else ValidationStatus.FAILED,
                device.returncode,
                self._output(device.stdout, device.stderr),
            )

            if device.returncode != 0:
                return PromotionResult(
                    PromotionStatus.ROLLED_BACK,
                    baseline,
                    device_validation=record,
                    reason="device validation failed; live source was not changed",
                )

            # The device gate can take time. Refuse to overwrite work committed
            # by another process while this candidate was being validated.
            if self._revision() != baseline or not self._clean():
                return PromotionResult(
                    PromotionStatus.REJECTED,
                    baseline,
                    device_validation=record,
                    reason="live source changed during promotion validation",
                )

            patch_file = self.source_root / ".nova-promotion.patch"
            try:
                patch_file.write_text(candidate.patch, encoding="utf-8")
                applied = self._git("apply", str(patch_file))
                if applied.returncode != 0:
                    return PromotionResult(
                        PromotionStatus.ROLLED_BACK,
                        baseline,
                        device_validation=record,
                        reason="candidate could not be applied after device validation",
                    )

                staged = self._git("add", "--", *candidate.paths)
                if staged.returncode != 0:
                    self._rollback(baseline)
                    return PromotionResult(
                        PromotionStatus.ROLLED_BACK,
                        baseline,
                        device_validation=record,
                        reason="could not stage promoted files; baseline restored",
                    )

                committed = self._git(
                    "-c", "user.name=Nova Agent",
                    "-c", "user.email=nova-agent@localhost",
                    "commit", "-m", self.policy.commit_message,
                )
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
        finally:
            if worktree is not None:
                self._remove_worktree(worktree)
