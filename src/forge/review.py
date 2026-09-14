"""Deterministic review-grading of Forge's own verdict-producing systems.

Methodology (agent-accuracy-grading skill, applied to what Forge itself
built): the correct verdict for every case is COMPUTED from the inputs plus
the documented rule (an oracle) — never judged by an LLM. Three suites:

- ``gate_suite``    — promotion gate boundary sweep (`evaluate_candidate`):
  validated / candidate / rejected across applicability, A/B equality and
  benefit, held-out regression/missing, and evidence-ref thresholds.
- ``verify_controller_verdicts`` — verifier-authority truth table: the
  controller's final task status across worker status x artifact x verifier.
- ``routing_suite`` — judge-decision x retry-budget matrix through the real
  scheduler: continue / retry (budget respected) / escalate / stop / invalid.

Every case and a per-dimension summary are persisted to the Ledger with
failure detail. Each suite takes its graded callable as a parameter, so a
regressed implementation is DETECTED (failures reported), not silently
re-graded green.
"""
from __future__ import annotations

import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .fleet import FleetController
from .graph import GraphSpec, NodeSpec, to_taskgraph
from .harness import EvaluationEvidence, GateVerdict, evaluate_candidate
from .ledger import Ledger
from .scheduler import GraphScheduler
from .schema import GoalSpec

VALID_ROUTING_DECISIONS = ("continue", "retry", "reroute", "escalate", "stop")


# --------------------------------------------------------------------------
# Oracles: the documented rules, encoded independently of the implementation
# --------------------------------------------------------------------------

def expected_gate_status(
    candidate_id: str,
    applicability: bool,
    ab_benefit: bool,
    heldout_ok: bool,
    refs_ok: bool = True,
    counts_ok: bool = True,
) -> str:
    """Spec rule: rejected on hard failures; validated needs all three gates."""
    if not counts_ok or not refs_ok or not heldout_ok:
        return "rejected"
    if applicability and ab_benefit and heldout_ok:
        return "validated"
    return "candidate"


def expected_controller_status(
    worker_status: str, artifact_exists: bool, verification_passed: bool
) -> tuple[str, str | None]:
    """Spec rule: a worker pass counts ONLY with fresh artifact + verifier."""
    if worker_status == "passed":
        if artifact_exists and verification_passed:
            return ("passed", None)
        return ("failed", "unverified_worker_pass")
    return (worker_status, None)


def expected_routing_outcome(
    decision: str, runs: int, judged: str = "passed"
) -> dict[str, Any]:
    if decision not in VALID_ROUTING_DECISIONS:
        return {"raises": True}
    if decision in ("escalate", "stop"):
        return {"continues": False, "judged": "blocked", "raises": False}
    return {"continues": True, "judged": judged, "raises": False}


# --------------------------------------------------------------------------
# Shared grading plumbing
# --------------------------------------------------------------------------

@dataclass
class ScoredCase:
    suite: str
    name: str
    dims: dict[str, bool]
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "name": self.name,
            **self.dims,
            "failure": self.failure,
        }


def _summary(cases: list[ScoredCase]) -> dict[str, Any]:
    dims = [name for name in cases[0].dims] if cases else []
    rates = {
        dim: sum(1 for case in cases if case.dims[dim]) / len(cases)
        for dim in dims
    }
    rates["failure_count"] = sum(1 for case in cases if case.failure is not None)
    # The flag must be computed over the scored DIMENSIONS only. Including
    # failure_count (a raw count) here made it constant False: `abs(count-1)`
    # is only < 1e-9 when there is exactly one failure, so a perfect suite
    # (failure_count 0) was reported as failing.
    rates["all_dimensions_100"] = all(abs(rates[dim] - 1.0) < 1e-9 for dim in dims)
    return rates


def _persist(
    ledger: Ledger, run_id: str, suite: str, cases: list[ScoredCase], summary: dict[str, Any]
) -> None:
    for case in cases:
        ledger.event(run_id, "review_case", "review-grader", case.to_dict())
    ledger.event(run_id, "review_summary", "review-grader", {
        "suite": suite, **summary,
    })


# --------------------------------------------------------------------------
# Suite 1: promotion gate
# --------------------------------------------------------------------------

def _gate_evidence(
    *,
    candidate_id: str = "skill-a",
    applicability_cases: tuple[str, ...] = ("c1", "c2"),
    baseline_passed: int = 1,
    candidate_passed: int = 2,
    heldout_passed: int = 1,
    heldout_total: int = 1,
    evidence_refs: tuple[str, ...] = ("run:1", "run:2", "run:3"),
) -> EvaluationEvidence:
    return EvaluationEvidence(
        candidate_id=candidate_id,
        applicability_cases=applicability_cases,
        baseline_passed=baseline_passed,
        candidate_passed=candidate_passed,
        heldout_passed=heldout_passed,
        heldout_total=heldout_total,
        evidence_refs=evidence_refs,
    )


