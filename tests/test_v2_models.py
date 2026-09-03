from nova_core.models import (
    Action,
    ActionType,
    Goal,
    Observation,
    RunStatus,
    UiElement,
)


def test_goal_rejects_blank_text() -> None:
    try:
        Goal("   ")
    except ValueError:
        return
    raise AssertionError("blank goals must be rejected")


def test_observation_is_immutable_data() -> None:
    observation = Observation(
        package="com.example",
        activity="MainActivity",
        elements=(UiElement(id="save", text="Save", clickable=True),),
        revision=1,
    )
    assert observation.elements[0].id == "save"
    assert observation.revision == 1


def test_action_has_no_execution_behavior() -> None:
    action = Action(ActionType.TAP, target_id="save")
    assert action.type is ActionType.TAP
    assert action.target_id == "save"


def test_run_status_is_explicit() -> None:
    assert RunStatus.CREATED.value == "created"
    assert RunStatus.RUNNING.value == "running"
    assert RunStatus.SUCCEEDED.value == "succeeded"
