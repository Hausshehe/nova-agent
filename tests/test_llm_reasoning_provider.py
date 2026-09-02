import json

import pytest

from agent.core import ActionType, UIElement, WorldState
from agent.reasoning_context import build_reasoning_context
from agent.reasoning_response import InvalidReasoningResponse
from agent.llm_reasoning_provider import LLMReasoningProvider


def test_llm_provider_serializes_context_and_validates_response():
    button = UIElement("n1", text="Continue", clickable=True)
    context = build_reasoning_context(
        "Tap Continue",
        WorldState(package="nova", elements=(button,)),
        [],
    )
    received = []

    def responder(prompt):
        received.append(prompt)
        assert '"action_type":"click|back|wait"' in prompt
        assert 'Do not use an \'action\' field.' in prompt
        payload = json.loads(prompt.split("Observation and goal:\n", 1)[1])
        assert payload["goal"] == "Tap Continue"
        assert payload["state"]["elements"][0]["id"] == "n1"
        return {
            "action_type": "click",
            "target": {"element_id": "n1"},
            "reason": "selected by model",
        }

    decision = LLMReasoningProvider(responder).decide(context)

    assert received
    assert decision.action.type is ActionType.CLICK
    assert decision.action.target.element_id == "n1"
    assert decision.rationale == "selected by model"


def test_llm_provider_rejects_stale_target_before_execution():
    context = build_reasoning_context(
        "Tap Continue",
        WorldState(
            package="nova",
            elements=(UIElement("n1", text="Continue", clickable=True),),
        ),
        [],
    )

    provider = LLMReasoningProvider(
        lambda prompt: {
            "action_type": "click",
            "target": {"element_id": "stale"},
        }
    )

    with pytest.raises(InvalidReasoningResponse, match="not available"):
        provider.decide(context)


def test_llm_provider_wraps_responder_failure():
    context = build_reasoning_context(
        "Tap Continue",
        WorldState(
            package="nova",
            elements=(UIElement("n1", text="Continue", clickable=True),),
        ),
        [],
    )

    def failing_responder(prompt):
        raise OSError("connection failed")

    with pytest.raises(RuntimeError, match="reasoning provider failed"):
        LLMReasoningProvider(failing_responder).decide(context)
