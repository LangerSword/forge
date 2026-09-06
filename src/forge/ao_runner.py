"""Bounded Forge runner for AO workers.

The runner deliberately uses the documented AO CLI spawn command and the
read-only/session action surface exposed by :class:`forge.ao.AOClient`.  It
never infers success from an AO status alone: a filesystem artifact and, when
configured, an independent verifier must agree before a run passes.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from .ao_cli import AOCLI, AOCommandResult, parse_spawn_output
from .ledger import Ledger
from .watchdog import (
    SessionSnapshot,
    WatchdogDecision,
    WorkerClassification,
    WorkerObservation,
    classify_worker,
)


class AOClientLike(Protocol):
    def session(self, session_id: str) -> dict[str, Any]: ...
    def send(self, session_id: str, message: str) -> dict[str, Any]: ...
    def kill(self, session_id: str) -> dict[str, Any]: ...


ChangedFilesProbe = Callable[[Path], tuple[str, ...]]
IndependentVerifier = Callable[[Path, Path], bool]
SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class AORunRequest:
    run_id: str
    goal: str
    project: str
    worker_name: str
    prompt: str
    harness: str = "opencode"
    mode: str = "chat"
    condition: str = "C0"
    artifact_path: Path | None = None
    worktree: Path | None = None
    max_polls: int = 30
    poll_interval_s: float = 1.0
    max_idle_s: float = 90.0
    nudge: str = "Continue the scoped task; report blockers."

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if not self.goal.strip():
            raise ValueError("goal is required")
        if not self.project.strip():
            raise ValueError("project is required")
        if not self.worker_name.strip():
            raise ValueError("worker_name is required")
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        if self.max_polls < 1:
            raise ValueError("max_polls must be >= 1")
        if self.poll_interval_s < 0:
            raise ValueError("poll_interval_s must be >= 0")
        if self.max_idle_s < 0:
            raise ValueError("max_idle_s must be >= 0")


@dataclass(frozen=True)
class AORunEvent:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "payload": _json_safe(self.payload)}


@dataclass(frozen=True)
class AORunResult:
    run_id: str
    status: str
    classification: WorkerClassification | None
    session_id: str | None
    worktree: Path | None
    artifact_exists: bool
    verification_passed: bool
    events: tuple[AORunEvent, ...]
    reason: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "forge.ao-runner.v1",
            "run_id": self.run_id,
            "status": self.status,
            "passed": self.passed,
            "classification": self.classification.value if self.classification else None,
            "session_id": self.session_id,
            "worktree": str(self.worktree) if self.worktree else None,
            "artifact_exists": self.artifact_exists,
            "verification_passed": self.verification_passed,
            "reason": self.reason,
            "events": [event.to_dict() for event in self.events],
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, WorkerClassification):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value


def _nested_value(payload: Any, names: set[str]) -> Any | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in names and value not in (None, ""):
                return value
        for value in payload.values():
            found = _nested_value(value, names)
            if found not in (None, ""):
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _nested_value(value, names)
            if found not in (None, ""):
                return found
    return None


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def session_snapshot(payload: dict[str, Any], *, session_id: str) -> SessionSnapshot:
    """Normalize an observed AO session response to the watchdog contract."""
    raw_id = _nested_value(payload, {"session_id", "sessionId", "id"})
    observed_id = str(raw_id) if raw_id not in (None, "") else session_id
    raw_status = _nested_value(payload, {"status", "state"})
    status = str(raw_status).strip().lower() if raw_status not in (None, "") else "unknown"
    activity = _nested_value(payload, {"activity_state", "activityState", "activity"})
    activity_state = str(activity).strip().lower() if activity not in (None, "") else status
    elapsed = _number(_nested_value(payload, {"elapsed_s", "elapsedSeconds", "elapsed"}))
    last_activity = _number(_nested_value(payload, {"last_activity_s", "lastActivitySeconds", "last_activity"}))
    terminated = _bool(_nested_value(payload, {"is_terminated", "isTerminated", "terminated"}))
    if status in {"terminated", "exited", "killed", "failed"}:
        terminated = True
    return SessionSnapshot(
        session_id=observed_id,
        status=status,
        activity_state=activity_state,
        elapsed_s=elapsed,
        last_activity_s=last_activity,
        is_terminated=terminated,
    )


def _default_changed_files(worktree: Path) -> tuple[str, ...]:
    if not worktree.is_dir():
        return ()
    try:
        proc = subprocess.run(
            ("git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if proc.returncode != 0:
        return ()
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) > 3:
            paths.append(line[3:].strip())
    return tuple(paths)


def _safe_command(command: tuple[str, ...]) -> tuple[str, ...]:
    """Keep commands useful for evidence without persisting the prompt."""
    result: list[str] = []
    redact_next = False
    for item in command:
        if redact_next:
            result.append("<redacted>")
            redact_next = False
        else:
            result.append(item)
            redact_next = item == "--prompt"
    return tuple(result)


class AORunner:
    """Run one AO worker with a bounded poll/nudge/kill policy."""

    def __init__(
        self,
        *,
        ao_cli: AOCLI,
        ao_client: AOClientLike,
        ledger: Ledger | None = None,
        changed_files_probe: ChangedFilesProbe | None = None,
        independent_verifier: IndependentVerifier | None = None,
        sleep_fn: SleepFn = time.sleep,
    ) -> None:
        self.ao_cli = ao_cli
        self.ao_client = ao_client
        self.ledger = ledger
        self.changed_files_probe = changed_files_probe or _default_changed_files
        self.independent_verifier = independent_verifier
        self.sleep_fn = sleep_fn

    def _record(self, events: list[AORunEvent], request: AORunRequest, kind: str, payload: dict[str, Any]) -> None:
        event = AORunEvent(kind, _json_safe(payload))
        events.append(event)
        if self.ledger is not None:
            self.ledger.event(request.run_id, kind, "ao-runner", event.payload)

    def _result(
        self,
        request: AORunRequest,
        events: list[AORunEvent],
        *,
        status: str,
        classification: WorkerClassification | None,
        session_id: str | None,
        worktree: Path | None,
        artifact_exists: bool = False,
        verification_passed: bool = False,
        reason: str = "",
    ) -> AORunResult:
        result = AORunResult(
            run_id=request.run_id,
            status=status,
            classification=classification,
            session_id=session_id,
            worktree=worktree,
            artifact_exists=artifact_exists,
            verification_passed=verification_passed,
            events=tuple(events),
            reason=reason,
        )
        self._record(
            events,
            request,
            "verdict",
            {
                "status": result.status,
                "classification": result.classification.value if result.classification else None,
                "artifact_exists": result.artifact_exists,
                "verification_passed": result.verification_passed,
                "reason": result.reason,
            },
        )
        # The result owns an immutable snapshot of events.  Rebuild after the
        # verdict event so callers and the ledger see the same terminal trace.
        result = AORunResult(
            run_id=result.run_id,
            status=result.status,
            classification=result.classification,
            session_id=result.session_id,
            worktree=result.worktree,
            artifact_exists=result.artifact_exists,
            verification_passed=result.verification_passed,
            events=tuple(events),
            reason=result.reason,
        )
        if self.ledger is not None:
            self.ledger.update_run_status(request.run_id, result.status)
        return result

    def run(self, request: AORunRequest) -> AORunResult:
        events: list[AORunEvent] = []
        if self.ledger is not None:
            self.ledger.run(request.run_id, request.goal, request.condition, request.harness, "running")

        try:
            command = self.ao_cli.spawn_command(
                project=request.project,
                name=request.worker_name,
                prompt=request.prompt,
                harness=request.harness,
                mode=request.mode,
            )
            self._record(events, request, "spawn", {"command": _safe_command(command), "decision": "execute"})
            spawned = self.ao_cli.spawn(
                project=request.project,
                name=request.worker_name,
                prompt=request.prompt,
                harness=request.harness,
                mode=request.mode,
            )
            parsed = parse_spawn_output(spawned)
            self._record(
                events,
                request,
                "spawn_result",
                {"exit_code": spawned.exit_code, "session_id": parsed.session_id, "worktree": parsed.worktree},
            )
        except Exception as exc:
            self._record(events, request, "spawn_error", {"error_type": type(exc).__name__})
            return self._result(
                request,
                events,
                status="failed",
                classification=WorkerClassification.TERMINATED,
                session_id=None,
                worktree=request.worktree,
                reason=f"spawn_failed:{type(exc).__name__}",
            )

        session_id = parsed.session_id
        worktree = parsed.worktree or request.worktree
        nudge_count = 0
        last_artifact = False
        last_verification = False
        last_classification: WorkerClassification | None = None
        last_reason = ""

        for poll_number in range(1, request.max_polls + 1):
            try:
                payload = self.ao_client.session(session_id)
                snapshot = session_snapshot(payload, session_id=session_id)
            except Exception as exc:
                self._record(events, request, "poll_error", {"poll": poll_number, "error_type": type(exc).__name__})
                return self._result(
                    request,
                    events,
                    status="failed",
                    classification=WorkerClassification.LIVENESS_STUCK,
                    session_id=session_id,
                    worktree=worktree,
                    artifact_exists=last_artifact,
                    verification_passed=last_verification,
                    reason=f"poll_failed:{type(exc).__name__}",
                )

            artifact = self._artifact_path(request, worktree)
            artifact_exists = artifact is not None and artifact.exists() and artifact.is_file()
            changed_files = self.changed_files_probe(worktree) if worktree is not None else ()
            verification_passed = False
            verification_error: str | None = None
            if artifact_exists:
                if self.independent_verifier is None:
                    verification_passed = True
                else:
                    try:
                        verification_root = worktree if worktree is not None else artifact.parent
                        verification_passed = bool(self.independent_verifier(verification_root, artifact))
                    except Exception as exc:
                        verification_error = type(exc).__name__
            if artifact is not None:
                self._record(
                    events,
                    request,
                    "check",
                    {
                        "poll": poll_number,
                        "artifact": artifact,
                        "artifact_exists": artifact_exists,
                        "verification_passed": verification_passed,
                        "verification_error": verification_error,
                    },
                )
            visible_question = self._visible_question(payload)
            observation = WorkerObservation(
                snapshot=snapshot,
                worktree_exists=worktree is not None and worktree.is_dir(),
                changed_files=changed_files,
                artifact_exists=artifact_exists,
                verification_passed=verification_passed,
                visible_question=visible_question,
                nudge_count=nudge_count,
            )
            decision = classify_worker(observation, max_idle_s=request.max_idle_s)
            self._record(
                events,
                request,
                "poll",
                {
                    "poll": poll_number,
                    "session_id": session_id,
                    "status": snapshot.status,
                    "activity_state": snapshot.activity_state,
                    "elapsed_s": snapshot.elapsed_s,
                    "last_activity_s": snapshot.last_activity_s,
                    "changed_files": changed_files,
                    "artifact_exists": artifact_exists,
                    "verification_passed": verification_passed,
                },
            )
            self._record(
                events,
                request,
                "watchdog",
                {
                    "poll": poll_number,
                    "classification": decision.classification,
                    "should_nudge": decision.should_nudge,
                    "should_kill": decision.should_kill,
                    "reason": decision.reason,
                },
            )
            last_artifact, last_verification = artifact_exists, verification_passed
            last_classification, last_reason = decision.classification, decision.reason

            if decision.classification == WorkerClassification.PASSED:
                return self._result(
                    request,
                    events,
                    status="passed",
                    classification=decision.classification,
                    session_id=session_id,
                    worktree=worktree,
                    artifact_exists=artifact_exists,
                    verification_passed=verification_passed,
                    reason=decision.reason,
                )
            if decision.classification == WorkerClassification.BLOCKED_VISIBLE:
                return self._result(
                    request,
                    events,
                    status="blocked",
                    classification=decision.classification,
                    session_id=session_id,
                    worktree=worktree,
                    artifact_exists=artifact_exists,
                    verification_passed=verification_passed,
                    reason=decision.reason,
                )
            if decision.should_nudge:
                try:
                    self.ao_client.send(session_id, request.nudge)
                    self._record(
                        events,
                        request,
                        "send",
                        {"session_id": session_id, "decision": "nudge", "nudge_number": nudge_count + 1},
                    )
                    nudge_count += 1
                except Exception as exc:
                    self._record(events, request, "send_error", {"session_id": session_id, "error_type": type(exc).__name__})
                    return self._result(
                        request,
                        events,
                        status="failed",
                        classification=decision.classification,
                        session_id=session_id,
                        worktree=worktree,
                        artifact_exists=artifact_exists,
                        verification_passed=verification_passed,
                        reason=f"nudge_failed:{type(exc).__name__}",
                    )
            elif decision.should_kill:
                try:
                    self.ao_client.kill(session_id)
                    self._record(
                        events,
                        request,
                        "kill",
                        {"session_id": session_id, "decision": "watchdog", "reason": decision.reason},
                    )
                except Exception as exc:
                    self._record(events, request, "kill_error", {"session_id": session_id, "error_type": type(exc).__name__})
                status = "blocked" if decision.classification in {
                    WorkerClassification.BLOCKED_HIDDEN,
                    WorkerClassification.BLOCKED_VISIBLE,
                } else "failed"
                return self._result(
                    request,
                    events,
                    status=status,
                    classification=decision.classification,
                    session_id=session_id,
                    worktree=worktree,
                    artifact_exists=artifact_exists,
                    verification_passed=verification_passed,
                    reason=decision.reason,
                )

            if poll_number < request.max_polls:
                self.sleep_fn(request.poll_interval_s)

        try:
            self.ao_client.kill(session_id)
            self._record(
                events,
                request,
                "kill",
                {"session_id": session_id, "decision": "poll_budget", "reason": "poll budget exhausted"},
            )
        except Exception as exc:
            self._record(events, request, "kill_error", {"session_id": session_id, "error_type": type(exc).__name__})
        return self._result(
            request,
            events,
            status="failed",
            classification=WorkerClassification.LIVENESS_STUCK,
            session_id=session_id,
            worktree=worktree,
            artifact_exists=last_artifact,
            verification_passed=last_verification,
            reason=f"poll_budget_exhausted:{last_reason or 'worker did not reach a verified terminal state'}",
        )

    @staticmethod
    def _artifact_path(request: AORunRequest, worktree: Path | None) -> Path | None:
        if request.artifact_path is None:
            return None
        if request.artifact_path.is_absolute():
            return request.artifact_path
        if worktree is None:
            return None
        return worktree / request.artifact_path

    @staticmethod
    def _visible_question(payload: dict[str, Any]) -> bool:
        value = _nested_value(payload, {"visible_question", "visibleQuestion", "actionable_question"})
        return _bool(value)
