import json

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext, ReasoningStep
from nova_core.reasoning_adapter import LLMReasoner, _reasoning_payload
from nova_core.uncertainty import UncertaintyAssessment


def _observation() -> Observation:
    return Observation(
        package="com.example",
        activity="MainActivity",
        revision=2,
        elements=(
            UiElement(id="retry", text="Retry", clickable=True),
            UiElement(id="continue", text="Continue", clickable=True),
        ),
    )


def _context(uncertainty: UncertaintyAssessment, history=()) -> ReasoningContext:
    return ReasoningContext(
        goal=Goal("Finish the task"),
        observation=_observation(),
        history=tuple(history),
        uncertainty=uncertainty,
    )


def test_high_uncertainty_changes_concrete_action_guidance():
    payload = _reasoning_payload(_context(UncertaintyAssessment(
        level="high",
        basis="accepted action produced no observable change",
        unknowns=("whether retry advanced the goal",),
    )))

    assert payload["uncertainty"]["mode"] == "reassess"
    assert "resolves an unknown" in payload["uncertainty"]["guidance"]
    assert "fresh observable evidence" in payload["uncertainty"]["guidance"]
    assert "current observation" in " ".join(payload["rules"])


def test_medium_uncertainty_requires_verifiable_action_effect():
    payload = _reasoning_payload(_context(UncertaintyAssessment(
        level="medium",
        basis="action changed the UI",
        unknowns=("whether the change advances the goal",),
    )))

    assert payload["uncertainty"]["mode"] == "progress_check"
    assert "verified from a fresh observation" in payload["uncertainty"]["guidance"]


def test_low_uncertainty_does_not_force_unnecessary_recovery():
    payload = _reasoning_payload(_context(UncertaintyAssessment(
        level="low",
        basis="goal completion verified",
    )))

    assert payload["uncertainty"]["mode"] == "execute"
    assert "unnecessary recovery" in " ".join(payload["rules"])


def test_high_uncertainty_with_stalled_history_exposes_alternative_path():
    stalled = ReasoningStep(
        decision=Decision(Action(ActionType.TAP, target_id="retry"), "retry"),
        execution=ExecutionResult(accepted=True, changed=False),
        post_observation=_observation(),
    )
    payload = _reasoning_payload(_context(UncertaintyAssessment(
        level="high",
        basis="accepted action produced no observable change",
        unknowns=("whether retry advanced the goal",),
    ), history=(stalled,)))

    assert payload["recovery"]["active"] is True
    assert payload["recovery"]["available_alternatives"] == [
        {"action": "tap", "target": "continue", "label": "Continue"},
    ]


def test_action_reasoner_still_accepts_only_current_observation_targets():
    prompts = []

    def responder(prompt: str):
        prompts.append(json.loads(prompt))
        return {"action_type": "tap", "target_id": "continue", "reason": "current evidence supports progress"}

    reasoner = LLMReasoner(responder)
    decision = reasoner.decide(_context(UncertaintyAssessment(
        level="high",
        basis="stalled after prior action",
        unknowns=("whether retry advanced the goal",),
    )))

    assert decision.action == Action(ActionType.TAP, target_id="continue")
    assert decision.target_label == "Continue"
    assert prompts[0]["uncertainty"]["mode"] == "reassess"
