from nova_core.improvement.orchestrator import SelfImprovementOrchestrator
from nova_core.improvement.policy import ImprovementDecision, ImprovementPolicy
from nova_core.improvement.validation import ValidationPolicy
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, RunResult, RunStatus, Observation, UiElement
from nova_core.reasoning import ReasoningStep


def _failed_result() -> RunResult:
    return RunResult(status=RunStatus.FAILED, steps=1, error="step budget exhausted")


def _history() -> tuple[ReasoningStep, ...]:
    decision = Decision(Action(type=ActionType.TAP, target_id="continue"), reason="advance")
    execution = ExecutionResult(accepted=True, changed=True)
    return (ReasoningStep(decision=decision, execution=execution),)


def test_orchestrator_diagnoses_and_sends_device_context_to_proposer(tmp_path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    import subprocess
    subprocess.run(("git", "init"), cwd=source, check=True, capture_output=True)
    (source / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(("git", "add", "value.py"), cwd=source, check=True, capture_output=True)
    subprocess.run(("git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "baseline"), cwd=source, check=True, capture_output=True)

    observation = Observation(
        package="com.example.nova",
        activity="MainActivity",
        revision=9,
        elements=(UiElement(id="continue", text="Continue", clickable=True),),
    )
    prompts: list[str] = []

    def responder(prompt: str):
        prompts.append(prompt)
        return {
            "description": "repair value",
            "patch": "--- a/value.py\n+++ b/value.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
            "paths": ["value.py"],
        }

    result = SelfImprovementOrchestrator(
        source,
        responder,
        validation_policy=ValidationPolicy(commands=(("python", "-m", "py_compile", "value.py"),)),
    ).improve(_failed_result(), _history(), observation)

    assert result.decision is ImprovementDecision.PROPOSE
    assert result.diagnosis is not None
    assert result.candidate is not None
    assert result.sandbox is not None
    assert result.sandbox.accepted is True
    assert result.source_revision
    assert "com.example.nova" in prompts[0]
    assert "device.revision=9" in prompts[0]
    assert (source / "value.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_orchestrator_does_not_propose_after_policy_budget(tmp_path) -> None:
    source = tmp_path / "repo"
    source.mkdir()
    called = False

    def responder(prompt: str):
        nonlocal called
        called = True
        raise AssertionError("responder must not be called")

    result = SelfImprovementOrchestrator(
        source,
        responder,
        policy=ImprovementPolicy(max_proposals_per_run=1),
    ).improve(_failed_result(), proposals_used=1)

    assert result.decision is ImprovementDecision.NO_ACTION
    assert called is False
