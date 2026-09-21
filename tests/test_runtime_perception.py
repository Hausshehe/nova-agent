from types import SimpleNamespace

import pytest

import nova_core.runtime as runtime_module


def _runtime_type():
    return next(
        cls
        for cls in vars(runtime_module).values()
        if isinstance(cls, type) and "_observe" in cls.__dict__
    )


class RecordingBrain:
    def __init__(self):
        self.summaries = []

    def record_perception(self, summary):
        self.summaries.append(summary)


class RecordingObserver:
    def __init__(self, observation):
        self.observation = observation
        self.calls = []

    def observe(self):
        self.calls.append(("observe", None))
        return self.observation


class RecordingPerceiver:
    def __init__(self, summary="screen looks ready", error=None):
        self.summary = summary
        self.error = error
        self.observations = []

    def assess(self, observation):
        self.observations.append(observation)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(summary=self.summary)


def _runtime(observer, perceiver):
    runtime = _runtime_type().__new__(_runtime_type())
    runtime.observer = observer
    runtime.perceiver = perceiver
    runtime.brain = RecordingBrain()
    return runtime


def test_observe_preserves_authoritative_observation_and_records_perception():
    observation = object()
    observer = RecordingObserver(observation)
    perceiver = RecordingPerceiver()

    runtime = _runtime(observer, perceiver)

    result = runtime._observe()

    assert result is observation
    assert observer.calls == [("observe", None)]
    assert perceiver.observations == [observation]
    assert runtime.brain.summaries == ["", "screen looks ready"]


def test_observe_without_perceiver_preserves_existing_behavior():
    observation = object()
    observer = RecordingObserver(observation)

    runtime = _runtime(observer, None)

    result = runtime._observe()

    assert result is observation
    assert observer.calls == [("observe", None)]
    assert runtime.brain.summaries == [""]


@pytest.mark.parametrize("error", [ValueError("bad summary"), RuntimeError("provider down"), TypeError("bad type")])
def test_perception_failure_does_not_fail_observation(error):
    observation = object()
    observer = RecordingObserver(observation)
    perceiver = RecordingPerceiver(error=error)

    runtime = _runtime(observer, perceiver)

    result = runtime._observe()

    assert result is observation
    assert perceiver.observations == [observation]
    assert runtime.brain.summaries == [""]


def test_perception_summary_is_forwarded_to_reasoning_context():
    observation = object()
    observer = RecordingObserver(observation)
    perceiver = RecordingPerceiver(summary="button is enabled")

    runtime = _runtime(observer, perceiver)

    runtime._observe()

    assert runtime.brain.summaries[-1] == "button is enabled"


def test_fresh_observation_is_used_after_changed_execution():
    class FreshMarker:
        pass

    class FreshObserver(RecordingObserver, FreshMarker):
        def observe_fresh(self, previous):
            self.calls.append(("observe_fresh", previous))
            return self.observation

    original_marker = runtime_module.FreshObserver
    runtime_module.FreshObserver = FreshMarker
    try:
        previous = object()
        observation = object()
        observer = FreshObserver(observation)
        perceiver = RecordingPerceiver()

        runtime = _runtime(observer, perceiver)

        result = runtime._observe(fresh_from=previous)

        assert result is observation
        assert observer.calls == [("observe_fresh", previous)]
        assert perceiver.observations == [observation]
    finally:
        runtime_module.FreshObserver = original_marker


def test_perception_cannot_replace_authoritative_observation():
    observation = object()
    observer = RecordingObserver(observation)

    class LyingPerceiver(RecordingPerceiver):
        def assess(self, value):
            self.observations.append(value)
            return SimpleNamespace(summary="fake", observation=object())

    runtime = _runtime(observer, LyingPerceiver())

    result = runtime._observe()

    assert result is observation
    assert runtime.brain.summaries == ["", "fake"]
