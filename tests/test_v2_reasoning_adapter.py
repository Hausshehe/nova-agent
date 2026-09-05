import json

import pytest

from nova_core.models import ActionType, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext
from nova_core.reasoning_adapter import LLMReasoner, LegacyReasoningAdapter


class FakeProvider:
    def __init__(self, result): self.result, self.calls = result, []
    def decide(self, goal, observation, history):
        self.calls.append((goal, observation, history)); return self.result


def context():
    return ReasoningContext(goal=Goal("tap the button"), observation=Observation("com.example", "MainActivity", (UiElement(id="button", text="Tap", clickable=True),)))


def test_adapter_translates_click_and_preserves_context():
    provider = FakeProvider({"action_type": "click", "target": {"element_id": "button"}, "reason": "target matches goal"})
    decision = LegacyReasoningAdapter(provider).decide(context())
    assert decision.action.type is ActionType.TAP and decision.action.target_id == "button"
    assert decision.reason == "target matches goal" and provider.calls[0][0] == "tap the button"


def test_adapter_translates_back(): assert LegacyReasoningAdapter(FakeProvider({"action_type": "back"})).decide(context()).action.type is ActionType.BACK


def test_adapter_translates_scroll():
    decision = LegacyReasoningAdapter(FakeProvider({"action_type": "scroll", "target": {"element_id": "button"}})).decide(context())
    assert decision.action.type is ActionType.SCROLL and decision.action.target_id == "button"


@pytest.mark.parametrize("result", [None, [], "click", {"action_type": "unknown"}])
def test_adapter_fails_closed_for_invalid_output(result):
    with pytest.raises(ValueError): LegacyReasoningAdapter(FakeProvider(result)).decide(context())


def test_adapter_rejects_click_without_target_id():
    with pytest.raises(ValueError, match="target.element_id"): LegacyReasoningAdapter(FakeProvider({"action_type": "click", "target": {}})).decide(context())


def test_llm_reasoner_serializes_v2_context_and_validates_live_target():
    received = []
    def responder(prompt):
        received.append(prompt); payload = json.loads(prompt)
        assert payload["goal"] == "tap the button" and payload["observation"]["revision"] == 0
        assert payload["observation"]["elements"][0]["id"] == "button" and payload["observation"]["elements"][0]["clickable"] is True
        assert payload["history"] == [] and "goal_stage_candidates" in payload
        return {"action_type": "tap", "target_id": "button", "reason": "selected the visible button"}
    decision = LLMReasoner(responder).decide(context())
    assert received and decision.action.type is ActionType.TAP and decision.action.target_id == "button"
    assert decision.target_label == "Tap" and decision.reason == "selected the visible button"


def test_llm_reasoner_exposes_generic_goal_stage_candidate():
    received = []
    observation = Observation("pkg", "MainActivity", (
        UiElement(id="start", text="Multi-Step Test", clickable=True),
        UiElement(id="continue", text="Continue Multi-Step", clickable=True),
        UiElement(id="finish", text="Finish Multi-Step", clickable=True),
    ))
    context_value = ReasoningContext(goal=Goal("Finish Multi-Step Test"), observation=observation)
    def responder(prompt):
        received.append(json.loads(prompt)); return {"action_type": "tap", "target_id": "start"}
    decision = LLMReasoner(responder).decide(context_value)
    candidates = received[0]["goal_stage_candidates"]
    assert {item["id"] for item in candidates} == {"start"}
    assert decision.action.target_id == "start"


def test_llm_reasoner_does_not_repeat_completed_goal_stage_candidate():
    observation = Observation("pkg", "MainActivity", (UiElement(id="start", text="Multi-Step Test", clickable=True), UiElement(id="finish", text="Finish Multi-Step", clickable=True)))
    from nova_core.models import Action, Decision, ExecutionResult
    from nova_core.reasoning import ReasoningStep
    history = (ReasoningStep(Decision(Action(ActionType.TAP, "start"), target_label="Multi-Step Test"), ExecutionResult(True, True), observation),)
    received = []
    context_value = ReasoningContext(goal=Goal("Finish Multi-Step Test"), observation=observation, history=history)
    def responder(prompt): received.append(json.loads(prompt)); return {"action_type": "tap", "target_id": "finish"}
    LLMReasoner(responder).decide(context_value)
    assert received[0]["goal_stage_candidates"] == []


def test_llm_reasoner_rejects_stale_or_non_clickable_target():
    with pytest.raises(ValueError, match="not available"): LLMReasoner(lambda prompt: {"action_type": "tap", "target_id": "stale"}).decide(context())
    non_clickable = ReasoningContext(goal=Goal("tap the button"), observation=Observation("com.example", "MainActivity", (UiElement(id="button", text="Tap", clickable=False),)))
    with pytest.raises(ValueError, match="not available"): LLMReasoner(lambda prompt: {"action_type": "tap", "target_id": "button"}).decide(non_clickable)


def test_llm_reasoner_wraps_responder_failure():
    with pytest.raises(RuntimeError, match="reasoning provider failed"): LLMReasoner(lambda prompt: (_ for _ in ()).throw(OSError("connection failed"))).decide(context())


def test_llm_reasoner_rejects_invalid_action_shape():
    with pytest.raises(ValueError, match="not allowed"): LLMReasoner(lambda prompt: {"action_type": "back", "target_id": "button"}).decide(context())
