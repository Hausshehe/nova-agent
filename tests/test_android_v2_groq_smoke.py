import subprocess

from agent import android_v2_groq_smoke


def test_reset_nova_process_prefers_root_start_stop(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    android_v2_groq_smoke._reset_nova_process(3)

    assert calls[0][0] == ["su", "-c", "am start -S -n com.hausshehe.nova/.MainActivity"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == 3
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert len(calls) == 1


def test_reset_nova_process_tries_variants_after_failure(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if len(calls) < 2:
            raise subprocess.CalledProcessError(1, command, stdout="", stderr="permission denied")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    android_v2_groq_smoke._reset_nova_process(3)

    assert calls == [
        ["su", "-c", "am start -S -n com.hausshehe.nova/.MainActivity"],
        ["am", "start", "-S", "-n", "com.hausshehe.nova/.MainActivity"],
    ]


def test_reset_nova_process_refuses_to_continue_if_all_variants_fail(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command, stdout="", stderr="permission denied")

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    try:
        android_v2_groq_smoke._reset_nova_process(3)
    except RuntimeError as exc:
        message = str(exc)
        assert "refusing to run a stateful smoke test without a reset" in message
        assert "exit=1" in message
        assert "permission denied" in message
    else:
        raise AssertionError("expected reset failure")

    assert len(calls) == 2
