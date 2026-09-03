import pytest

from agent.core import ActionType, UIElement, WorldState
from agent.reasoning_context import build_reasoning_context
from agent.reasoning_response import InvalidReasoningResponse
from agent.structured_reasoning_provider import StructuredReasoningProvider


def test_structured_provider_passes_payload_to_responder_and_returns_decision():
    button = UIElement("n1", text="Continue", clickable=True)
    context = build_reasoning_context(
        "Tap Continue",
        WorldState(package="nova", elements=(button,)),
        [],
    )
    received = []

    def responder(payload):
        received.append(payload)
        return {
            "action_type": "click",
            "target": {"element_id": "n1"},
            "reason": "goal match",
        }

    decision = StructuredReasoningProvider(responder).decide(context)

    assert received[0]["goal"] == "Tap Continue"
    assert received[0]["candidates"][0]["target"]["element_id"] == "n1"
    assert decision.action.type is ActionType.CLICK
    assert decision.action.target.element_id == "n1"
    assert decision.rationale == "goal match"


def test_structured_provider_rejects_invalid_responder_output():
    context = build_reasoning_context(
        "Tap Continue",
        WorldState(
            package="nova",
            elements=(UIElement("n1", text="Continue", clickable=True),),
        ),
        [],
    )

    provider = StructuredReasoningProvider(
        lambda payload: {
            "action_type": "click",
            "target": {"element_id": "stale"},
        }
    )

    with pytest.raises(InvalidReasoningResponse, match="not available"):
        provider.decide(context)
