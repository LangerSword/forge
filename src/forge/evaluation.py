"""Verifier-owned evaluation for candidate learning artifacts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from .harness import EvaluationEvidence, GateVerdict, evaluate_candidate


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    evidence_ref: str


class CaseExecutor(Protocol):
    def __call__(self, case: EvaluationCase, candidate_id: str | None) -> bool: ...


@dataclass(frozen=True)
class EvaluationRun:
    evidence: EvaluationEvidence
    verdict: GateVerdict


def run_candidate_evaluation(
    candidate_id: str,
    train_cases: Iterable[EvaluationCase],
    heldout_cases: Iterable[EvaluationCase],
    *,
    baseline_executor: CaseExecutor,
    candidate_executor: CaseExecutor,
) -> EvaluationRun:
    """Run comparable baseline/candidate trials and a sealed held-out check.

    The executor is supplied by the verifier/evaluation harness. Reflection
    output never supplies pass/fail values. Held-out cases are accepted as a
    separate iterable so callers can keep them isolated from candidate context.
    """
    train = tuple(train_cases)
    heldout = tuple(heldout_cases)
    if not train:
        raise ValueError("at least one applicability case is required")
    if not heldout:
        raise ValueError("held-out cases are required")
    train_ids = {case.case_id for case in train}
    heldout_ids = {case.case_id for case in heldout}
    if train_ids & heldout_ids:
        raise ValueError("train and held-out cases must be disjoint")
    if any(not case.case_id.strip() or not case.evidence_ref.strip() for case in (*train, *heldout)):
        raise ValueError("evaluation cases require case_id and evidence_ref")

    baseline_passed = sum(bool(baseline_executor(case, None)) for case in train)
    candidate_passed = sum(bool(candidate_executor(case, candidate_id)) for case in train)
    heldout_passed = sum(bool(candidate_executor(case, candidate_id)) for case in heldout)
    evidence = EvaluationEvidence(
        candidate_id=candidate_id,
        applicability_cases=tuple(case.case_id for case in train),
        baseline_passed=baseline_passed,
        candidate_passed=candidate_passed,
        heldout_passed=heldout_passed,
        heldout_total=len(heldout),
        evidence_refs=tuple(
            [case.evidence_ref for case in train]
            + [case.evidence_ref for case in heldout]
        ),
    )
    return EvaluationRun(evidence=evidence, verdict=evaluate_candidate(evidence))
