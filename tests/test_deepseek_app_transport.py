from __future__ import annotations

from dataclasses import dataclass

from agent.core import UIElement, WorldState
from agent.deepseek_app_transport import (
    DEEPSEEK_PACKAGE,
    DEEPSEEK_SHARE_COMPONENT,
    DeepSeekAppTransport,
)


@dataclass
class FakeBridge:
    states: list[WorldState]

    def __post_init__(self) -> None:
        self.opened: list[tuple[str, str | None]] = []
        self.shared: list[tuple[str, str, str]] = []
        self.clicked: list[str] = []

    def open_uri(self, uri: str, package: str | None = None) -> dict:
        self.opened.append((uri, package))
        return {"ok": True, "accepted": True}

    def share_text(self, text: str, package: str, component: str) -> dict:
        self.shared.append((text, package, component))
        return {"ok": True, "accepted": True}

    def observe(self) -> WorldState:
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]

    def click(self, element_id: str) -> dict:
        self.clicked.append(element_id)
        return {"ok": True, "accepted": True, "changed": True}


def state(*elements: UIElement, package: str = DEEPSEEK_PACKAGE) -> WorldState:
    return WorldState(
        observation_id="1",
        package=package,
        activity="MainActivity",
        elements=tuple(elements),
        timestamp_ms=1,
    )


def element(
    *,
    id: str,
    text: str = "",
    content_description: str = "",
    clickable: bool = False,
    bounds: str = "",
) -> UIElement:
    return UIElement(
        id=id,
        text=text,
        content_description=content_description,
        clickable=clickable,
        enabled=True,
        class_name="android.view.View",
        bounds=bounds,
        editable=False,
        scrollable=False,
        checkable=False,
        checked=False,
        focused=False,
        visible=True,
    )


def test_start_new_chat_opens_exposed_deepseek_uri() -> None:
    bridge = FakeBridge([state()])
    transport = DeepSeekAppTransport(bridge=bridge, sleeper=lambda _: None)

    session = transport.start_new_chat()

    assert session
    assert bridge.opened == [("dpsk://chat/new", DEEPSEEK_PACKAGE)]


def test_send_prompt_waits_for_send_readiness_then_reads_new_response() -> None:
    prompt = "Return exactly one JSON object."
    send = element(id="send-wrapper", content_description="Send", clickable=True, bounds="[1,2][3,4]")
    response = element(id="answer", text='{"status":"continue","action":{"type":"none"}}')
    bridge = FakeBridge([
        state(),
        state(),
        state(element(id="composer", text=prompt)),
        state(element(id="composer", text=prompt), send),
        state(element(id="composer", text=prompt), send, response),
        state(element(id="composer", text=prompt), send, response),
        state(element(id="composer", text=prompt), send, response),
    ])
    transport = DeepSeekAppTransport(bridge=bridge, poll_seconds=0.0, stable_polls=2, sleeper=lambda _: None)
    session = transport.start_new_chat()

    result = transport.send_prompt(session, prompt)

    assert bridge.shared == [(prompt, DEEPSEEK_PACKAGE, DEEPSEEK_SHARE_COMPONENT)]
    assert bridge.clicked == ["send-wrapper"]
    assert result["text"] == '{"status":"continue","action":{"type":"none"}}'
    assert result["session_id"] == session


def test_send_prompt_clicks_smallest_clickable_container_of_send_icon() -> None:
    prompt = "hello"
    send_semantic = element(id="send-semantic", content_description="Send", bounds="[625,935][655,965]")
    send_wrapper = element(id="send-wrapper", clickable=True, bounds="[580,890][697,1003]")
    larger_container = element(id="composer-container", clickable=True, bounds="[500,800][750,1100]")
    response = element(id="answer", text="response")
    bridge = FakeBridge([
        state(element(id="composer", text=prompt)),
        state(element(id="composer", text=prompt), send_semantic, send_wrapper, larger_container),
        state(element(id="composer", text=prompt), send_semantic, send_wrapper, larger_container, response),
        state(element(id="composer", text=prompt), send_semantic, send_wrapper, larger_container, response),
    ])
    transport = DeepSeekAppTransport(bridge=bridge, poll_seconds=0.0, stable_polls=2, sleeper=lambda _: None)
    session = transport.start_new_chat()

    transport.send_prompt(session, prompt)

    assert bridge.clicked == ["send-wrapper"]


def test_session_must_be_started_before_sending() -> None:
    bridge = FakeBridge([state()])
    transport = DeepSeekAppTransport(bridge=bridge, sleeper=lambda _: None)

    try:
        transport.send_prompt("missing", "hello")
    except RuntimeError as exc:
        assert "invalid or inactive" in str(exc)
    else:
        raise AssertionError("expected inactive session failure")
