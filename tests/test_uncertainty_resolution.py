from nova_core.models import ActionType, Goal, Observation, UiElement
from nova_core.uncertainty import UncertaintyAssessment, UncertaintyResolutionPolicy


def _observation(*elements: UiElement) -> Observation:
    return Observation(
        package="com.example",
        activity="MainActivity",
        elements=tuple(elements),
        revision=3,
    )


def test_high_uncertainty_generates_goal_relevant_evidence_action() -> None:
    observation = _observation(
        UiElement(id="help", text="Help", clickable=True),
        UiElement(id="finish", text="Finish setup", clickable=True),
    )
    assessment = UncertaintyAssessment(
        level="high",
        basis="goal completion is unknown",
        unknowns=("goal completion",),
    )

    resolution = UncertaintyResolutionPolicy().resolve(
        assessment,
        observation,
        Goal("Finish setup"),
    )

    assert resolution.candidates
    assert resolution.candidates[0].action.type is ActionType.TAP
    assert resolution.candidates[0].action.target_id == "finish"
    assert resolution.candidates[0].target_label == "Finish setup"
    assert resolution.candidates[0].resolves == "goal completion"


def test_stalled_target_is_excluded_from_evidence_candidates() -> None:
    observation = _observation(
        UiElement(id="stalled", text="Continue", clickable=True),
        UiElement(id="alternative", text="Open details", clickable=True),
    )
    assessment = UncertaintyAssessment(
        level="high",
        basis="accepted action produced no observable change",
        unknowns=("whether another action is required",),
    )

    resolution = UncertaintyResolutionPolicy().resolve(
        assessment,
        observation,
        Goal("Open details"),
        excluded_target_ids=("stalled",),
    )

    ids = {candidate.action.target_id for candidate in resolution.candidates}
    assert "stalled" not in ids
    assert "alternative" in ids


def test_no_current_candidate_requires_fresh_observation_instead_of_guessing() -> None:
    observation = _observation(UiElement(id="label", text="Status"))
    assessment = UncertaintyAssessment(
        level="high",
        basis="current UI is insufficient",
        unknowns=("which action best advances the goal",),
    )

    resolution = UncertaintyResolutionPolicy().resolve(
        assessment,
        observation,
        Goal("Finish task"),
    )

    assert resolution.candidates == ()
    assert "Gather fresh observation" in resolution.guidance[1]
