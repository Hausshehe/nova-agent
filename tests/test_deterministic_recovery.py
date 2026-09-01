from agent.core import UIElement, WorldState
from agent.deterministic_reasoner import DeterministicReasoner
from agent.reasoning_context import build_reasoning_context


def test_deterministic_reasoner_avoids_previously_failed_target():
    first = UIElement("n1", text="Try action", clickable=True)
    fallback = UIElement("n2", text="Alternative action", clickable=True)
    state = WorldState(package="nova", observation_id="2", elements=(first, fallback))
    history = ({
        "step": 1,
        "action_type": "click",
        "target_id": "n1",
        "target_text": "Try action",
        "target_content_description": "",
        "accepted": True,
        "changed": True,
        "verified": False,
        "error": None,
    },)

    context = build_reasoning_context("Complete task", state, history)
    decision = DeterministicReasoner().plan(context)

    assert decision.action.target is not None
    assert decision.action.target.element_id == "n2"
    assert decision.action.target.element_id != history[0]["target_id"]
