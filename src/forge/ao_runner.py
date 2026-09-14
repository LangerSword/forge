"""Bounded Forge runner for AO workers.

The runner deliberately uses the documented AO CLI spawn command and the
read-only/session action surface exposed by :class:`forge.ao.AOClient`.  It
never infers success from an AO status alone: a filesystem artifact and, when
configured, an independent verifier must agree before a run passes.
"""
from __future__ import annotations

import subprocess
import time
import hashlib
from datetime import datetime, timezone
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
    model: str | None = None
    artifact_path: Path | None = None
    worktree: Path | None = None
    existing_session_id: str | None = None
    independent_verifier: IndependentVerifier | None = None
    max_polls: int = 30
    max_runtime_s: float | None = None
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
        if self.max_runtime_s is not None and self.max_runtime_s <= 0:
            raise ValueError("max_runtime_s must be > 0 when provided")


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


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def session_snapshot(
    payload: dict[str, Any],
    *,
    session_id: str,
    now: datetime | None = None,
) -> SessionSnapshot:
    """Normalize an observed AO session response to the watchdog contract."""
    raw_id = _nested_value(payload, {"session_id", "sessionId", "id"})
    observed_id = str(raw_id) if raw_id not in (None, "") else session_id
    raw_status = _nested_value(payload, {"status", "state"})
    status = str(raw_status).strip().lower() if raw_status not in (None, "") else "unknown"
    activity = _nested_value(payload, {"activity_state", "activityState"})
    if activity in (None, ""):
        activity_payload = _nested_value(payload, {"activity"})
        if isinstance(activity_payload, dict):
            activity = activity_payload.get("state")
    activity_state = str(activity).strip().lower() if activity not in (None, "") else status
    elapsed = _number(_nested_value(payload, {"elapsed_s", "elapsedSeconds", "elapsed"}))
    last_activity = _number(_nested_value(payload, {"last_activity_s", "lastActivitySeconds", "last_activity"}))
    now = now or datetime.now(timezone.utc)
    created_at = _parse_timestamp(_nested_value(payload, {"createdAt", "created_at"}))
    last_activity_at = _parse_timestamp(_nested_value(payload, {"lastActivityAt", "last_activity_at"}))
    if created_at is not None:
        elapsed = max(0.0, (now - created_at).total_seconds())
    if last_activity_at is not None:
        last_activity = max(0.0, (now - last_activity_at).total_seconds())
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


def _artifact_fingerprint(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


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

    def _cleanup_session(
        self,
        request: AORunRequest,
        events: list[AORunEvent],
        session_id: str,
        *,
        reason: str,
    ) -> None:
        """Close a terminal AO session without changing the verifier verdict."""
        try:
            self.ao_client.kill(session_id)
            self._record(
                events,
                request,
                "cleanup",
                {"session_id": session_id, "action": "kill", "reason": reason},
            )
        except Exception as exc:
            self._record(
                events,
                request,
                "cleanup_error",
                {"session_id": session_id, "error_type": type(exc).__name__, "reason": reason},
            )

    def run(self, request: AORunRequest) -> AORunResult:
        events: list[AORunEvent] = []
        if self.ledger is not None:
            self.ledger.run(request.run_id, request.goal, request.condition, request.harness, "running")

        if request.existing_session_id:
            session_id = request.existing_session_id
            worktree = request.worktree
            self._record(
                events,
                request,
                "resume",
                {"session_id": session_id, "decision": "poll_existing_session", "worktree": worktree},
            )
        else:
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
            if worktree is None:
                discover = getattr(self.ao_cli, "discover_worktree", None)
                if discover is not None:
                    worktree = discover(session_id)
                    self._record(
                        events,
                        request,
                        "worktree_discovered" if worktree is not None else "worktree_unavailable",
                        {"session_id": session_id, "worktree": worktree},
                    )
        nudge_count = 0
        independent_verifier = request.independent_verifier or self.independent_verifier
        last_artifact = False
        last_verification = False
        last_classification: WorkerClassification | None = None
        last_reason = ""
        artifact = self._artifact_path(request, worktree)
        baseline_fingerprint = _artifact_fingerprint(artifact)
        self._record(
            events,
            request,
            "artifact_baseline",
            {"artifact": artifact, "fingerprint": baseline_fingerprint},
        )

        started_at = time.monotonic()
        for poll_number in range(1, request.max_polls + 1):
            if request.max_runtime_s is not None and time.monotonic() - started_at >= request.max_runtime_s:
                try:
                    self.ao_client.kill(session_id)
                    self._record(
                        events,
                        request,
                        "kill",
                        {"session_id": session_id, "decision": "runtime_budget", "max_runtime_s": request.max_runtime_s},
                    )
                except Exception as exc:
                    self._record(events, request, "kill_error", {"session_id": session_id, "error_type": type(exc).__name__})
                return self._result(
                    request,
                    events,
                    status="stopped",
                    classification=WorkerClassification.LIVENESS_STUCK,
                    session_id=session_id,
                    worktree=worktree,
                    artifact_exists=last_artifact,
                    verification_passed=last_verification,
                    reason="runtime_budget_exceeded",
                )
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
            artifact_fingerprint = _artifact_fingerprint(artifact)
            artifact_exists = artifact_fingerprint is not None
            artifact_fresh = artifact_exists and artifact_fingerprint != baseline_fingerprint
            changed_files = self.changed_files_probe(worktree) if worktree is not None else ()
            verification_passed = False
            verification_error: str | None = None
            if artifact_exists and not artifact_fresh:
                self._record(
                    events,
                    request,
                    "stale_artifact",
                    {"poll": poll_number, "artifact": artifact, "fingerprint": artifact_fingerprint},
                )
                if snapshot.is_terminated or snapshot.status in {"terminated", "exited", "killed", "completed", "done"}:
                    return self._result(
                        request,
                        events,
                        status="blocked",
                        classification=WorkerClassification.TERMINATED,
                        session_id=session_id,
                        worktree=worktree,
                        artifact_exists=True,
                        verification_passed=False,
                        reason="stale_artifact",
                    )
            if artifact_exists and artifact_fresh:
                if independent_verifier is None:
                    self._record(
                        events,
                        request,
                        "verification_unavailable",
                        {"poll": poll_number, "reason": "independent verifier is required"},
                    )
                    if not snapshot.is_terminated and snapshot.status not in {"terminated", "exited", "killed"}:
                        try:
                            self.ao_client.kill(session_id)
                            self._record(
                                events,
                                request,
                                "kill",
                                {"session_id": session_id, "decision": "verification_unavailable"},
                            )
                        except Exception as exc:
                            self._record(
                                events,
                                request,
                                "kill_error",
                                {"session_id": session_id, "error_type": type(exc).__name__},
                            )
                    return self._result(
                        request,
                        events,
                        status="blocked",
                        classification=WorkerClassification.VERIFICATION_UNAVAILABLE,
                        session_id=session_id,
                        worktree=worktree,
                        artifact_exists=True,
                        verification_passed=False,
                        reason="independent_verifier_required",
                    )
                else:
                    try:
                        verification_root = worktree if worktree is not None else artifact.parent
                        assert artifact is not None
                        verification_passed = bool(independent_verifier(verification_root, artifact))
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
                        "artifact_fresh": artifact_fresh,
                        "artifact_fingerprint": artifact_fingerprint,
                        "baseline_fingerprint": baseline_fingerprint,
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
                self._cleanup_session(
                    request,
                    events,
                    session_id,
                    reason="verified_artifact",
                )
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
