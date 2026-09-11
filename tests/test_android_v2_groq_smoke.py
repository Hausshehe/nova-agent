import subprocess

from nova_core.models import Action, ActionType, ExecutionResult

from agent import android_v2_groq_smoke


def test_reset_nova_process_uses_non_root_start_stop(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    android_v2_groq_smoke._reset_nova_process(3)

    assert calls[0][0] == ["am", "start", "-S", "-n", "com.hausshehe.nova/.MainActivity"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == 3
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert len(calls) == 1


def test_reset_nova_process_refuses_to_continue_if_non_root_reset_fails(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        error = subprocess.CalledProcessError(1, command)
        error.stdout = ""
        error.stderr = "permission denied"
        raise error

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    try:
        android_v2_groq_smoke._reset_nova_process(3)
    except RuntimeError as exc:
        message = str(exc)
        assert "unable to reset and launch Nova without root" in message
        assert "permission denied" in message
    else:
        raise AssertionError("expected reset failure")

    assert calls == [["am", "start", "-S", "-n", "com.hausshehe.nova/.MainActivity"]]


def test_failure_injecting_executor_reports_one_controlled_failure_after_real_execution():
    class FakeAdapter:
        def __init__(self):
            self.calls = 0

        def execute(self, action):
            self.calls += 1
            return ExecutionResult(True, True, None)

    adapter = FakeAdapter()
    execute, injected = android_v2_groq_smoke._failure_injecting_executor(adapter)
    action = Action(ActionType.TAP, target_id="recovery_test")

    first = execute(action)
    second = execute(action)

    assert first == ExecutionResult(False, False, "controlled smoke failure after Android execution")
    assert second == ExecutionResult(True, True, None)
    assert adapter.calls == 2
    assert injected() is True
