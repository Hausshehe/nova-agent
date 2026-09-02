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
        assert "Do not use an 'action' field." in prompt
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


def test_llm_provider_reasoning_contract_requires_current_state_and_prerequisites():
    button = UIElement("n1", text="Finish multi-step", clickable=True)
    context = build_reasoning_context(
        "Multi-Step completed",
        WorldState(package="nova", elements=(button,)),
        [{"target_id": "n0", "verified": True}],
    )
    received = []

    def responder(prompt):
        received.append(prompt)
        return {
            "action_type": "click",
            "target": {"element_id": "n1"},
            "reason": "test decision",
        }

    LLMReasoningProvider(responder).decide(context)

    contract = received[0]
    required_instructions = (
        "Reason from the CURRENT OBSERVATION, not from the goal text alone.",
        "The goal describes the desired end state.",
        "Treat visible UI text, status messages, and the current observation as the",
        "Use the action history to understand what has already been attempted.",
        "Never claim that the goal is complete unless the current observation provides",
        "If an action appears to require a prerequisite that has not been established,",
        "After a failed or rejected attempt, re-evaluate the fresh observation before",
        "Do not assume that an accepted Android click means the intended task was completed.",
    )
    for instruction in required_instructions:
        assert instruction in contract

    payload = json.loads(contract.split("Observation and goal:\n", 1)[1])
    assert payload["goal"] == "Multi-Step completed"
    assert payload["history"][0]["target_id"] == "n0"


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
