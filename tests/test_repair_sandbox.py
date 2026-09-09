from pathlib import Path

import pytest

from nova_core.improvement.repair import RepairCandidate
from nova_core.improvement.sandbox import RepairSandbox


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
    result = RepairSandbox(source).evaluate(candidate, ("python", "-c", "import value; assert value.VALUE == 2"))
    assert result.accepted is True
    assert (source / "value.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_sandbox_rejects_bad_patch(tmp_path: Path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    candidate = RepairCandidate("bad", "not a patch", ())
    with pytest.raises(ValueError):
        RepairSandbox(source).evaluate(candidate)
