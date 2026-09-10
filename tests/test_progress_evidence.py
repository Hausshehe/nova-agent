from nova_core.evidence import EvidenceTracker
from nova_core.models import Observation, UiElement


def _observation(revision: int, label: str = "Continue") -> Observation:
    return Observation(
        package="com.example.app",
        activity="MainActivity",
        revision=revision,
        elements=(UiElement(id="button", text=label, clickable=True),),
    )


def test_revision_change_alone_is_not_progress() -> None:
    tracker = EvidenceTracker()
    tracker.observe(_observation(1))
    tracker.observe(_observation(2))
    evidence = tracker.snapshot()

    assert evidence.observation_changed is False
    assert evidence.unchanged_observation_count == 1


def test_ui_change_resets_stagnation_and_records_progress() -> None:
    tracker = EvidenceTracker()
    tracker.observe(_observation(1, "Continue"))
    tracker.observe(_observation(2, "Continue"))
    tracker.observe(_observation(3, "Finish"))
    evidence = tracker.snapshot()

    assert evidence.observation_changed is True
    assert evidence.unchanged_observation_count == 0
    assert evidence.added_labels == ("Finish",)
    assert evidence.removed_labels == ("Continue",)


def test_three_identical_observations_report_bounded_stagnation_count() -> None:
    tracker = EvidenceTracker()
    tracker.observe(_observation(1))
    tracker.observe(_observation(2))
    tracker.observe(_observation(3))
    evidence = tracker.snapshot()

    assert evidence.unchanged_observation_count == 2


def test_progress_evidence_is_exposed_to_reasoning_payload() -> None:
    from nova_core.models import Goal
    from nova_core.reasoning import ReasoningContext
    from nova_core.reasoning_adapter import _reasoning_payload

    tracker = EvidenceTracker()
    tracker.observe(_observation(1))
    tracker.observe(_observation(2))
    evidence = tracker.snapshot()
    payload = _reasoning_payload(
        ReasoningContext(goal=Goal("Finish"), observation=_observation(2), evidence=evidence)
    )

    assert payload["evidence"]["observation_changed"] is False
    assert payload["evidence"]["unchanged_observation_count"] == 1
