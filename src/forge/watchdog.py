"""AO worker watchdog and executor boundary.

AO is the execution plane, but its session status alone is insufficient. This
module combines AO state with observable worktree artifacts and verification
signals before classifying a worker run.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class WorkerClassification(StrEnum):
    WORKING = "working"
    PASSED = "passed"
    BLOCKED_VISIBLE = "blocked_visible"
    BLOCKED_HIDDEN = "blocked_hidden"
    NO_OP = "no_op"
    LIVENESS_STUCK = "liveness_stuck"
    TERMINATED = "terminated"


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    status: str
    activity_state: str
    elapsed_s: float
    last_activity_s: float
    is_terminated: bool = False


@dataclass(frozen=True)
class WorkerObservation:
    snapshot: SessionSnapshot
    worktree_exists: bool
    changed_files: tuple[str, ...]
    artifact_exists: bool
    verification_passed: bool
    visible_question: bool = False
    nudge_count: int = 0


@dataclass(frozen=True)
class WatchdogDecision:
    classification: WorkerClassification
    should_nudge: bool = False
    should_kill: bool = False
    reason: str = ""


class AOExecutor(Protocol):
    def send(self, session_id: str, message: str) -> None: ...
    def kill(self, session_id: str) -> None: ...


def classify_worker(obs: WorkerObservation, *, max_idle_s: float = 90.0) -> WatchdogDecision:
    """Classify a worker from observed AO state plus filesystem/verifier evidence."""
    s = obs.snapshot
    if obs.verification_passed and obs.artifact_exists:
        return WatchdogDecision(WorkerClassification.PASSED, reason="artifact and independent verification passed")
    if s.is_terminated or s.status in {"terminated", "exited"}:
        return WatchdogDecision(WorkerClassification.TERMINATED, reason="AO reports terminated/exited")
    if s.status == "needs_input":
        if obs.visible_question:
            return WatchdogDecision(WorkerClassification.BLOCKED_VISIBLE, reason="worker has an actionable visible question")
        if obs.nudge_count == 0:
            return WatchdogDecision(WorkerClassification.BLOCKED_HIDDEN, should_nudge=True, reason="needs_input without an observable question")
        return WatchdogDecision(WorkerClassification.BLOCKED_HIDDEN, should_kill=True, reason="needs_input remained hidden after one nudge")
    if s.status in {"working", "running"}:
        if not obs.worktree_exists and s.elapsed_s >= max_idle_s:
            return WatchdogDecision(WorkerClassification.LIVENESS_STUCK, should_kill=True, reason="working without a worktree past liveness budget")
        if obs.worktree_exists and not obs.changed_files and s.elapsed_s >= max_idle_s:
            if obs.nudge_count == 0:
                return WatchdogDecision(WorkerClassification.NO_OP, should_nudge=True, reason="working with no changed files past artifact checkpoint")
            return WatchdogDecision(WorkerClassification.NO_OP, should_kill=True, reason="no changed files after one nudge")
        return WatchdogDecision(WorkerClassification.WORKING, reason="worker active within artifact checkpoint")
    if s.status == "idle":
        if obs.artifact_exists and not obs.verification_passed:
            return WatchdogDecision(WorkerClassification.NO_OP, reason="idle with artifact awaiting independent verification")
        return WatchdogDecision(WorkerClassification.NO_OP, reason="idle without verified artifact")
    return WatchdogDecision(WorkerClassification.LIVENESS_STUCK, should_kill=True, reason=f"unrecognized AO status: {s.status}")


def apply_decision(executor: AOExecutor, obs: WorkerObservation, decision: WatchdogDecision, *, nudge: str) -> WatchdogDecision:
    """Apply only the bounded side effect selected by classify_worker."""
    if decision.should_nudge:
        executor.send(obs.snapshot.session_id, nudge)
    elif decision.should_kill:
        executor.kill(obs.snapshot.session_id)
    return decision
