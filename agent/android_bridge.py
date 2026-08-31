from __future__ import annotations

import json
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UIElement:
    id: str
    text: str = ""
    content_description: str = ""
    clickable: bool = False
    enabled: bool = True
    class_name: str = ""
    bounds: str = ""


@dataclass(frozen=True)
class AndroidState:
    observation_id: int
    package: str
    activity: str
    elements: tuple[UIElement, ...]


class AndroidBridgeError(RuntimeError):
    pass


class AndroidBridge:
    """Small client for Nova's localhost Android command server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 18765, timeout: float = 3.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = (json.dumps(payload) + "\n").encode()
        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(raw)
                data = b""
                while b"\n" not in data:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
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
        result = []
        for item in raw or []:
            result.append(UIElement(
                id=str(item.get("id", "")),
                text=str(item.get("text", "")),
                content_description=str(item.get("contentDescription", item.get("content_description", ""))),
                clickable=bool(item.get("clickable", False)),
                enabled=bool(item.get("enabled", True)),
                class_name=str(item.get("className", item.get("class_name", ""))),
                bounds=str(item.get("bounds", "")),
            ))
        return tuple(result)

    def observe(self) -> AndroidState:
        response = self._request({"command": "observe"})
        state = response.get("state", response)
        return AndroidState(
            observation_id=int(state.get("observationId", state.get("observation_id", 0))),
            package=str(state.get("package", "")),
            activity=str(state.get("activity", "")),
            elements=self._elements(state.get("elements", [])),
        )

    def click(self, element_id: str) -> dict[str, Any]:
        return self._request({"command": "click", "elementId": element_id})

    def launch(self, package: str = "com.hausshehe.nova") -> dict[str, Any]:
        try:
            return self._request({"command": "launch", "package": package})
        except AndroidBridgeError:
            # The server may not expose launch on older builds. Fall back to Termux.
            try:
                subprocess.run(["am", "start", "-n", f"{package}/.MainActivity"], check=True,
                               timeout=self.timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"ok": True}
            except Exception as exc:
                raise AndroidBridgeError(f"Unable to launch Nova: {exc}") from exc

    def wait_for_fresh_observation(self, previous_id: int, max_seconds: float = 2.0,
                                   poll_seconds: float = 0.2) -> AndroidState:
        deadline = time.monotonic() + max_seconds
        while True:
            state = self.observe()
            if state.observation_id != previous_id:
                return state
            if time.monotonic() >= deadline:
                raise AndroidBridgeError(
                    f"timed out waiting for fresh Android observation after {previous_id}"
                )
            time.sleep(poll_seconds)
