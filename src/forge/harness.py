"""Shared harness contracts for Forge agents.

This module intentionally contains deterministic orchestration primitives, not
LLM behavior. Model calls and AO/Hermes adapters plug into these contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic
from typing import Any, Protocol


class RunState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    BLOCKED = "blocked"
    PASSED = "passed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class Budget:
    max_steps: int = 30
    max_minutes: float = 15.0
    max_repairs: int = 2


@dataclass(frozen=True)
class HarnessInput:
    run_id: str
    task_id: str
    goal: str
    workdir: str
    context_refs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    budget: Budget = Budget()


@dataclass
class TraceEvent:
    kind: str
    actor: str
    payload: dict[str, Any]
    duration_ms: int | None = None


@dataclass
class HarnessResult:
    state: RunState
    artifact_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    events: list[TraceEvent] = field(default_factory=list)
    failure_signature: str | None = None
    handoff: dict[str, Any] | None = None


class AgentAdapter(Protocol):
    name: str

    def execute(self, request: HarnessInput, emit) -> HarnessResult:
        ...


class BoundedHarness:
    """Wrap an agent adapter with deterministic budget and trace controls."""

    def __init__(self, adapter: AgentAdapter):
        self.adapter = adapter

    def run(self, request: HarnessInput) -> HarnessResult:
        started = monotonic()
        events: list[TraceEvent] = []
        steps = 0

        def emit(kind: str, payload: dict[str, Any], duration_ms: int | None = None):
            nonlocal steps
            steps += 1
            events.append(TraceEvent(kind, self.adapter.name, payload, duration_ms))
            if steps > request.budget.max_steps:
                raise BudgetExceeded("max_steps", request.budget.max_steps)
            if (monotonic() - started) / 60 > request.budget.max_minutes:
                raise BudgetExceeded("max_minutes", request.budget.max_minutes)

        try:
            result = self.adapter.execute(request, emit)
        except BudgetExceeded as exc:
            return HarnessResult(RunState.STOPPED, events=events, failure_signature=str(exc))
        except Exception as exc:  # boundary: adapter failures become trace data
            emit("harness_error", {"error_type": type(exc).__name__})
            return HarnessResult(RunState.FAILED, events=events, failure_signature=type(exc).__name__)

        result.events = events + result.events
        return result


class BudgetExceeded(RuntimeError):
    def __init__(self, dimension: str, limit: int | float):
        super().__init__(f"budget_exceeded:{dimension}:{limit}")
        self.dimension = dimension
        self.limit = limit


@dataclass(frozen=True)
class GateVerdict:
    status: str  # validated | candidate | rejected
    applicability: bool
    ab_benefit: bool
    heldout_no_regression: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationEvidence:
    """Evidence owned by the evaluator, not authored by reflection."""

    candidate_id: str
    applicability_cases: tuple[str, ...]
    baseline_passed: int
    candidate_passed: int
    heldout_passed: int
    heldout_total: int
    evidence_refs: tuple[str, ...]


def evaluate_candidate(evidence: EvaluationEvidence) -> GateVerdict:
    """Derive a promotion verdict from comparable trial evidence.

    Counts are intentionally explicit. A reflection agent may propose a
    candidate, but it cannot manufacture this evaluator-owned record.
    """
    reasons: list[str] = []
    if not evidence.candidate_id.strip():
        reasons.append("candidate_id_missing")
    if not evidence.applicability_cases:
        reasons.append("applicability_missing")
    if evidence.baseline_passed < 0 or evidence.candidate_passed < 0:
        reasons.append("trial_counts_invalid")
    if evidence.heldout_total <= 0:
        reasons.append("heldout evidence missing")
    elif evidence.heldout_passed < evidence.heldout_total:
        reasons.append("heldout regression")
    if len(set(evidence.evidence_refs)) < 3:
        reasons.append("three evidence refs required")

    applicability = not any(reason in reasons for reason in ("candidate_id_missing", "applicability_missing"))
    heldout_no_regression = evidence.heldout_total > 0 and evidence.heldout_passed == evidence.heldout_total
    ab_benefit = evidence.candidate_passed > evidence.baseline_passed

    if reasons and any(reason in reasons for reason in ("heldout evidence missing", "heldout regression", "three evidence refs required", "trial_counts_invalid")):
        status = "rejected"
    elif applicability and ab_benefit and heldout_no_regression:
        status = "validated"
    else:
        status = "candidate"
    return GateVerdict(
        status=status,
        applicability=applicability,
        ab_benefit=ab_benefit,
        heldout_no_regression=heldout_no_regression,
        reasons=tuple(reasons or (["candidate did not improve comparable trial"] if not ab_benefit else [])),
    )


def promote_candidate(verdict: GateVerdict) -> bool:
    """Only the deterministic gate may promote a learning artifact."""
    return (
        verdict.status == "validated"
        and verdict.applicability
        and verdict.ab_benefit
        and verdict.heldout_no_regression
    )
