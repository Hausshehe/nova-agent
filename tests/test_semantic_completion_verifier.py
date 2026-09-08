from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.semantic_verifier import SemanticGoalVerifier


def _verify(after_elements: tuple[UiElement, ...]) -> bool:
    verifier = SemanticGoalVerifier()
    before = Observation(
        package="com.hausshehe.nova",
        activity="android.widget.FrameLayout",
        elements=(),
        revision=1,
    )
    after = Observation(
        package="com.hausshehe.nova",
        activity="android.widget.FrameLayout",
        elements=after_elements,
        revision=2,
    )
    decision = Decision(
        action=Action(ActionType.TAP, target_id="com.hausshehe.nova:id/test"),
    )
    result = ExecutionResult(accepted=True, changed=True)
    return verifier.verify(Goal("Finish Multi-Step"), before, decision, result, after)


def test_finish_button_is_not_completion_evidence() -> None:
    assert not _verify(
        (
            UiElement(
                id="com.hausshehe.nova:id/multi_step_finish",
                text="FINISH MULTI-STEP",
                clickable=True,
            ),
        )
    )


def test_completed_status_is_completion_evidence() -> None:
    assert _verify(
        (
            UiElement(
                id="com.hausshehe.nova:id/multi_step_status",
                text="Multi-Step Test completed",
                clickable=False,
            ),
        )
    )


def test_finish_button_and_completed_status_require_the_status() -> None:
    assert _verify(
        (
            UiElement(
                id="com.hausshehe.nova:id/multi_step_finish",
                text="FINISH MULTI-STEP",
                clickable=True,
            ),
            UiElement(
                id="com.hausshehe.nova:id/multi_step_status",
                text="Multi-Step Test completed",
                clickable=False,
            ),
        )
    )
