from nova_core.action_guard import ActionGuard
from nova_core.evidence import EvidenceTracker
from nova_core.models import Action, ActionType, Decision, Observation, UiElement


def obs(revision, *elements):
    return Observation("pkg", "activity", tuple(elements), revision)


def button(element_id, text):
    return UiElement(element_id, text=text, clickable=True, enabled=True)


def test_evidence_tracks_transition_and_generic_workflow_hints():
    tracker = EvidenceTracker()
    tracker.observe(obs(1, button("start", "Start Task"), button("cont", "Continue Task"), button("finish", "Finish Task")))
    first = tracker.snapshot()
    assert first.previous_revision is None
    assert ("start", "Start Task", 10) in first.action_stage_hints
    assert ("cont", "Continue Task", 20) in first.action_stage_hints
    assert ("finish", "Finish Task", 30) in first.action_stage_hints

    tracker.observe(obs(2, button("cont", "Continue Task"), button("finish", "Finish Task"), button("msg", "Start Task first")))
    second = tracker.snapshot()
    assert second.previous_revision == 1
    assert "Start Task first" in second.blocking_messages
    assert "Start Task" in second.removed_labels


def test_explicit_blocker_infers_later_stage_prerequisite():
    tracker = EvidenceTracker()
    tracker.observe(obs(1, button("start", "Start Task"), button("cont", "Continue Task"), button("finish", "Finish Task"), button("msg", "Start Task first")))
    evidence = tracker.snapshot()
    assert ("cont", "Continue Task", "Start Task", 10) in evidence.unsatisfied_prerequisites
    assert ("finish", "Finish Task", "Start Task", 10) in evidence.unsatisfied_prerequisites
    assert all(item[0] != "start" for item in evidence.unsatisfied_prerequisites)


def test_action_guard_blocks_later_stage_when_ui_explicitly_requires_prerequisite():
    observation = obs(1, button("start", "Start Task"), button("cont", "Continue Task"), button("msg", "Start Task first"))
    guard = ActionGuard()
    assert guard.check(Decision(Action(ActionType.TAP, "cont")), observation).allowed is False
    assert guard.check(Decision(Action(ActionType.TAP, "start")), observation).allowed is True


def test_action_guard_rejects_stale_or_unsupported_targets_before_execution():
    observation = obs(1, button("ok", "Continue"))
    guard = ActionGuard()
    assert guard.check(Decision(Action(ActionType.TAP, "missing")), observation).allowed is False
    assert guard.check(Decision(Action(ActionType.TAP, "ok")), observation).allowed is True
    assert guard.check(Decision(Action(ActionType.TAP, "ok", value="bad")), observation).allowed is False
