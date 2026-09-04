from agent import android_v2_groq_smoke


def test_reset_nova_process_prefers_root_force_stop(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return None

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    android_v2_groq_smoke._reset_nova_process(3)

    assert calls[0][0] == ["su", "-c", "am force-stop com.hausshehe.nova"]
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == 3
    assert len(calls) == 1


def test_reset_nova_process_falls_back_to_am(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ["su", "-c"]:
            raise FileNotFoundError()
        return None

    monkeypatch.setattr(android_v2_groq_smoke.subprocess, "run", run)

    android_v2_groq_smoke._reset_nova_process(3)

    assert calls == [
        ["su", "-c", "am force-stop com.hausshehe.nova"],
        ["am", "force-stop", "com.hausshehe.nova"],
    ]
