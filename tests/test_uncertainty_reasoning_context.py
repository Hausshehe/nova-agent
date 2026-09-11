from nova_core.models import Goal, Observation, UiElement
from nova_core.runtime_brain import RuntimeBrain


def test_mission_snapshot_exposes_evidence_seeking_candidates() -> None:
    brain = RuntimeBrain.create(Goal("Finish setup"))
    brain.start()
    brain.record_observation(
        Observation(
            package="com.example",
            activity="MainActivity",
            elements=(UiElement(id="finish", text="Finish setup", clickable=True),),
            revision=1,
        )
    )

    snapshot = brain.mission.reasoning_snapshot()

    resolution = snapshot["uncertainty_resolution"]
    assert resolution["candidates"][0]["target_id"] == "finish"
    assert resolution["candidates"][0]["action"] == "tap"


def test_runtime_brain_reasoning_context_carries_uncertainty_resolution() -> None:
    brain = RuntimeBrain.create(Goal("Finish setup"))
    brain.start()
    brain.record_observation(
        Observation(
            package="com.example",
            activity="MainActivity",
            elements=(UiElement(id="finish", text="Finish setup", clickable=True),),
            revision=1,
        )
    )

    context = brain.reasoning_context()

    assert context.uncertainty_resolution is None
    assert context.mission_state is brain.mission
    assert context.mission_state.reasoning_snapshot()["uncertainty_resolution"]["candidates"]
