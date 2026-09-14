"""Tests for review.py — deterministic grading of Forge's own verdict systems."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from forge.graph import GraphSpec, NodeSpec
from forge.harness import EvaluationEvidence, GateVerdict
from forge.ledger import Ledger
from forge.review import (
    expected_gate_status,
    expected_controller_status,
    expected_routing_outcome,
    gate_suite,
    routing_suite,
    verify_controller_verdicts,
)


# --------------------------------------------------------------------------
# Oracle: the promotion gate's documented rule (spec, not implementation)
# --------------------------------------------------------------------------

def test_gate_oracle_validated_requires_all_three() -> None:
    assert expected_gate_status(
        candidate_id="skill-a",
        applicability=True,
        ab_benefit=True,
        heldout_ok=True,
    ) == "validated"


def test_gate_oracle_candidate_when_no_measured_benefit() -> None:
    assert expected_gate_status(
        candidate_id="skill-a", applicability=True, ab_benefit=False, heldout_ok=True
    ) == "candidate"


def test_gate_oracle_rejected_when_heldout_regresses() -> None:
    assert expected_gate_status(
        candidate_id="skill-a", applicability=True, ab_benefit=True, heldout_ok=False
    ) == "rejected"


def test_gate_oracle_rejected_when_insufficient_evidence_refs() -> None:
    assert expected_gate_status(
        candidate_id="skill-a",
        applicability=True,
        ab_benefit=True,
        heldout_ok=True,
        refs_ok=False,
    ) == "rejected"


# --------------------------------------------------------------------------
# Gate suite: sweep the real evaluate_candidate against the oracle
# --------------------------------------------------------------------------

def test_gate_suite_sweeps_boundaries_and_scores_every_case(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    report = gate_suite(ledger, run_id="review-gate")

    assert report["total_cases"] > 100
    assert report["summary"]["status_correct"] == 1.0
    assert report["summary"]["applicability_correct"] == 1.0
    assert report["summary"]["ab_benefit_correct"] == 1.0
    assert report["summary"]["heldout_correct"] == 1.0
    assert report["summary"]["failure_count"] == 0
    assert report["summary"]["all_dimensions_100"] is True
    # boundaries are actually present in the sweep
    boundaries = report["summary"]["scenario_summary"]
    assert boundaries["ab_benefit_equal"] > 0    # baseline == candidate cases
    assert boundaries["heldout_regression"] > 0  # heldout regression cases
    assert boundaries["refs_below_three"] > 0    # insufficient-ref cases


def test_gate_suite_detects_a_regressed_gate(tmp_path: Path) -> None:
    """The grader must be able to fail: feed it a gate that drops the refs rule."""

    def broken_gate(evidence: EvaluationEvidence) -> GateVerdict:
        from dataclasses import replace

        from forge.harness import evaluate_candidate

        # simulate a regression: evidence-refs rule disabled (always >= 3 refs)
        padded = replace(evidence, evidence_refs=("a", "b", "c") * 3)
        return evaluate_candidate(padded)

    ledger = Ledger(tmp_path)
    report = gate_suite(ledger, run_id="review-gate-broken", gate_fn=broken_gate)

    assert report["summary"]["all_dimensions_100"] is False
    assert report["summary"]["failure_count"] > 0
    # failures must carry detail (guard None: passing cases have failure=None)
    assert any(
        case["failure"] and "expected status='rejected'" in case["failure"]
        for case in report["cases"]
    )


# --------------------------------------------------------------------------
# Verdict suite: controller verifier-authority truth table
# --------------------------------------------------------------------------

def test_controller_oracle_truth_table() -> None:
    # worker passed: pass ONLY with fresh artifact AND independent verification
    assert expected_controller_status("passed", True, True) == ("passed", None)
    assert expected_controller_status("passed", True, False) == (
        "failed", "unverified_worker_pass")
    assert expected_controller_status("passed", False, True) == (
        "failed", "unverified_worker_pass")
    assert expected_controller_status("passed", False, False) == (
        "failed", "unverified_worker_pass")
    # non-passed worker statuses pass through, artifact/verifier irrelevant
    assert expected_controller_status("failed", True, True) == ("failed", None)
    assert expected_controller_status("blocked", False, False) == ("blocked", None)


def test_controller_verdicts_truth_table_all_correct(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    report = verify_controller_verdicts(ledger, run_id="review-verdict")

    assert report["total_cases"] == 12  # 3 worker statuses x 2 artifact x 2 verifier
    assert report["summary"]["status_correct"] == 1.0
    assert report["summary"]["reason_correct"] == 1.0
    assert report["summary"]["failure_count"] == 0


# --------------------------------------------------------------------------
# Routing suite: judge decision x retry budget matrix
# --------------------------------------------------------------------------

def test_routing_oracle_matrix() -> None:
    assert expected_routing_outcome("continue", runs=1) == {
        "continues": True, "judged": "passed", "raises": False}
    assert expected_routing_outcome("retry", runs=2, judged="passed") == {
        "continues": True, "judged": "passed", "raises": False}
    assert expected_routing_outcome("escalate", runs=1) == {
        "continues": False, "judged": "blocked", "raises": False}
    assert expected_routing_outcome("teleport", runs=1) == {"raises": True}


def test_routing_suite_matrix_scores_scheduler(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    report = routing_suite(ledger, run_id="review-routing")

    assert report["total_cases"] >= 7
    assert report["summary"]["runs_correct"] == 1.0
    assert report["summary"]["judged_status_correct"] == 1.0
    assert report["summary"]["graph_status_correct"] == 1.0
    assert report["summary"]["oracle_consistent"] == 1.0
    assert report["summary"]["failure_count"] == 0


def test_review_run_persists_to_ledger(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    from forge.review import run_review

    result = run_review(ledger, run_id="review-full")

    events = ledger.events_for_run("review-full")
    kinds = [event["kind"] for event in events]
    assert kinds.count("review_case") > 100
    assert "review_summary" in kinds
    assert ledger.get_run("review-full")["status"] == "passed"
    assert result["all_suites_100"] is True
    assert set(result["suites"].keys()) == {"gate", "verdict", "routing"}


def test_cli_review_command_reports_suites(capsys) -> None:
    import json

    from forge.cli import main_from_args_for_test

    code = main_from_args_for_test(["review", "--run-id", "review-cli-wireup"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["ok"] is True
    assert out["all_suites_100"] is True
    assert set(out["suites"].keys()) == {"gate", "verdict", "routing"}
    assert out["suites"]["gate"]["summary"]["all_dimensions_100"] is True