from dataclasses import dataclass, field
from typing import cast

from forge.watchdog import (
    SessionSnapshot,
    WatchdogDecision,
    WorkerClassification,
    WorkerObservation,
    apply_decision,
    classify_worker,
)


def obs(**kwargs: object) -> WorkerObservation:
    base: dict[str, object] = dict(
        snapshot=SessionSnapshot("ao-1", "working", "active", 10, 2),
        worktree_exists=True,
        changed_files=("src/a.py",),
        artifact_exists=True,
        verification_passed=False,
    )
    base.update(kwargs)
    return WorkerObservation(**cast(dict, base))


@dataclass
class FakeAO:
    sent: list[tuple[str, str]] = field(default_factory=list)
    killed: list[str] = field(default_factory=list)

    def send(self, session_id, message):
        self.sent.append((session_id, message))

    def kill(self, session_id):
        self.killed.append(session_id)


def test_verified_artifact_wins_over_idle_state():
    o = obs(snapshot=SessionSnapshot("ao-1", "idle", "idle", 100, 100), verification_passed=True)
    d = classify_worker(o)
    assert d.classification == WorkerClassification.PASSED
    assert not d.should_kill


def test_working_without_changes_gets_one_nudge_then_kill():
    o = obs(snapshot=SessionSnapshot("ao-1", "working", "active", 100, 100), changed_files=())
    d = classify_worker(o)
    assert d.classification == WorkerClassification.NO_OP
    assert d.should_nudge and not d.should_kill

    o2 = obs(snapshot=o.snapshot, changed_files=(), nudge_count=1)
    d2 = classify_worker(o2)
    assert d2.should_kill


def test_hidden_needs_input_gets_one_nudge_then_kill():
    o = obs(snapshot=SessionSnapshot("ao-1", "needs_input", "waiting_input", 1, 1))
    d = classify_worker(o)
    assert d.classification == WorkerClassification.BLOCKED_HIDDEN
    assert d.should_nudge

    d2 = classify_worker(obs(snapshot=o.snapshot, nudge_count=1))
    assert d2.should_kill


def test_visible_question_is_blocked_not_killed():
    d = classify_worker(obs(snapshot=SessionSnapshot("ao-1", "needs_input", "waiting_input", 1, 1), visible_question=True))
    assert d.classification == WorkerClassification.BLOCKED_VISIBLE
    assert not d.should_kill


def test_apply_decision_has_bounded_side_effect():
    ao = FakeAO()
    o = obs(snapshot=SessionSnapshot("ao-1", "working", "active", 100, 100), changed_files=())
    d = classify_worker(o)
    apply_decision(ao, o, d, nudge="Continue the scoped task; report blockers.")
    assert ao.sent == [("ao-1", "Continue the scoped task; report blockers.")]
    assert ao.killed == []

    o2 = obs(snapshot=o.snapshot, changed_files=(), nudge_count=1)
    d2 = classify_worker(o2)
    apply_decision(ao, o2, d2, nudge="unused")
    assert ao.killed == ["ao-1"]
