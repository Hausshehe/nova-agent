from pathlib import Path

import pytest

from nova_core.improvement.repair import RepairCandidate
from nova_core.improvement.sandbox import RepairSandbox
from nova_core.improvement.validation import ValidationPolicy, ValidationStatus


def test_candidate_rejects_unsafe_paths() -> None:
    candidate = RepairCandidate("bad", "--- a/x.py\n+++ b/x.py\n", ("../secret.py",))
    with pytest.raises(ValueError):
        candidate.validate()


def test_sandbox_does_not_modify_source(tmp_path: Path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    (source / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    candidate = RepairCandidate(
        "change value",
        "--- a/value.py\n+++ b/value.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
        ("value.py",),
    )
    result = RepairSandbox(source).evaluate(candidate)
    assert result.accepted is True
    assert result.report.reason == "all required validations passed"
    assert result.report.records[0].status is ValidationStatus.PASSED
    assert (source / "value.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_sandbox_rejects_bad_patch(tmp_path: Path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    candidate = RepairCandidate("bad", "not a patch", ())
    with pytest.raises(ValueError):
        RepairSandbox(source).evaluate(candidate)


def test_failed_required_validation_is_recorded(tmp_path: Path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    (source / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    candidate = RepairCandidate(
        "change value",
        "--- a/value.py\n+++ b/value.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
        ("value.py",),
    )
    policy = ValidationPolicy(commands=(("python", "-c", "raise SystemExit(3)"),))
    result = RepairSandbox(source, policy).evaluate(candidate)
    assert result.accepted is False
    assert result.report.reason == "a required validation failed"
    assert result.report.records[0].return_code == 3
    assert result.report.records[0].status is ValidationStatus.FAILED
