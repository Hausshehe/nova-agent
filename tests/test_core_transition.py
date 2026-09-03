from agent.core import ExecutionResult, TransitionVerifier, UIElement, WorldState


def test_transition_verifier_ignores_observation_identity_when_ui_is_unchanged():
    before = WorldState(observation_id="10", timestamp_ms=100, elements=(UIElement(id="x", text="Ready"),))
    after = WorldState(observation_id="11", timestamp_ms=200, elements=(UIElement(id="x", text="Ready"),))

    assert TransitionVerifier().verify(before, after, ExecutionResult(True, True)) is False


def test_transition_verifier_accepts_real_ui_change_with_new_observation():
    before = WorldState(observation_id="10", elements=(UIElement(id="x", text="Ready"),))
    after = WorldState(observation_id="11", elements=(UIElement(id="x", text="Complete"),))

    assert TransitionVerifier().verify(before, after, ExecutionResult(True, True)) is True
