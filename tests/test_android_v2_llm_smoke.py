import json

from agent.android_v2_llm_smoke import _controlled_responder


def test_controlled_responder_selects_safe_visible_target():
    prompt = json.dumps({
        "goal": "Tap Test Navigation Action",
        "observation": {
            "package": "com.hausshehe.nova",
            "activity": "MainActivity",
            "revision": 1,
            "elements": [
                {
                    "id": "heading",
                    "text": "Navigation",
                    "content_description": "",
                    "clickable": False,
                    "enabled": True,
                    "class_name": "TextView",
                    "editable": False,
                    "scrollable": False,
                    "checkable": False,
                    "checked": False,
                    "focused": False,
                    "visible": True,
                },
                {
                    "id": "target",
                    "text": "Test Navigation Action",
                    "content_description": "",
                    "clickable": True,
                    "enabled": True,
                    "class_name": "Button",
                    "editable": False,
                    "scrollable": False,
                    "checkable": False,
                    "checked": False,
                    "focused": False,
                    "visible": True,
                },
            ],
        },
        "history": [],
    })

    result = _controlled_responder(prompt)

    assert result == {
        "action_type": "tap",
        "target_id": "target",
        "reason": "controlled model-shaped decision",
    }
