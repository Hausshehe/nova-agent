import subprocess

from agent import android_v2_groq_smoke


def test_reset_nova_process_prefers_root_force_stop(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return None

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    android_v2_groq_smoke._reset_nova_process(3)

    assert calls[0][0] == ["su", "-c", "cmd activity force-stop com.hausshehe.nova"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == 3
    assert len(calls) == 1


def test_reset_nova_process_tries_variants_after_failure(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, command)
        return None

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    android_v2_groq_smoke._reset_nova_process(3)

    assert calls == [
        ["su", "-c", "cmd activity force-stop com.hausshehe.nova"],
        ["cmd", "activity", "force-stop", "com.hausshehe.nova"],
        ["am", "force-stop", "com.hausshehe.nova"],
    ]


def test_reset_nova_process_refuses_to_continue_if_all_variants_fail(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    try:
        android_v2_groq_smoke._reset_nova_process(3)
    except RuntimeError as exc:
        assert "refusing to run a stateful smoke test without a reset" in str(exc)
    else:
        raise AssertionError("expected reset failure")

    assert len(calls) == 3
