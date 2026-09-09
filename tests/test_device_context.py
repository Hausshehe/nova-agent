from nova_core.improvement.device_context import DeviceEvidence, MAX_ELEMENTS, MAX_TEXT_CHARS
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Observation, UiElement


def test_device_evidence_captures_live_ui_and_action() -> None:
    observation = Observation(
        package="com.example.nova",
        activity="MainActivity",
        revision=7,
        elements=(
            UiElement(id="continue", text="Continue", clickable=True),
            UiElement(id="finish", content_description="Finish", clickable=True),
        ),
    )
    decision = Decision(Action(type=ActionType.TAP, target_id="continue"), reason="advance")
    execution = ExecutionResult(accepted=False, changed=False, error="prerequisite missing")

    evidence = DeviceEvidence.from_runtime(observation, decision, execution, previous=Observation(
        package="com.example.nova", activity="MainActivity", revision=6, elements=()
    ))

    assert evidence.package == "com.example.nova"
    assert evidence.activity == "MainActivity"
    assert evidence.revision == 7
    assert evidence.previous_revision == 6
    assert evidence.visible_elements == ("Continue", "Finish")
    assert evidence.last_action == "tap target=continue"
    assert evidence.action_accepted is False
    assert evidence.action_changed is False
    assert evidence.action_error == "prerequisite missing"


def test_device_evidence_is_bounded() -> None:
    observation = Observation(
        package="pkg",
        activity="Activity",
        revision=1,
        elements=tuple(
            UiElement(id=f"id-{i}", text="x" * (MAX_TEXT_CHARS + 100))
            for i in range(MAX_ELEMENTS + 10)
        ),
    )
    evidence = DeviceEvidence.from_runtime(observation)

    assert len(evidence.visible_elements) == MAX_ELEMENTS
    assert all(len(label) <= MAX_TEXT_CHARS for label in evidence.visible_elements)
    assert all(len(line) <= MAX_TEXT_CHARS + 1000 for line in evidence.bounded_lines())
