import json

from agent.core import ActionType, UIElement, WorldState
from agent.reasoning_context import build_reasoning_context
from agent.reasoning_payload import reasoning_payload


def test_reasoning_payload_contains_goal_state_history_and_candidates():
    state = WorldState(
        package="com.hausshehe.nova",
        activity="MainActivity",
        observation_id="42",
        timestamp_ms=1234,
        elements=(
            UIElement(
                "n1",
                text="Continue",
                content_description="Continue task",
                clickable=True,
                enabled=True,
                class_name="android.widget.Button",
                bounds="[0,0][100,50]",
                focused=True,
            ),
            UIElement("status", text="Step 2 started", clickable=False),
        ),
    )
    history = ({"step": 1, "action_type": "click", "target_id": "n0", "verified": False},)
    context = build_reasoning_context("Continue the task", state, history)

    payload = reasoning_payload(context)

    assert payload["goal"] == "Continue the task"
    assert payload["state"]["package"] == "com.hausshehe.nova"
    assert payload["state"]["activity"] == "MainActivity"
    assert payload["state"]["observation_id"] == "42"
    assert payload["state"]["status_text"] == ["Step 2 started"]
    assert payload["history"] == list(history)
    assert payload["candidates"][0]["action_type"] == ActionType.CLICK.value
    assert payload["candidates"][0]["target"]["element_id"] == "n1"
    assert payload["candidates"][-2]["action_type"] == ActionType.BACK.value
    assert payload["candidates"][-1]["action_type"] == ActionType.WAIT.value


def test_reasoning_payload_excludes_clickable_elements_from_status_text():
    state = WorldState(
        package="nova",
        elements=(
            UIElement("n1", text="Finish", clickable=True),
            UIElement("status", text="Step 2 started", clickable=False),
        ),
    )
    context = build_reasoning_context("Tap Finish", state, [])

    payload = reasoning_payload(context)

    assert payload["state"]["status_text"] == ["Step 2 started"]
    assert "Finish" not in payload["state"]["status_text"]


def test_reasoning_payload_includes_current_ui_evidence_for_state_reasoning():
    state = WorldState(
        package="nova",
        elements=(
            UIElement(
                "n1",
                text="Finish",
                content_description="Finish task",
                clickable=True,
                enabled=True,
                scrollable=False,
                visible=True,
            ),
            UIElement(
                "n2",
                text="Continue",
                clickable=True,
                enabled=True,
                visible=True,
            ),
            UIElement("status", text="Step 1 started", clickable=False, visible=True),
        ),
    )
    context = build_reasoning_context("Tap Finish", state, [])

    payload = reasoning_payload(context)
    current_ui = payload["state"]["current_ui"]

    assert [item["element_id"] for item in current_ui] == ["n1", "n2", "status"]
    assert current_ui[0]["text"] == "Finish"
    assert current_ui[0]["clickable"] is True
    assert current_ui[0]["enabled"] is True
    assert current_ui[1]["text"] == "Continue"
    assert current_ui[2]["text"] == "Step 1 started"
    assert current_ui[2]["clickable"] is False
    assert set(current_ui[0]) == {
        "element_id",
        "text",
        "content_description",
        "clickable",
        "enabled",
        "visible",
        "scrollable",
    }


def test_reasoning_payload_is_json_serializable():
    state = WorldState(
        package="nova",
        elements=(UIElement("n1", text="Finish", clickable=True),),
    )
    context = build_reasoning_context("Tap Finish", state, [])

    encoded = json.dumps(reasoning_payload(context))

    assert '"goal": "Tap Finish"' in encoded
    assert '"current_ui"' in encoded
