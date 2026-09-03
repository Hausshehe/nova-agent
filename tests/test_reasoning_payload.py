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


def test_reasoning_payload_omits_llm_irrelevant_ui_metadata():
    state = WorldState(
        package="nova",
        elements=(
            UIElement(
                "n1",
                text="Finish",
                content_description="Finish task",
                clickable=True,
                enabled=True,
                class_name="android.widget.Button",
                bounds="[0,0][100,50]",
                editable=True,
                scrollable=True,
                checkable=True,
                checked=True,
                focused=True,
                visible=True,
            ),
        ),
    )
    context = build_reasoning_context("Tap Finish", state, [])

    payload = reasoning_payload(context)
    candidate = payload["candidates"][0]

    assert set(payload["state"]) == {
        "package",
        "activity",
        "observation_id",
        "status_text",
    }
    assert set(candidate) == {"action_type", "target", "enabled", "visible"}
    assert set(candidate["target"]) == {"element_id", "text", "content_description"}
    assert "elements" not in payload["state"]
    assert "bounds" not in candidate
    assert "class_name" not in candidate


def test_reasoning_payload_is_json_serializable():
    state = WorldState(
        package="nova",
        elements=(UIElement("n1", text="Finish", clickable=True),),
    )
    context = build_reasoning_context("Tap Finish", state, [])

    encoded = json.dumps(reasoning_payload(context))

    assert '"goal": "Tap Finish"' in encoded
