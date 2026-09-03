from __future__ import annotations

import json
import socket
import subprocess
import time
from typing import Any

from .core import Action, ActionType, ExecutionResult, UIElement, WorldState


class AndroidBridgeError(RuntimeError):
    pass


class AndroidBridge:
    """Client for Nova's localhost Android command server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18765, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = (json.dumps(payload) + "\n").encode()
        deadline = time.monotonic() + self.timeout
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                sock.settimeout(min(0.5, self.timeout))
                sock.sendall(raw)
                data = b""
                while b"\n" not in data:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise AndroidBridgeError(
                            f"Android bridge response timed out after {self.timeout:.1f}s"
                        )
                    sock.settimeout(min(0.5, remaining))
                    try:
                        chunk = sock.recv(65536)
                    except socket.timeout as exc:
                        if time.monotonic() >= deadline:
                            raise AndroidBridgeError(
                                f"Android bridge response timed out after {self.timeout:.1f}s"
                            ) from exc
                        continue
                    if not chunk:
                        break
                    data += chunk
        except AndroidBridgeError:
            raise
        except OSError as exc:
            raise AndroidBridgeError(f"Android bridge unavailable: {exc}") from exc
        if not data:
            raise AndroidBridgeError("Android bridge returned no response")
        try:
            response = json.loads(data.split(b"\n", 1)[0].decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AndroidBridgeError("Invalid Android bridge response") from exc
        if response.get("ok") is False:
            raise AndroidBridgeError(str(response.get("error", "Android bridge request failed")))
        return response

    @staticmethod
    def _elements(raw: Any) -> tuple[UIElement, ...]:
        return tuple(
            UIElement(
                id=str(item.get("id", "")),
                text=str(item.get("text", "")),
                content_description=str(item.get("contentDescription", item.get("content_description", ""))),
                clickable=bool(item.get("clickable", False)),
                enabled=bool(item.get("enabled", True)),
                class_name=str(item.get("className", item.get("class_name", ""))),
                bounds=str(item.get("bounds", "")),
                editable=bool(item.get("editable", False)),
                scrollable=bool(item.get("scrollable", False)),
                checkable=bool(item.get("checkable", False)),
                checked=bool(item.get("checked", False)),
                focused=bool(item.get("focused", False)),
                visible=bool(item.get("visible", True)),
            )
            for item in (raw or [])
        )

    def observe(self) -> WorldState:
        response = self._request({"command": "observe"})
        state = response.get("state", response)
        return WorldState(
            observation_id=str(state.get("observationId", state.get("observation_id", ""))),
            package=str(state.get("package", "")),
            activity=str(state.get("activity", "")),
            elements=self._elements(state.get("elements", [])),
            timestamp_ms=int(state.get("timestampMs", state.get("timestamp_ms", 0)) or 0),
        )

    def click(self, element_id: str) -> dict[str, Any]:
        return self._request({"command": "click", "elementId": element_id})

    def scroll(self, element_id: str) -> dict[str, Any]:
        return self._request({"command": "scroll", "elementId": element_id})

    def execute(self, action: Action) -> ExecutionResult:
        if action.type == ActionType.CLICK:
            if action.target is None:
                return ExecutionResult(False, False, False, "click action has no target")
            try:
                response = self.click(action.target.element_id)
            except AndroidBridgeError as exc:
                return ExecutionResult(False, False, False, str(exc))
            return ExecutionResult(
                accepted=bool(response.get("accepted", response.get("ok", True))),
                changed=bool(response.get("changed", False)),
                verified=bool(response.get("verified", False)),
                error=response.get("error"),
            )
        if action.type == ActionType.SCROLL:
            if action.target is None:
                return ExecutionResult(False, False, False, "scroll action has no target")
            try:
                response = self.scroll(action.target.element_id)
            except AndroidBridgeError as exc:
                return ExecutionResult(False, False, False, str(exc))
            return ExecutionResult(
                accepted=bool(response.get("accepted", response.get("ok", True))),
                changed=bool(response.get("changed", False)),
                verified=bool(response.get("verified", False)),
                error=response.get("error"),
            )
        if action.type == ActionType.BACK:
            try:
                response = self._request({"command": "back"})
            except AndroidBridgeError as exc:
                return ExecutionResult(False, False, False, str(exc))
            return ExecutionResult(bool(response.get("accepted", response.get("ok", True))), bool(response.get("changed", False)))
        return ExecutionResult(False, False, False, f"unsupported action type: {action.type}")

    def launch(self, package: str = "com.hausshehe.nova", root: bool = True) -> dict[str, Any]:
        try:
            return self._request({"command": "launch", "package": package})
        except AndroidBridgeError:
            component = f"{package}/.MainActivity"
            commands: list[list[str]] = []
            if root:
                commands.append(["su", "-c", f"am start -n {component}"])
            commands.append(["am", "start", "-n", component])
            last_error: Exception | None = None
            for command in commands:
                try:
                    subprocess.run(command, check=True, timeout=self.timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return {"ok": True, "root": command[0] == "su"}
                except Exception as exc:
                    last_error = exc
            raise AndroidBridgeError(f"Unable to launch Nova: {last_error}") from last_error

    @staticmethod
    def _same_ui(left: WorldState, right: WorldState) -> bool:
        return (
            left.package == right.package
            and left.activity == right.activity
            and left.elements == right.elements
        )

    def wait_for_fresh_observation(
        self,
        previous: WorldState,
        timeout: float = 2.0,
        poll_seconds: float = 0.2,
    ) -> WorldState:
        """Wait for a fresh observation whose UI has also stabilized.

        A new accessibility observation ID only proves that an accessibility
        event occurred. It does not prove that the post-action UI is settled.
        Require two consecutive identical UI snapshots after the first fresh
        observation, while keeping the whole wait bounded.
        """
        deadline = time.monotonic() + timeout
        candidate: WorldState | None = None
        while True:
            state = self.observe()
            if state.observation_id != previous.observation_id:
                if candidate is not None and self._same_ui(candidate, state):
                    return state
                candidate = state

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"timed out waiting for fresh stable Android observation after {previous.observation_id}"
                )
            time.sleep(min(poll_seconds, remaining))
