from __future__ import annotations

import subprocess
from pathlib import Path

from nova_core.improvement.promotion import PromotionPolicy, PromotionStatus, RepairPromotionGate
from nova_core.improvement.repair import RepairCandidate
from nova_core.improvement.sandbox import SandboxResult
from nova_core.improvement.validation import ValidationReport


def _git(repo: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "nova_core").mkdir()
    (repo / "nova_core" / "bug.py").write_text("def is_ready():\n    return False\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", ".")
    subprocess.run(
        ("git", "-c", "user.email=test@example.com", "-c", "user.name=Nova Test", "commit", "-m", "baseline"),
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return repo


def _candidate() -> RepairCandidate:
    return RepairCandidate(
        "make readiness true",
        "--- a/nova_core/bug.py\n+++ b/nova_core/bug.py\n@@ -1,2 +1,2 @@\n def is_ready():\n-    return False\n+    return True\n",
        ("nova_core/bug.py",),
    )


def _accepted() -> SandboxResult:
    return SandboxResult(ValidationReport((), True, "accepted"), "sandbox")


def test_promotion_requires_accepted_sandbox(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    gate = RepairPromotionGate(repo, PromotionPolicy((("python", "-c", "raise SystemExit(0)"),)))
    result = gate.promote(_candidate(), SandboxResult(ValidationReport((), False, "failed"), "sandbox"))
    assert result.status is PromotionStatus.REJECTED
    assert "not passed" in result.reason


def test_device_failure_does_not_touch_live_source(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline = subprocess.run(("git", "rev-parse", "HEAD"), cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    gate = RepairPromotionGate(repo, PromotionPolicy((("python", "-c", "raise SystemExit(3)"),)))
    result = gate.promote(_candidate(), _accepted())
    assert result.status is PromotionStatus.ROLLED_BACK
    assert result.baseline_revision == baseline
    assert result.promoted_revision is None
    assert "return False" in (repo / "nova_core" / "bug.py").read_text(encoding="utf-8")
    assert subprocess.run(("git", "rev-parse", "HEAD"), cwd=repo, check=True, capture_output=True, text=True).stdout.strip() == baseline
    assert subprocess.run(("git", "status", "--porcelain"), cwd=repo, check=True, capture_output=True, text=True).stdout == ""


def test_validation_commands_run_in_order_and_see_candidate(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    commands = (
        (
            "python",
            "-c",
            "from pathlib import Path; assert 'return True' in Path('nova_core/bug.py').read_text(); Path('stage1').write_text('ok')",
        ),
        (
            "python",
            "-c",
            "from pathlib import Path; assert Path('stage1').read_text() == 'ok'; assert 'return False' not in Path('nova_core/bug.py').read_text()",
        ),
    )
    gate = RepairPromotionGate(repo, PromotionPolicy(commands, commit_message="test promotion"))
    result = gate.promote(_candidate(), _accepted())
    assert result.status is PromotionStatus.PROMOTED
    assert [record.status.value for record in result.validations] == ["passed", "passed"]
    assert [record.command for record in result.validations] == list(commands)
    assert "return True" in (repo / "nova_core" / "bug.py").read_text(encoding="utf-8")


def test_validation_stops_after_first_failure(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    marker = "marker"
    commands = (
        ("python", "-c", "raise SystemExit(4)"),
        ("python", "-c", f"from pathlib import Path; Path('{marker}').write_text('should-not-run')"),
    )
    gate = RepairPromotionGate(repo, PromotionPolicy(commands))
    result = gate.promote(_candidate(), _accepted())
    assert result.status is PromotionStatus.ROLLED_BACK
    assert len(result.validations) == 1
    assert result.validations[0].status.value == "failed"
    assert not (repo / marker).exists()
    assert "return False" in (repo / "nova_core" / "bug.py").read_text(encoding="utf-8")


def test_device_gate_sees_candidate_while_live_source_stays_baseline(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    command = (
        "python",
        "-c",
        "from pathlib import Path; "
        "p=Path('nova_core/bug.py'); "
        "assert 'return True' in p.read_text(); "
        "raise SystemExit(0)",
    )
    gate = RepairPromotionGate(repo, PromotionPolicy((command,), commit_message="test promotion"))
    result = gate.promote(_candidate(), _accepted())
    assert result.status is PromotionStatus.PROMOTED
    assert result.device_validation is not None
    assert result.device_validation.status.value == "passed"
    assert "return True" in (repo / "nova_core" / "bug.py").read_text(encoding="utf-8")


def test_successful_device_gate_promotes_and_commits(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline = subprocess.run(("git", "rev-parse", "HEAD"), cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    gate = RepairPromotionGate(
        repo,
        PromotionPolicy((("python", "-c", "raise SystemExit(0)"),), commit_message="test promotion"),
    )
    result = gate.promote(_candidate(), _accepted())
    assert result.status is PromotionStatus.PROMOTED
    assert result.baseline_revision == baseline
    assert result.promoted_revision is not None
    assert result.promoted_revision != baseline
    assert "return True" in (repo / "nova_core" / "bug.py").read_text(encoding="utf-8")
    assert subprocess.run(("git", "status", "--porcelain"), cwd=repo, check=True, capture_output=True, text=True).stdout == ""