def _gate_scenarios() -> list[tuple[str, EvaluationEvidence]]:
    scenarios: list[tuple[str, EvaluationEvidence]] = []
    for candidate_id in ("", "skill-a"):
        for cases in ((), ("c1",), ("c1", "c2")):
            for baseline in (-1, 0, 1, 2):
                for candidate in (-1, 0, 1, 2, 3):
                    for heldout_total, heldout_passed in ((0, 0), (1, 0), (1, 1), (3, 0), (3, 3)):
                        for refs in (("a",), ("a", "b"), ("a", "b", "c")):
                            tags = []
                            if candidate == baseline:
                                tags.append("ab_benefit_equal")
                            elif candidate > baseline:
                                tags.append("ab_benefit")
                            if heldout_total > 0 and heldout_passed < heldout_total:
                                tags.append("heldout_regression")
                            if heldout_total == 0:
                                tags.append("heldout_missing")
                            if len(set(refs)) < 3:
                                tags.append("refs_below_three")
                            evidence = _gate_evidence(
                                candidate_id=candidate_id,
                                applicability_cases=cases,
                                baseline_passed=baseline,
                                candidate_passed=candidate,
                                heldout_passed=heldout_passed,
                                heldout_total=heldout_total,
                                evidence_refs=refs,
                            )
                            scenarios.append(("|".join(tags) or "valid_baseline", evidence))
    return scenarios


def gate_suite(
    ledger: Ledger,
    *,
    run_id: str = "review-gate",
    gate_fn: Callable[[EvaluationEvidence], GateVerdict] = evaluate_candidate,
) -> dict[str, Any]:
    """Grade the promotion gate against the spec oracle across the boundary sweep."""
    cases: list[ScoredCase] = []
    tag_counts: Counter[str] = Counter()
    for tag, evidence in _gate_scenarios():
        tag_counts[tag] += 1
        applicability = bool(evidence.candidate_id.strip() and evidence.applicability_cases)
        ab_benefit = evidence.candidate_passed > evidence.baseline_passed
        # heldout_no_regression mirrors evaluate_candidate exactly (total>0 and
        # all held-out trials passed). Negative counts are NOT folded in here —
        # they are the separate counts_ok dimension, so the two rules cannot
        # mask each other.
        heldout_ok = (
            evidence.heldout_total > 0
            and evidence.heldout_passed == evidence.heldout_total
        )
        refs_ok = len(set(evidence.evidence_refs)) >= 3
        counts_ok = evidence.baseline_passed >= 0 and evidence.candidate_passed >= 0
        expected = expected_gate_status(
            evidence.candidate_id, applicability, ab_benefit, heldout_ok, refs_ok, counts_ok
        )
        verdict = gate_fn(evidence)
        observed = verdict.status
        failures: list[str] = []
        if observed != expected:
            failures.append(f"expected status={expected!r}, got {observed!r}")
        if verdict.applicability != applicability:
            failures.append("applicability mismatch")
        if verdict.ab_benefit != ab_benefit:
            failures.append("ab_benefit mismatch")
        if verdict.heldout_no_regression != heldout_ok:
            failures.append("heldout_no_regression mismatch")
        cases.append(ScoredCase(
            suite="gate",
            name=f"gate:{tag}:{evidence.candidate_id or 'anon'}",
            dims={
                "status_correct": observed == expected,
                "applicability_correct": verdict.applicability == applicability,
                "ab_benefit_correct": verdict.ab_benefit == ab_benefit,
                "heldout_correct": verdict.heldout_no_regression == heldout_ok,
            },
            failure="; ".join(failures) if failures else None,
        ))
    summary = _summary(cases)
    summary["scenario_summary"] = dict(tag_counts)
    _persist(ledger, run_id, "gate", cases, summary)
    return {
        "suite": "gate",
        "total_cases": len(cases),
        "summary": summary,
        "cases": [case.to_dict() for case in cases],
    }


# --------------------------------------------------------------------------
# Suite 2: controller verifier-authority truth table
# --------------------------------------------------------------------------

def _scratch_root(tag: str) -> Path:
    """A fresh root for child executions.

    The suites' child controllers/schedulers are grading scaffolding, not real
    Forge runs: running them under a scratch root keeps the project ledger
    clean and — because each invocation gets a new root — makes the suites
    idempotent (no stale ``run_id``/``graph_id`` collision on a second run).
    """
    return Path(tempfile.mkdtemp(prefix=f"forge-review-{tag}-"))


