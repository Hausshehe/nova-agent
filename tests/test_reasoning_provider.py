from agent.core import Action, ActionType, Decision, UIElement, WorldState
from agent.deterministic_reasoner import DeterministicReasoner
from agent.reasoning_context import build_reasoning_context
from agent.reasoning_provider import ReasoningProvider


def test_deterministic_reasoner_implements_provider_boundary():
    state = WorldState(
        package="nova",
        observation_id="1",
        elements=(UIElement("n1", text="Finish", clickable=True),),
    )
    context = build_reasoning_context("Tap Finish", state, [])
    provider: ReasoningProvider = DeterministicReasoner()

    decision = provider.decide(context)

    assert isinstance(decision, Decision)
    assert decision.action == Action(ActionType.CLICK, context.candidates[0].target)


def test_provider_receives_goal_state_and_history():
    state = WorldState(package="nova", observation_id="7")
    history = ({"step": 1, "target_id": "n1", "verified": False},)
    context = build_reasoning_context("Continue", state, history)

    assert context.goal == "Continue"
    assert context.state is state
    assert context.history == history
