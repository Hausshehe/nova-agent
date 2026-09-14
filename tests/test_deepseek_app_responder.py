from __future__ import annotations

from typing import Any

from agent.deepseek_app_responder import DeepSeekAppResponder


class FakeDeepSeekTransport:
    def __init__(self) -> None:
        self.started = 0
        self.sent: list[tuple[str, str]] = []

    def start_new_chat(self) -> str:
        self.started += 1
        return f"session-{self.started}"

    def send_prompt(self, session_id: str, prompt: str) -> dict[str, Any]:
        self.sent.append((session_id, prompt))
        return {"status": "continue", "action": {"type": "none"}}


def test_reuses_one_deepseek_chat_for_multiple_reasoning_turns() -> None:
    transport = FakeDeepSeekTransport()
    responder = DeepSeekAppResponder(transport)

    assert responder.begin_mission() == "session-1"
    first = responder("turn one")
    second = responder("turn two")

    assert first["status"] == "continue"
    assert second["status"] == "continue"
    assert transport.started == 1
    assert transport.sent == [
        ("session-1", "turn one"),
        ("session-1", "turn two"),
    ]


def test_new_mission_replaces_the_previous_session() -> None:
    transport = FakeDeepSeekTransport()
    responder = DeepSeekAppResponder(transport)

    responder.begin_mission()
    responder("old mission turn")
    responder.begin_mission()
    responder("new mission turn")

    assert transport.started == 2
    assert transport.sent == [
        ("session-1", "old mission turn"),
        ("session-2", "new mission turn"),
    ]


def test_reasoning_requires_an_active_mission() -> None:
    responder = DeepSeekAppResponder(FakeDeepSeekTransport())

    try:
        responder("turn one")
    except RuntimeError as exc:
        assert "session has not been started" in str(exc)
    else:
        raise AssertionError("reasoning must require an active mission session")


def test_blank_prompt_is_rejected() -> None:
    transport = FakeDeepSeekTransport()
    responder = DeepSeekAppResponder(transport)
    responder.begin_mission()

    try:
        responder("   ")
    except ValueError as exc:
        assert "prompt must not be blank" in str(exc)
    else:
        raise AssertionError("blank prompts must be rejected")