def _verdict_runner(worker_status: str, artifact: bool, verifier: bool):
    from types import SimpleNamespace

    def runner_factory(request):
        return SimpleNamespace(run=lambda req: SimpleNamespace(
            status=worker_status, session_id="s", worktree=None,
            artifact_exists=artifact, verification_passed=verifier,
            classification=SimpleNamespace(value=worker_status),
            reason="scripted"))
    return runner_factory


def verify_controller_verdicts(ledger: Ledger, *, run_id: str = "review-verdict") -> dict[str, Any]:
    """Grade FleetController's final task status across the evidence truth table."""
    scratch = _scratch_root("verdict")
    cases: list[ScoredCase] = []
    goal = GoalSpec(
        goal="review verdict derivation",
        repo=str(scratch),
        acceptance=["ok"],
        harness="local",
    )

    index = 0
    for worker_status in ("passed", "failed", "blocked"):
        for artifact in (True, False):
            for verifier in (True, False):
                index += 1
                expected_status, expected_reason = expected_controller_status(
                    worker_status, artifact, verifier
                )
                controller = FleetController(
                    scratch, runner_factory=_verdict_runner(worker_status, artifact, verifier)
                )
                taskgraph = to_taskgraph(GraphSpec(
                    nodes=[NodeSpec(
                        node_id="v", node_type="specialist", title="v",
                        goal="verify", acceptance=["ok"], artifact_path="out.json",
                    )],
                    max_depth=1,
                    rationale="verdict suite",
                ))
                report = controller.run(goal, taskgraph, run_id=f"verdict-{index}")
                outcome = report.task_outcomes[0]
                failures: list[str] = []
                status_correct = outcome.status == expected_status
                if not status_correct:
                    failures.append(
                        f"expected status={expected_status!r}, "
                        f"got {outcome.status!r} (worker={worker_status}, "
                        f"artifact={artifact}, verifier={verifier})"
                    )
                reason_correct = (
                    expected_reason is None or outcome.reason == expected_reason
                )
                if not reason_correct:
                    failures.append(
                        f"expected reason={expected_reason!r}, got {outcome.reason!r}"
                    )
                cases.append(ScoredCase(
                    suite="verdict",
                    name=f"verdict:{worker_status}:artifact={artifact}:verifier={verifier}",
                    dims={"status_correct": status_correct, "reason_correct": reason_correct},
                    failure="; ".join(failures) if failures else None,
                ))
    summary = _summary(cases)
    _persist(ledger, run_id, "verdict", cases, summary)
    return {
        "suite": "verdict",
        "total_cases": len(cases),
        "summary": summary,
        "cases": [case.to_dict() for case in cases],
    }


# --------------------------------------------------------------------------
# Suite 3: routing decision x retry budget matrix
# --------------------------------------------------------------------------

_ROUTING_CASES: list[dict[str, Any]] = [
    {"name": "continue", "decision": "continue", "runner_status": "passed", "max_retries": 1,
     "expected_runs": 1, "expected_judged": "passed", "expected_graph": "passed"},
    {"name": "retry-budget1-pass", "decision": "retry", "runner_status": "passed", "max_retries": 1,
     "expected_runs": 2, "expected_judged": "passed", "expected_graph": "passed"},
    {"name": "retry-budget0", "decision": "retry", "runner_status": "passed", "max_retries": 0,
     "expected_runs": 1, "expected_judged": "passed", "expected_graph": "passed"},
    {"name": "retry-budget1-fail", "decision": "retry", "runner_status": "failed", "max_retries": 1,
     "expected_runs": 2, "expected_judged": "failed", "expected_graph": "failed"},
    {"name": "escalate", "decision": "escalate", "runner_status": "passed", "max_retries": 1,
     "expected_runs": 1, "expected_judged": "blocked", "expected_graph": "failed"},
    {"name": "stop", "decision": "stop", "runner_status": "passed", "max_retries": 1,
     "expected_runs": 1, "expected_judged": "blocked", "expected_graph": "failed"},
    {"name": "invalid", "decision": "teleport", "runner_status": "passed", "max_retries": 1,
     "expected_runs": 0, "expected_judged": "failed", "expected_graph": "failed", "raises": True},
]


