import json

from agent.android_v2_llm_smoke import _controlled_responder


def test_controlled_responder_selects_safe_visible_target():
    prompt = json.dumps({
        "goal": "Tap Test Navigation Action",
        "observation": {
            "package": "com.hausshehe.nova",
            "activity": "MainActivity",
            "revision": 1,
            "actions": [
                {
                    "id": "heading",
                    "label": "Navigation",
                },
                {
                    "id": "target",
                    "label": "Test Navigation Action",
                    "tap": True,
                },
            ],
            "visible_labels": [
                "Navigation",
                "Test Navigation Action",
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
