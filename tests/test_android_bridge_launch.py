from __future__ import annotations

import subprocess

import pytest

from agent.android_bridge import AndroidBridge, AndroidBridgeError


def test_launch_returns_bridge_response_without_root_fallback(monkeypatch):
    bridge = AndroidBridge(timeout=0.1)
    calls = []

    monkeypatch.setattr(
        bridge,
        "_request",
        lambda payload: {"ok": True, "root": False},
    )

    def run(command, **kwargs):
        calls.append(command)
        raise AssertionError("shell fallback must not run when bridge launch succeeds")

    monkeypatch.setattr(subprocess, "run", run)

    result = bridge.launch()

    assert result == {"ok": True, "root": False}
    assert calls == []


def test_launch_falls_back_to_non_root_am_when_bridge_launch_is_unavailable(monkeypatch):
    bridge = AndroidBridge(timeout=0.1)
    calls = []
    bridge._request = lambda payload: (_ for _ in ()).throw(
        AndroidBridgeError("bridge unavailable")
    )

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    result = bridge.launch()

    assert result == {"ok": True}
    assert calls == [["am", "start", "-n", "com.hausshehe.nova/.MainActivity"]]


def test_launch_raises_when_non_root_am_start_fails(monkeypatch):
    bridge = AndroidBridge(timeout=0.1)
    bridge._request = lambda payload: (_ for _ in ()).throw(
        AndroidBridgeError("bridge unavailable")
    )

    def run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(AndroidBridgeError, match="Unable to launch Nova"):
        bridge.launch()