def routing_suite(ledger: Ledger, *, run_id: str = "review-routing") -> dict[str, Any]:
    """Grade the scheduler's judge-routing semantics through the real scheduler."""
    scratch = _scratch_root("routing")
    cases: list[ScoredCase] = []

    for spec in _ROUTING_CASES:
        calls: list[str] = []

        def runner_factory(request: Any) -> Any:
            from types import SimpleNamespace
            runner_status = spec["runner_status"]
            def run(req):
                calls.append(req.run_id)
                return SimpleNamespace(
                    status=runner_status, session_id="s", worktree=None,
                    artifact_exists=(runner_status == "passed"),
                    verification_passed=(runner_status == "passed"),
                    classification=SimpleNamespace(value=runner_status),
                    reason="scripted")
            return SimpleNamespace(run=run)

        def judge(node, result):
            return {"decision": spec["decision"], "reason": "scripted"}

        scheduler = GraphScheduler(
            scratch, runner_factory=runner_factory, judge=judge,
            max_retries=spec["max_retries"],
        )
        graph = GraphSpec(nodes=[
            NodeSpec(node_id="s1", node_type="specialist", title="work",
                     goal="do work", acceptance=["done"]),
            NodeSpec(node_id="j1", node_type="judge", title="judge",
                     goal="judge", acceptance=["decision"], deps=["s1"]),
        ])
        failure: str | None = None
        raised = False
        try:
            report = scheduler.run(graph, graph_id=f"routing-{len(cases)}")
        except ValueError as exc:
            raised = True
            report = None

        if spec.get("raises"):
            runs_correct = raised
            # The contract for an invalid decision is "raises": there is no
            # judged or graph status to assert, so those dimensions are
            # satisfied vacuously when it raises (and fail if it does not).
            judged_status_correct = raised
            graph_status_correct = raised
            if not raised:
                failure = "expected ValueError for invalid decision, none raised"
        elif raised:
            runs_correct = judged_status_correct = graph_status_correct = False
            failure = "unexpected exception during routing"
        else:
            assert report is not None
            judged_runs = [call for call in calls if call.endswith(":s1")]
            runs_correct = len(judged_runs) == spec["expected_runs"]
            judged_result = next(
                (n for n in report.node_results if n.node_id == "s1"), None
            )
            judged_status_correct = (
                judged_result is not None
                and judged_result.status == spec["expected_judged"]
            )
            graph_status_correct = report.status == spec["expected_graph"]
            if not runs_correct:
                failure = (
                    f"expected {spec['expected_runs']} judged runs, "
                    f"got {len(judged_runs)}"
                )
            elif not judged_status_correct:
                failure = (
                    f"expected judged status={spec['expected_judged']!r}, "
                    f"got {judged_result.status if judged_result else None!r}"
                )
            elif not graph_status_correct:
                failure = f"expected graph status={spec['expected_graph']!r}, got {report.status!r}"

        # Cross-check the case table against the independent oracle, so the
        # oracle is exercised (not dead code) and a table typo is caught.
        oracle = expected_routing_outcome(
            spec["decision"], runs=spec["expected_runs"], judged=spec["expected_judged"]
        )
        if spec.get("raises"):
            oracle_consistent = oracle == {"raises": True}
        else:
            oracle_consistent = (
                oracle["raises"] is False
                and oracle["continues"] is (spec["decision"] not in ("escalate", "stop"))
                and oracle["judged"] == spec["expected_judged"]
            )

        cases.append(ScoredCase(
            suite="routing",
            name=f"routing:{spec['name']}",
            dims={
                "runs_correct": runs_correct,
                "judged_status_correct": judged_status_correct,
                "graph_status_correct": graph_status_correct,
                "oracle_consistent": oracle_consistent,
            },
            failure=failure,
        ))

    summary = _summary(cases)
    _persist(ledger, run_id, "routing", cases, summary)
    return {
        "suite": "routing",
        "total_cases": len(cases),
        "summary": summary,
        "cases": [case.to_dict() for case in cases],
    }


# --------------------------------------------------------------------------
# Full review
# --------------------------------------------------------------------------

def run_review(ledger: Ledger, *, run_id: str = "review") -> dict[str, Any]:
    """Run all three suites against one ledger and report per-suite rates."""
    gate_report = gate_suite(ledger, run_id=run_id)
    verdict_report = verify_controller_verdicts(ledger, run_id=run_id)
    routing_report = routing_suite(ledger, run_id=run_id)

    suites = {
        gate_report["suite"]: gate_report,
        verdict_report["suite"]: verdict_report,
        routing_report["suite"]: routing_report,
    }
    all_suites_100 = all(
        report["summary"]["all_dimensions_100"] for report in suites.values()
    )
    ledger.run(
        run_id,
        "deterministic review of Forge verdict systems",
        "REVIEW",
        "review-grader",
        "passed" if all_suites_100 else "failed",
    )
    return {"run_id": run_id, "all_suites_100": all_suites_100, "suites": suites}