import pytest

from nova_core.state_machine import InvalidTransition, RunState, is_terminal, transition


def test_happy_path_transitions_one_step_at_a_time() -> None:
    state = transition(RunState.CREATED, RunState.OBSERVING)
    state = transition(state, RunState.DECIDING)
    state = transition(state, RunState.EXECUTING)
    state = transition(state, RunState.VERIFYING)
    state = transition(state, RunState.SUCCEEDED)
    assert state is RunState.SUCCEEDED


def test_verification_can_return_to_observing_for_another_bounded_step() -> None:
    assert transition(RunState.VERIFYING, RunState.OBSERVING) is RunState.OBSERVING


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunState.CREATED, RunState.EXECUTING),
        (RunState.OBSERVING, RunState.SUCCEEDED),
        (RunState.DECIDING, RunState.OBSERVING),
        (RunState.EXECUTING, RunState.DECIDING),
        (RunState.SUCCEEDED, RunState.OBSERVING),
        (RunState.FAILED, RunState.CREATED),
        (RunState.ABORTED, RunState.OBSERVING),
    ],
)
def test_illegal_transition_is_rejected(current: RunState, target: RunState) -> None:
    with pytest.raises(InvalidTransition):
        transition(current, target)


def test_terminal_states_have_no_outgoing_transitions() -> None:
    for state in (RunState.SUCCEEDED, RunState.FAILED, RunState.ABORTED):
        assert is_terminal(state)
        with pytest.raises(InvalidTransition):
            transition(state, RunState.OBSERVING)


def test_failure_and_abort_are_explicit_terminal_paths() -> None:
    assert transition(RunState.OBSERVING, RunState.FAILED) is RunState.FAILED
    assert transition(RunState.CREATED, RunState.ABORTED) is RunState.ABORTED
