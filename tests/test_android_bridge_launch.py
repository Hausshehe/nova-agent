from __future__ import annotations

import subprocess

import pytest

from agent.android_bridge import AndroidBridge, AndroidBridgeError


FOREGROUND_NOVA = (
    "mFocusedApp=ActivityRecord{123 u0 com.hausshehe.nova/.MainActivity t1}"
)
FOREGROUND_TERMUX = "mFocusedApp=ActivityRecord{123 u0 com.termux/.app.TermuxActivity t1}"


def test_launch_verifies_requested_activity_is_foreground(monkeypatch):
    bridge = AndroidBridge(timeout=0.1)
    calls = []

    monkeypatch.setattr(
        bridge,
        "_request",
        lambda payload: {"ok": True, "root": False},
    )

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=FOREGROUND_NOVA, stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    result = bridge.launch(root=False)

    assert result["ok"] is True
    assert calls == [["dumpsys", "activity", "activities"]]


def test_launch_does_not_report_success_when_wrong_activity_remains_foreground(monkeypatch):
    bridge = AndroidBridge(timeout=0.1)

    monkeypatch.setattr(
        bridge,
        "_request",
        lambda payload: {"ok": True, "root": False},
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=FOREGROUND_TERMUX, stderr=""
        ),
    )

    with pytest.raises(AndroidBridgeError, match="did not become foreground"):
        bridge.launch(root=False)


def test_launch_falls_back_to_am_when_bridge_launch_is_unavailable(monkeypatch):
    bridge = AndroidBridge(timeout=0.1)
    calls = []
    bridge._request = lambda payload: (_ for _ in ()).throw(
        AndroidBridgeError("bridge unavailable")
    )

    def run(command, **kwargs):
        calls.append(command)
        if command == ["su", "-c", "am start -n com.hausshehe.nova/.MainActivity"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["su", "-c", "dumpsys activity activities"]:
            return subprocess.CompletedProcess(command, 0, stdout=FOREGROUND_NOVA, stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(subprocess, "run", run)

    result = bridge.launch()

    assert result == {"ok": True, "root": True}
    assert calls == [
        ["su", "-c", "am start -n com.hausshehe.nova/.MainActivity"],
        ["su", "-c", "dumpsys activity activities"],
    ]


def test_launch_raises_when_am_start_succeeds_but_foreground_verification_fails(monkeypatch):
    bridge = AndroidBridge(timeout=0.1)
    bridge._request = lambda payload: (_ for _ in ()).throw(
        AndroidBridgeError("bridge unavailable")
    )

    def run(command, **kwargs):
        if command[0] == "su" and command[2].startswith("am start"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[0] == "su" and command[2].startswith("dumpsys"):
            return subprocess.CompletedProcess(command, 0, stdout=FOREGROUND_TERMUX, stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(AndroidBridgeError, match="did not become foreground"):
        bridge.launch()
