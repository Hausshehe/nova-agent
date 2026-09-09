"""Controlled promotion gate for validated Nova self-repair candidates.

Candidates are validated from an isolated git worktree before the live checkout
is changed. Only a candidate that passes every trusted validation command is
applied to the live checkout and committed. The repair model never controls
commands.
"""

from __future__ import annotations

import shlex
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
    """Fixed validation commands and resource bounds.

    Commands are supplied by trusted Nova configuration rather than by the
    repair model. Each command runs in order inside the disposable candidate
    worktree. A non-zero exit or timeout stops the gate immediately.

    Trusted commands may use ``{worktree}`` and ``{candidate_apk}`` placeholders.
    They are rendered by the gate from its own paths, never from model output.
    Root should be used only for operations that actually require Android
    privileges, such as installing a candidate APK.
    """

    validation_commands: tuple[tuple[str, ...], ...]
    timeout_seconds: int = 120
    max_output_chars: int = 12_000
    commit_message: str = "promote validated self-repair"

    def __post_init__(self) -> None:
        if not self.validation_commands:
            raise ValueError("at least one validation command is required")
        for command in self.validation_commands:
            if not command or any(not part.strip() for part in command):
                raise ValueError("validation commands must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("validation timeout must be positive")
        if self.max_output_chars <= 0:
            raise ValueError("validation output limit must be positive")
        if not self.commit_message.strip():
            raise ValueError("promotion commit message must not be empty")


@dataclass(frozen=True)
class PromotionResult:
    status: PromotionStatus
    baseline_revision: str
    promoted_revision: str | None = None
    validations: tuple[ValidationRecord, ...] = ()
    reason: str = ""

    @property
    def device_validation(self) -> ValidationRecord | None:
        """Compatibility accessor for the first promotion validation."""
        return self.validations[0] if self.validations else None


class RepairPromotionGate:
    """Promote an already sandbox-accepted candidate with isolated validation."""

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

    def _render_command(self, command: tuple[str, ...], worktree: Path) -> tuple[str, ...]:
        """Render only trusted path placeholders into a trusted command."""
        candidate_apk = worktree / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        replacements = {
            "{worktree}": shlex.quote(str(worktree)),
            "{candidate_apk}": shlex.quote(str(candidate_apk)),
        }
        return tuple(
            part.replace("{worktree}", replacements["{worktree}"])
            .replace("{candidate_apk}", replacements["{candidate_apk}"])
            for part in command
        )

    def _run_root_command(self, rendered: tuple[str, ...], worktree: Path) -> tuple[int, str]:
        """Enter an interactive root shell, run the trusted command, then exit.

        The trusted install command is currently represented as ``su -c CMD``.
        We deliberately turn that into an interactive ``su`` shell so Magisk
        can present its normal authorization UI and the user can see the
        install operation live. Only the fixed trusted CMD is sent to root,
        followed by ``exit``. The repair model never supplies this command.
        """
        if len(rendered) != 3 or rendered[0] != "su" or rendered[1] != "-c":
            raise ValueError("interactive root validation requires trusted 'su -c CMD' command")

        print("PROMOTION_ROOT_ENTER=starting interactive root shell", flush=True)
        process = subprocess.Popen(
            ("su",),
            cwd=worktree,
            stdin=subprocess.PIPE,
            text=True,
        )
        try:
            assert process.stdin is not None
            process.stdin.write(rendered[2] + "\n")
            process.stdin.write("exit\n")
            process.stdin.flush()
            process.stdin.close()
            return_code = process.wait(timeout=self.policy.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
        finally:
            print(f"PROMOTION_ROOT_EXIT=return_code={process.returncode}", flush=True)

        return return_code, "interactive root command output was attached to the terminal"

    def _run_validation_commands(self, worktree: Path) -> tuple[ValidationRecord, ...]:
        records: list[ValidationRecord] = []
        for index, command in enumerate(self.policy.validation_commands, start=1):
            rendered = self._render_command(command, worktree)
            print(f"PROMOTION_STAGE_{index}_START={rendered!r}", flush=True)
            try:
                if rendered and rendered[0] == "su":
                    completed_return_code, output = self._run_root_command(rendered, worktree)
                else:
                    completed = subprocess.run(
                        rendered,
                        cwd=worktree,
                        text=True,
                        capture_output=True,
                        timeout=self.policy.timeout_seconds,
                        check=False,
                    )
                    completed_return_code = completed.returncode
                    output = self._output(completed.stdout, completed.stderr)
            except subprocess.TimeoutExpired as exc:
                output = self._output(getattr(exc, "stdout", "") or "", getattr(exc, "stderr", "") or "")
                record = ValidationRecord(rendered, ValidationStatus.TIMED_OUT, -1, output)
                records.append(record)
                print(f"PROMOTION_STAGE_{index}_END=timed_out", flush=True)
                break

            record = ValidationRecord(
                rendered,
                ValidationStatus.PASSED if completed_return_code == 0 else ValidationStatus.FAILED,
                completed_return_code,
                output,
            )
            records.append(record)
            print(
                f"PROMOTION_STAGE_{index}_END={record.status.value}:return_code={record.return_code}",
                flush=True,
            )
            if record.status is not ValidationStatus.PASSED:
                break
        return tuple(records)

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

            validations = self._run_validation_commands(worktree)
            if len(validations) != len(self.policy.validation_commands) or any(
                record.status is not ValidationStatus.PASSED for record in validations
            ):
                status = PromotionStatus.ROLLED_BACK
                last = validations[-1] if validations else None
                if last and last.status is ValidationStatus.TIMED_OUT:
                    reason = "promotion validation timed out; live source was not changed"
                else:
                    reason = "promotion validation failed; live source was not changed"
                return PromotionResult(status, baseline, validations=validations, reason=reason)

            if self._revision() != baseline or not self._clean():
                return PromotionResult(
                    PromotionStatus.REJECTED,
                    baseline,
                    validations=validations,
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
                        validations=validations,
                        reason="candidate could not be applied after validation",
                    )

                staged = self._git("add", "--", *candidate.paths)
                if staged.returncode != 0:
                    self._rollback(baseline)
                    return PromotionResult(
                        PromotionStatus.ROLLED_BACK,
                        baseline,
                        validations=validations,
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
                        validations=validations,
                        reason="could not commit promotion; baseline restored",
                    )

                return PromotionResult(
                    PromotionStatus.PROMOTED,
                    baseline,
                    promoted_revision=self._revision(),
                    validations=validations,
                    reason="all promotion validations passed and candidate was promoted",
                )
            finally:
                patch_file.unlink(missing_ok=True)
        finally:
            if worktree is not None:
                self._remove_worktree(worktree)
