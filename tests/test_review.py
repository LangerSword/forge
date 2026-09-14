"""Tests for review.py — deterministic grading of Forge's own verdict systems."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from forge.graph import GraphSpec, NodeSpec
from forge.harness import EvaluationEvidence, GateVerdict
from forge.harness_policy import HarnessPolicyError
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
    assert set(result["suites"].keys()) == {"gate", "verdict", "routing", "policy"}


def test_cli_review_command_reports_suites(capsys) -> None:
    import json

    from forge.cli import main_from_args_for_test

    code = main_from_args_for_test(["review", "--run-id", "review-cli-wireup"])
    out = json.loads(capsys.readouterr().out)

    assert code == 0
    assert out["ok"] is True
    assert out["all_suites_100"] is True
    assert set(out["suites"].keys()) == {"gate", "verdict", "routing", "policy"}
    assert out["suites"]["gate"]["summary"]["all_dimensions_100"] is True

# --------------------------------------------------------------------------
# Policy suite: the declared harness contract, boundary-swept
# --------------------------------------------------------------------------


def test_policy_oracle_matches_validate_request() -> None:
    """Oracle: the documented rule — within policy passes, violations raise
    with the violating field named."""
    from dataclasses import replace

    from forge.harness_policy import HarnessPolicy, validate_request

    policy = HarnessPolicy(
        harness="opencode", allowed_models=("nvidia/", None), max_runtime_s=900.0
    )
    # oracle table: (request-overrides, expected-violation-or-None)
    cases = [
        ({}, None),
        ({"model": "nvidia/abacusai/dracarys-llama-3.1-70b-instruct"}, None),
        ({"model": None}, None),
        ({"model": "sketchy-model"}, "model"),
        ({"harness": "codex"}, "harness"),
        ({"mode": "tui"}, "mode"),
        ({"max_runtime_s": 3600.0}, "runtime"),
        ({"max_polls": 500}, "polls"),
    ]
    for overrides, expected_field in cases:
        request = _policy_suite_request(**overrides)
        if expected_field is None:
            assert validate_request(request, policy) is True
        else:
            with pytest.raises(HarnessPolicyError, match=expected_field):
                validate_request(request, policy)


def _policy_suite_request(**overrides):
    from forge.ao_runner import AORunRequest

    defaults: dict = {
        "run_id": "policy-suite",
        "goal": "policy boundary sweep",
        "project": "forge",
        "worker_name": "w",
        "prompt": "p",
        "harness": "opencode",
        "mode": "chat",
        "max_polls": 40,
        "poll_interval_s": 2.0,
        "max_runtime_s": 300.0,
        "max_idle_s": 90.0,
    }
    defaults.update(overrides)
    return AORunRequest(**defaults)


def test_policy_suite_sweeps_boundaries_and_persists(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    from forge.review import policy_suite

    report = policy_suite(ledger, run_id="review-policy")

    assert report["total_cases"] >= 8
    assert report["summary"]["all_dimensions_100"] is True
    assert report["summary"]["failure_count"] == 0
    events = ledger.events_for_run("review-policy")
    kinds = [e["kind"] for e in events]
    assert kinds.count("review_case") == report["total_cases"]
    assert "review_summary" in kinds


def test_policy_suite_detects_a_late_validating_runner(tmp_path: Path) -> None:
    """The grader must fail: a runner that spawns BEFORE validating is caught
    by the observable spawn seam (violating model reached spawn)."""
    from types import SimpleNamespace

    from forge.harness_policy import HarnessPolicy
    from forge.review import policy_suite

    def late_runner_factory(cli, client):
        class LateRunner:
            """Simulates a regression: spawns first, validates after."""

            def run(self, request, *, policy=None):  # noqa: ANN001
                cli.spawn(model=request.model)  # reaches spawn BEFORE validating
                if policy is not None:
                    policy.validate_request(request)  # too late
                return SimpleNamespace(
                    status="failed", classification=None, session_id="s",
                    worktree=None, artifact_exists=False,
                    verification_passed=False, reason="scripted",
                )

        return LateRunner()

    policy = HarnessPolicy(
        harness="opencode", allowed_models=("nvidia/", None), max_runtime_s=900.0
    )
    ledger = Ledger(tmp_path)
    report = policy_suite(
        ledger, run_id="review-policy-late", runner_factory=late_runner_factory
    )

    assert report["summary"]["all_dimensions_100"] is False
    assert report["summary"]["failure_count"] > 0
    # failures must name the violating model that reached spawn
    assert any(
        case.get("failure") and "reached spawn" in case["failure"]
        for case in report["cases"]
    )
