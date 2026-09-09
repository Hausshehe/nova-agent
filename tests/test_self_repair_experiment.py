"""End-to-end controlled experiment for Nova's isolated self-repair path."""

from pathlib import Path

from nova_core.improvement.orchestrator import SelfImprovementOrchestrator
from nova_core.improvement.policy import ImprovementDecision
from nova_core.improvement.validation import ValidationPolicy
from nova_core.models import RunResult, RunStatus


def test_controlled_bug_is_repaired_without_mutating_baseline(tmp_path: Path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    (source / "nova_core").mkdir()
    target = source / "nova_core" / "bug.py"
    target.write_text("def is_ready():\n    return False\n", encoding="utf-8")

    import subprocess
    subprocess.run(("git", "init"), cwd=source, check=True, capture_output=True)
    subprocess.run(("git", "add", "."), cwd=source, check=True, capture_output=True)
    subprocess.run(("git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "baseline"), cwd=source, check=True, capture_output=True)

    def responder(prompt: str):
        assert "source.file=nova_core/bug.py" in prompt
        return {
            "description": "make the readiness predicate return true",
            "patch": "--- a/nova_core/bug.py\n+++ b/nova_core/bug.py\n@@ -1,2 +1,2 @@\n def is_ready():\n-    return False\n+    return True\n",
            "paths": ["nova_core/bug.py"],
        }

    result = SelfImprovementOrchestrator(
        source,
        responder,
        validation_policy=ValidationPolicy(
            commands=(("python", "-m", "py_compile", "nova_core/bug.py"),),
        ),
    ).improve(
        RunResult(status=RunStatus.FAILED, steps=1, error="step budget exhausted"),
        source_paths=("nova_core/bug.py",),
    )

    assert result.decision is ImprovementDecision.PROPOSE
    assert result.accepted is True
    assert result.source_revision
    assert target.read_text(encoding="utf-8") == "def is_ready():\n    return False\n"
