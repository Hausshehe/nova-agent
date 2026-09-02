from __future__ import annotations

import json
import os
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
        """Execute a direct click through Nova's Android bridge."""
        return self._request({"command": "click", "elementId": element_id})

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
        if action.type == ActionType.BACK:
            try:
                response = self._request({"command": "back"})
            except AndroidBridgeError as exc:
                return ExecutionResult(False, False, False, str(exc))
            return ExecutionResult(bool(response.get("accepted", response.get("ok", True))), bool(response.get("changed", False)))
        return ExecutionResult(False, False, False, f"unsupported action type: {action.type}")

    @staticmethod
    def _foreground_matches(output: str, package: str, component: str) -> bool:
        """Return whether ActivityManager reports the requested component foreground."""
        for line in output.splitlines():
            if "mFocusedApp=" not in line and "mResumedActivity=" not in line:
                continue
            if component in line:
                return True
        return False

    def _foreground_output(self, root: bool) -> str:
        command = ["dumpsys", "activity", "activities"]
        if root:
            command = ["su", "-c", "dumpsys activity activities"]
        result = subprocess.run(
            command,
            check=True,
            timeout=self.timeout,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def _wait_for_foreground(self, package: str, component: str, root: bool) -> bool:
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                output = self._foreground_output(root)
                if self._foreground_matches(output, package, component):
                    return True
            except (OSError, subprocess.SubprocessError):
                pass

            if time.monotonic() >= deadline:
                return False
            time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))

    def launch(self, package: str = "com.hausshehe.nova", root: bool = True) -> dict[str, Any]:
        """Launch Nova and verify ActivityManager actually foregrounded its main activity."""
        component = f"{package}/.MainActivity"
        launch_error: Exception | None = None

        try:
            response = self._request({"command": "launch", "package": package})
            if self._wait_for_foreground(package, component, root):
                return response
            launch_error = AndroidBridgeError(
                f"Android bridge reported launch success, but {component} did not become foreground"
            )
        except AndroidBridgeError as exc:
            launch_error = exc

        commands: list[list[str]] = []
        if root:
            commands.append(["su", "-c", f"am start -n {component}"])
        commands.append(["am", "start", "-n", component])

        last_error: Exception | None = launch_error
        for command in commands:
            try:
                subprocess.run(
                    command,
                    check=True,
                    timeout=self.timeout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                verified_root = command[0] == "su"
                if self._wait_for_foreground(package, component, verified_root):
                    return {"ok": True, "root": verified_root}
                last_error = AndroidBridgeError(
                    f"launch command succeeded, but {component} did not become foreground"
                )
            except Exception as exc:
                last_error = exc

        raise AndroidBridgeError(f"Unable to launch Nova: {last_error}") from last_error

    @staticmethod
    def _same_ui(before: WorldState, after: WorldState) -> bool:
        """Compare UI state while ignoring observation identity and timestamps."""
        return (
            before.package == after.package
            and before.activity == after.activity
            and before.elements == after.elements
        )

    def wait_for_fresh_observation(self, previous: WorldState, timeout: float = 2.0,
                                   poll_seconds: float = 0.2) -> WorldState:
        """Wait for a fresh observation, then return only after the UI settles."""
        deadline = time.monotonic() + timeout
        candidate: WorldState | None = None

        while True:
            state = self.observe()

            if candidate is None:
                if state.observation_id == previous.observation_id:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"timed out waiting for fresh Android observation after {previous.observation_id}"
                        )
                else:
                    candidate = state
            elif self._same_ui(candidate, state):
                return state
            else:
                candidate = state

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out waiting for settled Android observation after {previous.observation_id}"
                )
            time.sleep(poll_seconds)
