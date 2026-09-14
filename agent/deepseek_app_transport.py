from __future__ import annotations

import re
import time
import uuid
from typing import Any, Protocol

from .android_bridge import AndroidBridge
from .core import WorldState


DEEPSEEK_PACKAGE = "com.deepseek.chat"
DEEPSEEK_NEW_CHAT_URI = "dpsk://chat/new"
DEEPSEEK_SHARE_COMPONENT = "com.deepseek.chat.ShareProxyActivity"


class DeepSeekTransportError(RuntimeError):
    pass


class DeepSeekBridge(Protocol):
    def open_uri(uri: str, package: str | None = None) -> dict[str, Any]: ...
    def share_text(text: str, package: str, component: str) -> dict[str, Any]: ...
    def observe() -> WorldState: ...
    def click(element_id: str) -> dict[str, Any]: ...


class DeepSeekAppTransport:
    """Drive the normal DeepSeek Android app UI through Nova's bridge.

    This transport deliberately uses only exposed Android intents plus
    accessibility observation/clicking. It does not inspect DeepSeek's private
    network protocol or app storage.
    """

    def __init__(
        self,
        bridge: DeepSeekBridge | None = None,
        *,
        timeout: float = 30.0,
        poll_seconds: float = 0.4,
        stable_polls: int = 3,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        self.bridge = bridge or AndroidBridge()
        self.timeout = timeout
        self.poll_seconds = poll_seconds
        self.stable_polls = stable_polls
        self._clock = clock
        self._sleep = sleeper
        self._session_id: str | None = None

    def start_new_chat(self) -> str:
        self.bridge.open_uri(DEEPSEEK_NEW_CHAT_URI, DEEPSEEK_PACKAGE)
        self._wait_for_package()
        self._session_id = str(uuid.uuid4())
        return self._session_id

    def send_prompt(self, session_id: str, prompt: str) -> dict[str, Any]:
        if not session_id or session_id != self._session_id:
            raise DeepSeekTransportError("invalid or inactive DeepSeek mission session")
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be blank")

        before = self.bridge.observe()
        baseline_texts = self._text_values(before)
        self.bridge.share_text(prompt, DEEPSEEK_PACKAGE, DEEPSEEK_SHARE_COMPONENT)
        send_id = self._wait_for_send_control(prompt)
        click_result = self.bridge.click(send_id)
        if not bool(click_result.get("accepted", click_result.get("ok", False))):
            raise DeepSeekTransportError(
                f"DeepSeek Send control was not accepted: {click_result.get('error', 'unknown error')}"
            )

        response = self._wait_for_response(prompt, baseline_texts)
        return {
            "text": response,
            "session_id": session_id,
            "package": DEEPSEEK_PACKAGE,
        }

    def _wait_for_package(self) -> WorldState:
        deadline = self._clock() + self.timeout
        last_state: WorldState | None = None
        while self._clock() < deadline:
            state = self.bridge.observe()
            last_state = state
            if state.package == DEEPSEEK_PACKAGE:
                return state
            self._sleep(self.poll_seconds)
        active = last_state.package if last_state else ""
        raise DeepSeekTransportError(
            f"timed out waiting for DeepSeek app; active package={active!r}"
        )

    @staticmethod
    def _normalize_prompt_text(text: str) -> str:
        return " ".join(text.split())

    def _wait_for_send_control(self, prompt: str) -> str:
        """Wait until the submitted prompt and an actionable Send control coexist.

        DeepSeek can expose the composer text before its Send button/wrapper has
        settled into the accessibility hierarchy. The semantic Send node can
        also be a non-clickable icon inside a larger clickable wrapper, so the
        wrapper is selected by containment rather than requiring identical bounds.
        """
        deadline = self._clock() + self.timeout
        normalized_prompt = self._normalize_prompt_text(prompt)
        while self._clock() < deadline:
            state = self.bridge.observe()
            if state.package == DEEPSEEK_PACKAGE and any(
                self._normalize_prompt_text(element.text) == normalized_prompt
                for element in state.elements
                if element.visible
            ):
                send_id = self._find_send_id(state)
                if send_id is not None:
                    return send_id
            self._sleep(self.poll_seconds)
        raise DeepSeekTransportError(
            "timed out waiting for DeepSeek Send control after prompt became visible"
        )

    def _wait_for_response(self, prompt: str, baseline_texts: set[str]) -> str:
        deadline = self._clock() + self.timeout
        first_response_at: float | None = None
        last_candidate = ""
        stable_count = 0

        while self._clock() < deadline:
            state = self.bridge.observe()
            candidate = self._extract_response(state, prompt, baseline_texts)
            if candidate:
                if first_response_at is None:
                    first_response_at = self._clock()
                if candidate == last_candidate:
                    stable_count += 1
                else:
                    last_candidate = candidate
                    stable_count = 1
                if (
                    stable_count >= self.stable_polls
                    and self._clock() - first_response_at >= self.poll_seconds
                ):
                    return candidate
            self._sleep(self.poll_seconds)

        raise DeepSeekTransportError("timed out waiting for a stable DeepSeek response")

    @staticmethod
    def _text_values(state: WorldState) -> set[str]:
        return {
            element.text.strip()
            for element in state.elements
            if element.visible and element.text.strip()
        }

    @staticmethod
    def _parse_bounds(bounds: str) -> tuple[int, int, int, int] | None:
        match = re.fullmatch(
            r"\[\s*(-?\d+)\s*,\s*(-?\d+)\]\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]",
            bounds.strip(),
        )
        if not match:
            return None
        left, top, right, bottom = (int(value) for value in match.groups())
        if right < left or bottom < top:
            return None
        return left, top, right, bottom

    @classmethod
    def _find_send_id(cls, state: WorldState) -> str | None:
        candidates = [
            element
            for element in state.elements
            if element.visible
            and element.enabled
            and element.content_description.strip().lower() == "send"
        ]
        if not candidates:
            return None
        for element in candidates:
            if element.clickable:
                return element.id

        # DeepSeek can expose the white Send arrow as a non-clickable semantic
        # node inside a larger clickable blue button. Select the smallest
        # enabled clickable element whose bounds contain that semantic node.
        for semantic in candidates:
            semantic_bounds = cls._parse_bounds(semantic.bounds)
            if semantic_bounds is None:
                continue
            s_left, s_top, s_right, s_bottom = semantic_bounds
            containing: list[tuple[int, str]] = []
            for element in state.elements:
                if not element.visible or not element.enabled or not element.clickable:
                    continue
                wrapper_bounds = cls._parse_bounds(element.bounds)
                if wrapper_bounds is None:
                    continue
                w_left, w_top, w_right, w_bottom = wrapper_bounds
                if (
                    w_left <= s_left
                    and w_top <= s_top
                    and w_right >= s_right
                    and w_bottom >= s_bottom
                ):
                    area = (w_right - w_left) * (w_bottom - w_top)
                    containing.append((area, element.id))
            if containing:
                return min(containing, key=lambda item: item[0])[1]
        return None

    @classmethod
    def _extract_response(
        cls,
        state: WorldState,
        prompt: str,
        baseline_texts: set[str],
    ) -> str:
        candidates: list[str] = []
        for element in state.elements:
            text = element.text.strip()
            if not element.visible or not text or text == prompt.strip():
                continue
            if text in baseline_texts:
                continue
            if cls._looks_like_control_text(text):
                continue
            candidates.append(text)

        if not candidates:
            return ""
        return max(candidates, key=len)

    @staticmethod
    def _looks_like_control_text(text: str) -> bool:
        normalized = text.strip().lower()
        return normalized in {
            "send",
            "think",
            "search",
            "attach files",
            "deepseek",
            "new chat",
        }


def build_deepseek_mission_transport(bridge: DeepSeekBridge | None = None) -> DeepSeekAppTransport:
    return DeepSeekAppTransport(bridge=bridge)
